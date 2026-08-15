"""
core/pipedream_uploader.py

Stage 10 of the content pipeline: Pipedream + Local-Save Upload.

Handles the three non-YouTube-API upload modes from the README's
UPLOAD_MODE setting: "local" (save + write a metadata sidecar JSON for
manual upload), "skip" (no-op, video stays on disk), and "pipedream"
(POST video metadata + a downloadable/local path to a Pipedream webhook,
which can then relay to Zapier, Make, or a custom automation without this
repo ever touching the real YouTube API/OAuth surface). core/uploader.py
handles the fourth mode (direct youtube_api).

Public API:
    dispatch_upload(mode, video_path, seo_result, channel,
                     thumbnail_path=None, webhook_url=None) -> dict

Design notes:
- Every mode returns a status dict rather than raising, so the pipeline
  orchestrator can log/continue regardless of upload outcome, matching
  the resilience architecture used throughout this repo.
- "local" mode writes a `<video>.meta.json` sidecar next to the video
  containing all SEO metadata, so a human can copy/paste into YouTube
  Studio without re-deriving anything.
- "pipedream" mode never sends the raw video file over HTTP (webhooks
  are for metadata/notifications, not multi-GB uploads) -- it sends the
  local file path plus metadata, matching Pipedream's typical webhook
  relay pattern for local/self-hosted pipelines.
- requests is imported lazily so environments without it installed can
  still use "local" and "skip" modes with zero import errors.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

VALID_MODES = ("local", "skip", "pipedream")


def _seo_to_dict(seo_result) -> dict:
    return {
        "title": seo_result.title,
        "description": seo_result.description,
        "tags": seo_result.tags,
        "hashtags": seo_result.hashtags,
        "pinned_comment": seo_result.pinned_comment,
        "end_screen_topics": getattr(seo_result, "end_screen_topics", []),
    }


def _upload_local(video_path: str, seo_result, channel, thumbnail_path: Optional[str]) -> dict:
    """
    "local" mode: video already lives on disk (video_assembler.py output).
    Write a metadata sidecar JSON next to it so a human can manually
    complete the YouTube Studio upload without re-typing metadata.
    """
    meta_path = str(Path(video_path).with_suffix("")) + ".meta.json"
    payload = {
        "video_path": video_path,
        "thumbnail_path": thumbnail_path,
        "channel": getattr(channel, "codename", None),
        "channel_display_name": getattr(channel, "display_name", None),
        "category_id": getattr(channel, "category_id", None),
        **_seo_to_dict(seo_result),
    }
    try:
        Path(meta_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        logger.info("[pipedream_uploader] Local mode: wrote metadata sidecar -> %s", meta_path)
        return {"status": "local_saved", "video_path": video_path, "meta_path": meta_path}
    except OSError as exc:
        logger.error("[pipedream_uploader] Failed to write metadata sidecar: %s", exc)
        return {"status": "error", "error": str(exc)}


def _upload_skip(video_path: str) -> dict:
    """"skip" mode: intentional no-op, video remains on disk untouched."""
    logger.info("[pipedream_uploader] Skip mode: leaving video on disk at %s", video_path)
    return {"status": "skipped", "video_path": video_path}


def _upload_pipedream(
    video_path: str,
    seo_result,
    channel,
    thumbnail_path: Optional[str],
    webhook_url: Optional[str],
) -> dict:
    """
    "pipedream" mode: POST metadata + local file path to a Pipedream (or
    any generic) webhook URL. Never uploads the raw video bytes -- the
    webhook receiver is expected to pull from the local/shared path.
    """
    if not webhook_url:
        logger.error("[pipedream_uploader] Pipedream mode selected but no webhook_url provided.")
        return {"status": "error", "error": "missing webhook_url"}
    try:
        import requests
    except ImportError as exc:
        logger.error("[pipedream_uploader] 'requests' not installed - cannot POST to webhook: %s", exc)
        return {"status": "error", "error": "requests not installed"}

    payload = {
        "video_path": video_path,
        "thumbnail_path": thumbnail_path,
        "channel": getattr(channel, "codename", None),
        "channel_display_name": getattr(channel, "display_name", None),
        "category_id": getattr(channel, "category_id", None),
        **_seo_to_dict(seo_result),
    }
    try:
        resp = requests.post(webhook_url, json=payload, timeout=15)
        resp.raise_for_status()
        logger.info("[pipedream_uploader] Posted to Pipedream webhook (status=%d)", resp.status_code)
        return {"status": "pipedream_sent", "video_path": video_path, "http_status": resp.status_code}
    except Exception as exc:  # noqa: BLE001 - any network/HTTP failure is non-fatal here
        logger.error("[pipedream_uploader] Webhook POST failed: %s", exc)
        return {"status": "error", "error": str(exc)}


def dispatch_upload(
    mode: str,
    video_path: str,
    seo_result,
    channel,
    thumbnail_path: Optional[str] = None,
    webhook_url: Optional[str] = None,
) -> dict:
    """
    Route to the correct non-YouTube-API upload handler based on UPLOAD_MODE.

    Args:
        mode: one of "local", "skip", "pipedream" (see VALID_MODES).
            "youtube_api" is NOT handled here -- see core/uploader.py.
        video_path: path to the final assembled MP4.
        seo_result: SEOResult from seo_optimizer.py.
        channel: ChannelConfig instance.
        thumbnail_path: optional custom thumbnail path.
        webhook_url: required only for "pipedream" mode.

    Returns:
        A status dict, always containing at least a "status" key. Never
        raises -- an unknown mode or handler failure returns
        {"status": "error", ...} so the pipeline can log and continue.
    """
    if mode not in VALID_MODES:
        logger.error(
            "[pipedream_uploader] Unknown upload mode '%s' - expected one of %s "
            "(or 'youtube_api', handled by core/uploader.py).",
            mode, VALID_MODES,
        )
        return {"status": "error", "error": f"unknown mode '{mode}'"}
    if not Path(video_path).exists():
        logger.error("[pipedream_uploader] Video file not found: %s", video_path)
        return {"status": "error", "error": "video file not found"}

    if mode == "local":
        return _upload_local(video_path, seo_result, channel, thumbnail_path)
    if mode == "skip":
        return _upload_skip(video_path)
    return _upload_pipedream(video_path, seo_result, channel, thumbnail_path, webhook_url)
