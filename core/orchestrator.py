"""
core/orchestrator.py

Scheduler layer sitting on top of core/pipeline.py.

Responsible for:
  - Running the pipeline on a recurring schedule (daily/hourly/interval)
  - Pulling the next topic from a queue (falls back to a static list if
    no queue/database is configured)
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

FALLBACK_TOPICS = [
    "AI automation for beginners",
    "5 tools that save you hours every week",
    "how local LLMs are changing software development",
]


def _next_topic() -> str:
    """
    Fetch the next topic to produce a video for.

    Tries core.content_db (SQLite tracking layer) first; falls back to
    a static rotation if the DB or table isn't available, so the
    scheduler never stalls waiting on infrastructure.
    """
    try:
        from core.content_db import get_next_topic
        topic = get_next_topic()
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


def run_once(topic: Optional[str] = None) -> Optional[PipelineResult]:
    """Run a single pipeline pass, catching any error so callers never crash."""
    chosen_topic = topic or _next_topic()
    logger.info("Orchestrator triggering pipeline run for topic: %s", chosen_topic)
    try:
        result = run_pipeline(chosen_topic)
        _persist_result(result)
        if result.success:
            logger.info("Run succeeded for topic: %s", chosen_topic)
        else:
            logger.warning(
                "Run finished with failures for topic '%s': %s",
                chosen_topic,
                result.failed_stages,
            )
        return result
    except Exception:
        logger.error(
            "Unhandled exception during pipeline run for topic '%s':\n%s",
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


if __name__ == "__main__":
    import sys

    if "--once" in sys.argv:
        run_once()
    else:
        run_forever()
