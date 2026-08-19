"""
core/orchestrator.py

Scheduler layer sitting on top of core/pipeline.py.

Responsible for:
  - Running the pipeline on a per-channel cron schedule (APScheduler),
    matching the README's Schedule table (post times per channel, 2 AM
    topic replenishment, 30-min failed-video retry, 11 PM daily report)
  - Falling back to a plain fixed-interval loop (run_forever) when
    APScheduler isn't installed or is explicitly disabled
  - Pulling the next topic from a queue (falls back to a static list if
    no queue/database is configured, or to core.trend_engine seeding)
  - Persisting run history/results so failures can be reviewed later
  - Never letting one bad run kill the scheduler process itself

Resilience contract:
  - Every scheduled run is wrapped in try/except at the orchestrator
    level, IN ADDITION to the per-stage resilience already inside
    pipeline.run_pipeline(). A crash in one run logs the error and
    the scheduler continues waiting for the next scheduled run.
  - If the topic queue/database is unavailable, orchestrator falls
    back to a small built-in default topic list rather than stalling.
"""

import json
import logging
import os
import time
import traceback
from dataclasses import asdict
from datetime import datetime
from typing import List, Optional

from core.pipeline import run_pipeline, PipelineResult

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("orchestrator")

RUN_HISTORY_PATH = os.getenv("RUN_HISTORY_PATH", "run_history.jsonl")
DEFAULT_INTERVAL_SECONDS = int(os.getenv("PIPELINE_INTERVAL_SECONDS", str(6 * 60 * 60)))

# APScheduler is optional. If it isn't installed, run_scheduler() falls
# back to run_forever() so the scheduler never hard-fails on a missing dep.
_APSCHEDULER_ENABLED = os.getenv("APSCHEDULER_ENABLED", "true").lower() not in ("0", "false", "no")

FALLBACK_TOPICS = [
    "AI automation for beginners",
    "5 tools that save you hours every week",
    "how local LLMs are changing software development",
]


def _next_topic(channel_codename: Optional[str] = None) -> str:
    """
    Fetch the next topic to produce a video for.

    Tries core.content_db (SQLite tracking layer) first; falls back to
    a static rotation if the DB or table isn't available, so the
    scheduler never stalls waiting on infrastructure.
    """
    try:
        from core.content_db import get_next_topic
        topic = get_next_topic(channel=channel_codename)
        if topic:
            return topic
        logger.warning("content_db returned no topic, using fallback list")
    except Exception as exc:
        logger.warning("content_db unavailable (%s), using fallback list", exc)

    index = int(time.time()) % len(FALLBACK_TOPICS)
    return FALLBACK_TOPICS[index]


