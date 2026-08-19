"""
core/trend_engine.py

RSS + trending topic discovery for the YouTube Engine.

This is the topic-supply layer of the scheduler. The orchestrator pulls a
"next topic" from content_db; without a source feeding new topics in, the
DB has nothing to offer except re-queued FAILED videos (see
content_db.get_next_topic), and the orchestrator falls back to a tiny
static list. trend_engine fills that gap: it watches RSS feeds per channel
niche, dedupes entry titles against topics already in content_db, and seeds
new QUEUED video rows so the pipeline always has fresh supply.

Public API:
    discover_topics(codename=None, limit=5) -> list[str]
        Fetch + dedupe topic strings from a channel's configured RSS feeds.
    replenish(channel_codename, count=1) -> int
        Seed `count` new QUEUED rows in content_db from fresh topics.
    get_feed_sources(codename) -> list[str]
        Resolved feed URLs for a channel (env-overridable).

Design notes:
- feedparser is imported lazily (module-level try/except fallback) so an
  environment without it still imports cleanly -- matching the resilience
  pattern used throughout this repo.
- Topic generation is source-of-truth driven: entry titles are cleaned,
  truncated to a reasonable length, and deduped against content_db on the
  exact topic string so the scheduler never re-produces the same video.
- All network calls are wrapped; any failure degrades to an empty list
  (and a log), never an exception -- the scheduler must never stall on a
  dead RSS feed.

Feed sources:
    Per-channel feed URLs default to the DICT below. Any channel can be
    overridden (or pointed at a feed for the first time) via env var:

        TREND_RSS_<CODENAME>=https://feed.one,https://feed.two

    Leave a channel out of FEED_SOURCES (or unset the env var) and
    discover_topics()/replenish() simply return nothing for it.
"""

from __future__ import annotations

import logging
import os
import re
from typing import List, Optional

logger = logging.getLogger(__name__)

try:
    import feedparser  # type: ignore
except ImportError:  # pragma: no cover
    feedparser = None

# Default feed sources per channel codename. These are editable defaults --
# verified public feeds for the well-covered niches; channels without a
# good public feed are left empty and are meant to be pointed at a
# niche-specific source via TREND_RSS_<CODENAME> in .env.
FEED_SOURCES: dict[str, list[str]] = {
    "finance": ["https://finance.yahoo.com/rss/topstories"],
    "tech": ["https://techcrunch.com/feed/", "https://www.theverge.com/rss/index.xml"],
    "trending": ["https://feeds.bbci.co.uk/news/rss.xml"],
    "mmo": [],
    "thee3lite": [],
    "legal": [],
    "stories": [],
}

# Topics longer than this (in characters) are truncated -- keeps the stored
# topic string readable and reusable as a script-generation prompt.
MAX_TOPIC_LENGTH = 120

# Strip common RSS noise from entry titles so stored topics are clean.
_CLEANUP_PATTERNS = [
    re.compile(r"\s+", re.UNICODE),          # collapse whitespace
    re.compile(r"\s*[:|-]\s*$"),             # trailing colons/dashes
    re.compile(r"^(BREAKING|WATCH|VIDEO):\s*", re.IGNORECASE),
]


def _env_key(codename: str) -> str:
    return f"TREND_RSS_{codename.upper().replace('-', '_')}"


def get_feed_sources(codename: str) -> List[str]:
    """Resolved feed URLs for a channel: env override wins, else FEED_SOURCES."""
    env_value = os.getenv(_env_key(codename))
    if env_value:
        return [u.strip() for u in env_value.split(",") if u.strip()]
    return list(FEED_SOURCES.get(codename, []))


def _clean_topic(title: str) -> str:
    """Normalize an RSS entry title into a usable pipeline topic string."""
    text = title.strip()
    for pattern in _CLEANUP_PATTERNS:
        text = re.sub(pattern, " ", text)
    text = text.strip(" -|:")
    return text[:MAX_TOPIC_LENGTH]


def _existing_topics(codename: Optional[str], limit: int = 500) -> set[str]:
    """Topics currently known to content_db, for dedupe. Never raises."""
    try:
        from core import content_db
        rows = content_db.list_videos(channel=codename, limit=limit)
        return {row.topic for row in rows}
    except Exception as exc:  # noqa: BLE001
        logger.warning("trend_engine: could not read existing topics from content_db: %s", exc)
        return set()


def discover_topics(codename: Optional[str] = None, limit: int = 5) -> List[str]:
    """
    Fetch + dedupe topic strings from a channel's configured RSS feeds.

    Args:
        codename: channel codename to look up sources for. None -> only
            feeds that have a default/env mapping via get_feed_sources;
            sources are looked up per-codename.
        limit: max topics to return.

    Returns:
        Cleaned, deduped topic strings. Empty list if feedparser isn't
        installed, the channel has no sources, or every feed failed.
    """
    if feedparser is None:
        logger.warning(
            "trend_engine: 'feedparser' not installed - cannot fetch RSS topics. "
            "Run: pip install feedparser"
        )
        return []

    codenames = [codename] if codename else list(FEED_SOURCES.keys())
    sources: List[str] = []
    for name in codenames:
        sources.extend(get_feed_sources(name))

    known = _existing_topics(codename)
    seen: set[str] = set()
    topics: List[str] = []

    for url in sources:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:20]:
                raw = getattr(entry, "title", "") or ""
                topic = _clean_topic(raw)
                if not topic or topic in known or topic in seen:
                    continue
                seen.add(topic)
                topics.append(topic)
                if len(topics) >= limit:
                    return topics
        except Exception as exc:  # noqa: BLE001
            logger.warning("trend_engine: failed to parse feed %s: %s", url, exc)

    return topics[:limit]


def replenish(channel_codename: str, count: int = 1) -> int:
    """
    Seed `count` new QUEUED content_db rows for one channel from fresh topics.

    Args:
        channel_codename: which channel to produce topics for.
        count: max new rows to create per call (scheduler topic-replenishment
            job typically calls this once per channel per day with count=1).

    Returns:
        Number of new video rows created (0 if none available or DB write
        failed -- the scheduler should treat 0 as a normal no-op).
    """
    from core import content_db
    from config.channels import get_channel

    try:
        channel = get_channel(channel_codename)
    except KeyError:
        logger.warning("trend_engine: replenish called for unknown channel %r", channel_codename)
        return 0

    topics = discover_topics(codename=channel_codename, limit=count)
    created = 0
    for topic in topics:
        try:
            content_db.create_video(
                channel=channel.codename, topic=topic, video_mode=channel.video_mode
            )
            logger.info("trend_engine: seeded QUEUED video for %r: %r", channel.codename, topic)
            created += 1
        except Exception as exc:  # noqa: BLE001
            logger.error("trend_engine: failed to seed topic %r: %s", topic, exc)
    return created


def run_replenishment() -> dict:
    """
    One-shot replenishment pass over all registered channels (the 2 AM
    scheduler job). Returns a per-channel summary dict; never raises.
    """
    from config.channels import CHANNELS

    summary: dict[str, int] = {}
    for codename in list(CHANNELS.keys()):
        summary[codename] = replenish(channel_codename=codename, count=1)
    total = sum(summary.values())
    logger.info("trend_engine: replenishment pass complete, %d new topics seeded", total)
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    result = run_replenishment()
    for codename, count in result.items():
        print(f"  {codename}: {count} topic(s) seeded")
    print("Total:", sum(result.values()))