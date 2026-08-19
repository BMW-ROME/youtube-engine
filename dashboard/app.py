"""
dashboard/app.py

FastAPI dashboard + REST API for the YouTube Engine pipeline.

Reads the JSON-lines run history produced by core/orchestrator.py
(default path: run_history.jsonl) and the SQLite video tracking DB
(core/content_db.py) and exposes:

  - GET  /                          dark-themed HTML dashboard (auto-refresh 15s)
  - GET  /videos                    dark-themed "video library" card grid
  - GET  /media?p=<relpath>         serve local thumbnails/videos from content_path
  - GET  /search                    dark-themed transcript RAG search page
  - GET  /health                    health check
  - GET  /api/channels              per-channel stats (from content_db)
  - GET  /api/videos                list videos (filterable by channel/status)
  - GET  /api/videos/{video_id}     single video detail
  - GET  /api/search?q=&channel=    hybrid transcript search (RAG store)
  - GET  /api/ask?q=                transcript question-answering (chat LLM)
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
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
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


def _web_path(path: Optional[str]) -> Optional[str]:
    """Convert an absolute/relative path to a /media-relative web path if it
    is a real file inside content_path, else None. Handles paths stored as
    content_path-relative AND repo-root-relative (e.g. 'output/images/...')."""
    from config.settings import settings
    if not path:
        return None
    root = settings.content_path.resolve()
    p = Path(path)
    if p.is_absolute():
        candidates = [p]
    else:
        candidates = [root / p, Path.cwd() / p]
    for cand in candidates:
        cand = cand.resolve()
        if cand.is_file() and (cand == root or root in cand.parents):
            return cand.relative_to(root).as_posix()
    return None


def _thumbnail_web_path(video) -> Optional[str]:
    """Resolve a card thumbnail for a video: thumbnail_text output first
    (defaults to '{first_scene_stem}_text{suffix}' beside the source image,
    see thumbnail_text.py), then any scene image, else None."""
    from config.settings import settings
    root = settings.content_path
    meta = video.metadata or {}
    candidates: List[str] = []
    image_paths = meta.get("image_paths") or []
    if image_paths:
        first = str(image_paths[0])
        candidates.append(str(Path(first).with_name(f"{Path(first).stem}_text{Path(first).suffix}")))
        candidates.append(first)
    scene_dir = root / "images" / f"video_{video.id}"
    if scene_dir.is_dir():
        seen = set(candidates)
        for hit in sorted(scene_dir.glob("scene_*_text.*")):
            if str(hit) not in seen:
                candidates.append(str(hit))
                seen.add(str(hit))
        for hit in sorted(scene_dir.glob("scene_*.*")):
            if str(hit) not in seen:
                candidates.append(str(hit))
                seen.add(str(hit))
    for cand in candidates:
        web = _web_path(cand)
        if web:
            return web
    return None


def _video_cards(videos) -> List[Dict[str, Any]]:
    """Build the card payloads for the /videos library page."""
    cards = []
    for v in videos:
        meta = v.metadata or {}
        seo = meta.get("seo") or {}
        cards.append({
            "id": v.id,
            "title": seo.get("title") or v.topic or f"Video {v.id}",
            "description": seo.get("description") or "",
            "channel": v.channel,
            "status": v.status or "UNKNOWN",
            "video_mode": v.video_mode,
            "created_at": v.created_at,
            "published_at": v.published_at,
            "youtube_url": v.youtube_url,
            "thumbnail": _thumbnail_web_path(v),
            "media": _web_path(v.output_path),
        })
    return cards


@app.get("/", response_class=HTMLResponse)
async def index():
    return templates.TemplateResponse("index.html", {"request": {}})


@app.get("/videos", response_class=HTMLResponse)
async def videos_page():
    """Dark-themed card grid of produced videos ('video library')."""
    try:
        from core import content_db
        content_db.init_db()
        rows = content_db.list_videos(limit=200)
        return templates.TemplateResponse(
            "cards.html", {"request": {}, "cards": _video_cards(rows)}
        )
    except Exception as exc:
        logger.error("videos_page failed: %s", exc)
        return templates.TemplateResponse("cards.html", {"request": {}, "cards": []})


@app.get("/media")
async def media(p: str = ""):
    """Serve a local content file (thumbnail/video) but ONLY from inside
    content_path -- path traversal is blocked."""
    from config.settings import settings
    if not p:
        raise HTTPException(status_code=404, detail="missing p")
    root = settings.content_path.resolve()
    candidate = (root / p).resolve()
    if candidate != root and root not in candidate.parents:
        logger.warning("media: blocked path traversal attempt for %r", p)
        raise HTTPException(status_code=404, detail="not found")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(str(candidate))


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


@app.get("/api/search")
async def api_search(q: str = "", channel: Optional[str] = None, limit: int = 5):
    """Hybrid (FTS5 + optional vectors) transcript search across the RAG store."""
    try:
        from core.rag_index import search
        hits = search(q, top_k=limit, channel=channel)
        return {"query": q, "vector_available": any(h.get("vector") for h in hits), "hits": hits}
    except Exception as exc:
        logger.error("api_search failed: %s", exc)
        return JSONResponse(status_code=200, content={"query": q, "hits": []})


@app.get("/api/ask")
async def api_ask(q: str = "", limit: int = 3):
    """RAG question-answering over produced transcripts (uses the chat LLM)."""
    try:
        from core.rag_index import ask
        return ask(q, sources=limit)
    except Exception as exc:
        logger.error("api_ask failed: %s", exc)
        return JSONResponse(status_code=200, content={"question": q, "answer": "", "sources": []})


@app.get("/search", response_class=HTMLResponse)
async def search_page():
    """Dark-themed page with a search box + ask box for the RAG index."""
    return templates.TemplateResponse("search.html", {"request": {}})


if __name__ == "__main__":
    import uvicorn
    from config.settings import settings
    logger.info("Starting dashboard on http://%s:%d", settings.dashboard_host, settings.dashboard_port)
    uvicorn.run(app, host=settings.dashboard_host, port=settings.dashboard_port)