def _persist_result(result: PipelineResult) -> None:
    """Append a JSON line summarizing the run so history survives restarts."""
    try:
        record = asdict(result)
        record["timestamp"] = datetime.utcnow().isoformat() + "Z"
        with open(RUN_HISTORY_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")
    except Exception as exc:
        logger.error("Failed to persist run history: %s", exc)


def _index_result(result: PipelineResult) -> None:
    """Auto-index a produced video into the transcript RAG store (optional).
    Guarded by settings.rag_enabled; failures never affect the run."""
    try:
        from config.settings import settings
        if not settings.rag_enabled or getattr(result, "video_id", None) is None:
            return
        from core.rag_index import index_video
        index_video(result.video_id)
    except Exception as exc:
        logger.warning("RAG auto-index skipped for video %s: %s",
                       getattr(result, "video_id", None), exc)


def run_once(topic: Optional[str] = None, channel_codename: Optional[str] = None) -> Optional[PipelineResult]:
    """Run a single pipeline pass, catching any error so callers never crash."""
    chosen_topic = topic or _next_topic(channel_codename=channel_codename)
    logger.info("Orchestrator triggering pipeline run for channel=%s topic: %s", channel_codename, chosen_topic)
    try:
        result = run_pipeline(chosen_topic, channel_codename=channel_codename or "finance")
        _persist_result(result)
        if result.success:
            logger.info("Run succeeded for channel=%s topic: %s", channel_codename, chosen_topic)
        else:
            logger.warning(
                "Run finished with failures for channel=%s topic '%s': %s",
                channel_codename,
                chosen_topic,
                result.failed_stages,
            )
        _index_result(result)
        return result
    except Exception:
        logger.error(
            "Unhandled exception during pipeline run for channel=%s topic '%s':\n%s",
            channel_codename,
            chosen_topic,
            traceback.format_exc(),
        )
        return None


def run_forever(interval_seconds: int = DEFAULT_INTERVAL_SECONDS, topics: Optional[List[str]] = None) -> None:
    """
    Continuously run the pipeline on a fixed interval.

    A crash in any single iteration is caught and logged; the loop
    always continues to the next scheduled run rather than exiting.
    """
    logger.info("Starting orchestrator loop, interval=%ss", interval_seconds)
    queue = list(topics) if topics else None
    i = 0
    while True:
        try:
            topic = None
            if queue:
                topic = queue[i % len(queue)]
                i += 1
            run_once(topic)
        except Exception:
            logger.error(
                "Orchestrator loop iteration failed unexpectedly:\n%s",
                traceback.format_exc(),
            )
        logger.info("Sleeping for %ss until next run", interval_seconds)
        time.sleep(interval_seconds)


def run_replenishment() -> None:
    """2 AM job: seed fresh QUEUED topics for every channel from RSS feeds."""
    try:
        from core.trend_engine import run_replenishment as _replenish_all
        _replenish_all()
    except Exception:
        logger.error("Replenishment job failed:\n%s", traceback.format_exc())


def run_failed_retry() -> None:
    """Every-30-min job: re-run FAILED videos that haven't exhausted retries."""
    try:
        from core import content_db
        failed = content_db.get_failed_videos(max_retries=3)
        for record in failed:
            logger.info("Retrying failed video id=%s topic=%r channel=%s",
                        record.id, record.topic, record.channel)
            run_once(topic=record.topic, channel_codename=record.channel)
    except Exception:
        logger.error("Failed-retry job failed:\n%s", traceback.format_exc())


def run_daily_report() -> None:
    """11 PM job: summarize today's run history."""
    try:
        if not os.path.exists(RUN_HISTORY_PATH):
            logger.info("Daily report: no run history file yet at %s", RUN_HISTORY_PATH)
            return
        with open(RUN_HISTORY_PATH, "r", encoding="utf-8") as fh:
            lines = [l for l in fh if l.strip()]
        successes = sum(1 for l in lines if '"failed_stages": []' in l)
        failures = len(lines) - successes
        logger.info(
            "Daily report: %d run(s) recorded, %d success, %d failed(partial). ",
            len(lines), successes, failures,
        )
    except Exception:
        logger.error("Daily report job failed:\n%s", traceback.format_exc())


def run_scheduler() -> None:
    """
    Start the APScheduler background scheduler with per-channel cron jobs.

    If APScheduler isn't installed or APSCHEDULER_ENABLED=false, falls
    back to run_forever() with PIPELINE_INTERVAL_SECONDS (the loop still
    works, it just can't honor per-channel post times).
    """
    if not _APSCHEDULER_ENABLED:
        logger.warning("APSCHEDULER_ENABLED is off - using run_forever() interval loop instead.")
        run_forever()
        return

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError as exc:
        logger.warning(
            "APScheduler not installed (%s) - falling back to fixed-interval loop. "
            "Run: pip install apscheduler",
            exc,
        )
        run_forever()
        return

    from config.channels import CHANNELS

    scheduler = BackgroundScheduler()
    scheduler.add_job(run_replenishment, CronTrigger(hour=2, minute=0), id="topic_replenishment")
    scheduler.add_job(run_failed_retry, CronTrigger(minute="*/30"), id="failed_retry")
    scheduler.add_job(run_daily_report, CronTrigger(hour=23, minute=0), id="daily_report")

    for codename, channel in CHANNELS.items():
        hour, minute = channel.post_time_est.split(":")
        scheduler.add_job(
            run_once,
            CronTrigger(hour=int(hour), minute=int(minute)),
            kwargs={"channel_codename": codename},
            id=f"channel_{codename}",
        )
        logger.info(
            "Scheduled channel %s (post_time_est=%s, videos_per_day=%s)",
            codename, channel.post_time_est, channel.videos_per_day,
        )

    scheduler.start()
    logger.info("APScheduler started with %d cron jobs.", len(scheduler.get_jobs()))
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        logger.info("Scheduler shutting down.")
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    import sys

    if "--once" in sys.argv:
        channel_codename = None
        for flag in ("--channel", "--channel-codename"):
            if flag in sys.argv:
                idx = sys.argv.index(flag)
                if idx + 1 < len(sys.argv) and not sys.argv[idx + 1].startswith("--"):
                    channel_codename = sys.argv[idx + 1]
        run_once(channel_codename=channel_codename or "finance")
    else:
        run_scheduler()
