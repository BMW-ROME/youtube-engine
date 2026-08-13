"""
SQLite tracking database for the YouTube Engine.
Every video moves through a defined pipeline status as it's produced:

    QUEUED -> SCRIPTING -> VOICING -> MUSIC -> IMAGING -> ASSEMBLING
            -> OPTIMIZING -> UPLOADING -> PUBLISHED
                                        -> FAILED (from any stage)

This module owns the schema and all read/write access to it. Every other
pipeline stage (script_writer, voice_gen, image_gen, etc.) should update
video status through the functions here rather than touching SQLite directly.
"""

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from config.settings import settings

DB_FILENAME = "content.db"

VALID_STATUSES = (
    "QUEUED",
    "SCRIPTING",
    "VOICING",
    "MUSIC",
    "IMAGING",
    "ASSEMBLING",
    "OPTIMIZING",
    "UPLOADING",
    "PUBLISHED",
    "FAILED",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    channel         TEXT NOT NULL,
    topic           TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'QUEUED',
    video_mode      TEXT,
    metadata_json   TEXT,               -- script, seo, pinned comment, etc. (JSON blob)
    output_path     TEXT,               -- local path once assembled
    youtube_video_id TEXT,
    youtube_url     TEXT,
    error_message   TEXT,
    retry_count     INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    published_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_videos_channel ON videos(channel);
CREATE INDEX IF NOT EXISTS idx_videos_status ON videos(status);
CREATE INDEX IF NOT EXISTS idx_videos_created_at ON videos(created_at);

CREATE TABLE IF NOT EXISTS shorts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_video_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    title           TEXT,
    output_path     TEXT,
    youtube_video_id TEXT,
    youtube_url     TEXT,
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_shorts_parent ON shorts(parent_video_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _db_path() -> Path:
    return settings.content_path / DB_FILENAME


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create tables if they don't exist. Safe to call on every startup."""
    with get_connection() as conn:
        conn.executescript(SCHEMA)


@dataclass
class VideoRecord:
    id: int
    channel: str
    topic: str
    status: str
    video_mode: str | None
    metadata: dict[str, Any] = field(default_factory=dict)
    output_path: str | None = None
    youtube_video_id: str | None = None
    youtube_url: str | None = None
    error_message: str | None = None
    retry_count: int = 0
    created_at: str = ""
    updated_at: str = ""
    published_at: str | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "VideoRecord":
        raw_meta = row["metadata_json"]
        return cls(
            id=row["id"],
            channel=row["channel"],
            topic=row["topic"],
            status=row["status"],
            video_mode=row["video_mode"],
            metadata=json.loads(raw_meta) if raw_meta else {},
            output_path=row["output_path"],
            youtube_video_id=row["youtube_video_id"],
            youtube_url=row["youtube_url"],
            error_message=row["error_message"],
            retry_count=row["retry_count"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            published_at=row["published_at"],
        )


def create_video(channel: str, topic: str, video_mode: str | None = None) -> int:
    """Insert a new video row in QUEUED status. Returns the new row's id."""
    now = _now()
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO videos (channel, topic, status, video_mode, metadata_json,
                                 created_at, updated_at)
            VALUES (?, ?, 'QUEUED', ?, '{}', ?, ?)
            """,
            (channel, topic, video_mode, now, now),
        )
        return cur.lastrowid


def update_status(
    video_id: int,
    status: str,
    error_message: str | None = None,
) -> None:
    """Transition a video to a new pipeline status. Pass error_message when
    status='FAILED' to record what went wrong."""
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status '{status}'. Must be one of {VALID_STATUSES}")

    now = _now()
    published_at = now if status == "PUBLISHED" else None

    with get_connection() as conn:
        if published_at:
            conn.execute(
                """
                UPDATE videos
                SET status = ?, error_message = ?, updated_at = ?, published_at = ?
                WHERE id = ?
                """,
                (status, error_message, now, published_at, video_id),
            )
        else:
            conn.execute(
                """
                UPDATE videos
                SET status = ?, error_message = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, error_message, now, video_id),
            )


def increment_retry(video_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE videos SET retry_count = retry_count + 1, updated_at = ? WHERE id = ?",
            (_now(), video_id),
        )


def update_metadata(video_id: int, patch: dict[str, Any]) -> None:
    """Merge `patch` into the video's existing metadata JSON blob. Used by
    script_writer, seo_optimizer, shorts_gen etc. to attach their outputs
    (script, seo fields, pinned_comment, end_screen_topics) without each
    stage needing its own dedicated columns."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT metadata_json FROM videos WHERE id = ?", (video_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"No video with id {video_id}")
        current = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
        current.update(patch)
        conn.execute(
            "UPDATE videos SET metadata_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(current), _now(), video_id),
        )


def set_output_path(video_id: int, output_path: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE videos SET output_path = ?, updated_at = ? WHERE id = ?",
            (output_path, _now(), video_id),
        )


def set_youtube_info(video_id: int, youtube_video_id: str, youtube_url: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE videos
            SET youtube_video_id = ?, youtube_url = ?, updated_at = ?
            WHERE id = ?
            """,
            (youtube_video_id, youtube_url, _now(), video_id),
        )


def get_video(video_id: int) -> VideoRecord | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()
        return VideoRecord.from_row(row) if row else None


def list_videos(
    channel: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[VideoRecord]:
    query = "SELECT * FROM videos WHERE 1=1"
    params: list[Any] = []
    if channel:
        query += " AND channel = ?"
        params.append(channel)
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
        return [VideoRecord.from_row(r) for r in rows]


def get_failed_videos(max_retries: int = 3) -> list[VideoRecord]:
    """Videos in FAILED status that haven't exceeded the retry budget yet.
    Used by the orchestrator's retry job."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM videos WHERE status = 'FAILED' AND retry_count < ? "
            "ORDER BY created_at ASC",
            (max_retries,),
        ).fetchall()
        return [VideoRecord.from_row(r) for r in rows]


def add_short(parent_video_id: int, title: str, output_path: str | None = None) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO shorts (parent_video_id, title, output_path, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (parent_video_id, title, output_path, _now()),
        )
        return cur.lastrowid


def set_short_youtube_info(short_id: int, youtube_video_id: str, youtube_url: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE shorts SET youtube_video_id = ?, youtube_url = ? WHERE id = ?",
            (youtube_video_id, youtube_url, short_id),
        )


def get_shorts_for_video(video_id: int) -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM shorts WHERE parent_video_id = ? ORDER BY id ASC",
            (video_id,),
        ).fetchall()


def channel_stats(channel: str) -> dict[str, Any]:
    """Aggregate counts by status for a single channel, used by the dashboard."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) as n FROM videos WHERE channel = ? GROUP BY status",
            (channel,),
        ).fetchall()
        counts = {r["status"]: r["n"] for r in rows}
        total = sum(counts.values())
        return {
            "channel": channel,
            "total": total,
            "published": counts.get("PUBLISHED", 0),
            "failed": counts.get("FAILED", 0),
            "in_progress": total - counts.get("PUBLISHED", 0) - counts.get("FAILED", 0),
            "by_status": counts,
        }


def all_channel_stats(channels: list[str]) -> list[dict[str, Any]]:
    return [channel_stats(c) for c in channels]
