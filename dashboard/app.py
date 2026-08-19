"""
dashboard/app.py

FastAPI dashboard + REST API for the YouTube Engine pipeline.

Reads the JSON-lines run history produced by core/orchestrator.py
(default path: run_history.jsonl) and the SQLite video tracking DB
(core/content_db.py) and exposes:

  - GET  /                          dark-themed HTML dashboard (auto-refresh 15s)
  - GET  /health                    health check
  - GET  /api/channels              per-channel stats (from content_db)
  - GET  /api/videos                list videos (filterable by channel/status)
  - GET  /api/videos/{video_id}     single video detail
  - POST /api/trigger/{channel}     trigger one pipeline production run
  - POST /api/topics/{channel}/generate   seed QUEUED topics from RSS (trend_engine)
  - GET  /api/logs                  recent log lines (run history tail)

Resilience contract:
  - If the history file is missing or unreadable, endpoints still render
    with empty state / empty list instead of crashing.
  - Malformed individual lines are skipped and logged, not fatal.
  - Reads/writes never raise on transient DB state.

Run with:
    python dashboard/app.py
Then open http://localhost:<DASHBOARD_PORT> (default 8000).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("dashboard")

app = FastAPI(title="YouTube Engine Dashboard")

HERE = Path(__file__).resolve().parent
STATIC_DIR = HERE / "static"
TEMPLATES_DIR = HERE / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

RUN_HISTORY_PATH = os.getenv("RUN_HISTORY_PATH", "run_history.jsonl")

# sys.path bootstrap so `python dashboard/app.py` can import core/config
# even when run from the dashboard/ directory directly.
import sys
_REPO_ROOT = HERE.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _load_runs() -> List[Dict[str, Any]]:
    """Load run history, tolerating a missing file or malformed lines."""
    runs: List[Dict[str, Any]] = []
    if not os.path.exists(RUN_HISTORY_PATH):
        return runs
    try:
        with open(RUN_HISTORY_PATH, "r", encoding="utf-8") as fh:
            for line_num, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    runs.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    logger.warning("Skipping malformed line %d: %s", line_num, exc)
    except Exception as exc:
        logger.error("Failed to read run history: %s", exc)
    runs.reverse()  # most recent first
    return runs


def _videos_to_dicts(videos) -> List[Dict[str, Any]]:
    out = []
    for v in videos:
        out.append({
            "id": v.id,
            "channel": v.channel,
            "topic": v.topic,
            "status": v.status,
            "video_mode": v.video_mode,
            "metadata": v.metadata,
            "output_path": v.output_path,
            "youtube_video_id": v.youtube_video_id,
            "youtube_url": v.youtube_url,
            "error_message": v.error_message,
            "retry_count": v.retry_count,
            "created_at": v.created_at,
            "updated_at": v.updated_at,
            "published_at": v.published_at,
        })
    return out


@app.get("/", response_class=HTMLResponse)
async def index():
    return templates.TemplateResponse("index.html", {"request": {}})


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/channels")
async def api_channels():
    try:
        from core import content_db
        from config.channels import all_channels
        channels = all_channels()
        stats = content_db.all_channel_stats([c.codename for c in channels])
        return stats
    except Exception as exc:
        logger.error("api_channels failed: %s", exc)
        return JSONResponse(status_code=200, content=[])


@app.get("/api/videos")
async def api_videos(channel: Optional[str] = None, status: Optional[str] = None, limit: int = 50):
    try:
        from core import content_db
        content_db.init_db()
        rows = content_db.list_videos(channel=channel, status=status, limit=limit)
        return _videos_to_dicts(rows)
    except Exception as exc:
        logger.error("api_videos failed: %s", exc)
        return JSONResponse(status_code=200, content=[])


@app.get("/api/videos/{video_id}")
async def api_video(video_id: int):
    try:
        from core import content_db
        content_db.init_db()
        row = content_db.get_video(video_id)
        if row is None:
            raise HTTPException(status_code=404, detail="video not found")
        return _videos_to_dicts([row])[0]
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("api_video failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/trigger/{channel}")
async def api_trigger(channel: str):
    """Trigger one production run for a channel via the orchestrator."""
    try:
        from core.orchestrator import run_once
        result = run_once(channel_codename=channel)
        if result is None:
            return JSONResponse(status_code=500, content={"ok": False, "error": "pipeline run raised"})
        return {"ok": result.success, "video_id": result.video_id, "failed_stages": result.failed_stages}
    except Exception as exc:
        logger.error("api_trigger failed: %s", exc)
        return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})


@app.post("/api/topics/{channel}/generate")
async def api_generate_topics(channel: str):
    """Seed fresh QUEUED topics for a channel via core/trend_engine."""
    try:
        from core.trend_engine import replenish
        created = replenish(channel_codename=channel, count=1)
        return {"ok": True, "channel": channel, "created": created}
    except Exception as exc:
        logger.error("api_generate_topics failed: %s", exc)
        return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})


@app.get("/api/logs")
async def api_logs(lines: int = 200):
    """Return the tail of the run history file as a list of log records."""
    runs = _load_runs()
    return runs[:lines]


if __name__ == "__main__":
    import uvicorn
    from config.settings import settings
    logger.info("Starting dashboard on http://%s:%d", settings.dashboard_host, settings.dashboard_port)
    uvicorn.run(app, host=settings.dashboard_host, port=settings.dashboard_port)