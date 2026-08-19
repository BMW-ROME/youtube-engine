"""
scripts/upload_ready.py

Batch upload of finished videos that are still on disk (UPLOAD_MODE local
or skip mode leaves them in output/videos/). Reads the `.meta.json` sidecar
written by core/pipedream_uploader.py in "local" mode, reconstructs the
SEO payload, and dispatches through the configured upload path:

  - UPLOAD_MODE=local      -> rewrite/save sidecar (still manual upload)
  - UPLOAD_MODE=skip       -> no-op (leaves video on disk)
  - UPLOAD_MODE=pipedream  -> POST metadata + local path to the webhook
  - UPLOAD_MODE=youtube_api-> direct YouTube Data API v3 resumable upload
                             (requires google-* packages + OAuth env vars)

Shared engine is `upload_ready.upload_path_aux(video_path)` so
scripts/quick_upload.py can reuse it for a single video.

Usage:
    python scripts/upload_ready.py                          # all videos in output/videos/
    python scripts/upload_ready.py --ready-dir output/videos
    python scripts/upload_ready.py --dry-run                # list only, no upload
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

# Ensure the repo root (parent of scripts/) is importable as core/config
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("upload_ready")

DEFAULT_READY_DIR = Path("output") / "videos"


def _seo_from_meta(meta: Dict[str, Any]) -> SimpleNamespace:
    """Reconstruct a seo_result-shaped object from a .meta.json sidecar."""
    return SimpleNamespace(
        title=meta.get("title", ""),
        description=meta.get("description", ""),
        tags=meta.get("tags", []),
        hashtags=meta.get("hashtags", []),
        pinned_comment=meta.get("pinned_comment", ""),
        end_screen_topics=meta.get("end_screen_topics", []),
    )


def _channel_from_meta(meta: Dict[str, Any]):
    """Resolve the ChannelConfig a sidecar was produced for (best-effort)."""
    from config.channels import get_channel
    codename = meta.get("channel")
    if not codename:
        return None
    try:
        return get_channel(codename)
    except KeyError:
        return None


def find_ready_videos(ready_dir: Path) -> List[Path]:
    """All *.meta.json sidecars in the ready dir (each implies a finished MP4)."""
    if not ready_dir.exists():
        logger.warning("Ready dir not found: %s", ready_dir)
        return []
    return sorted(
        ready_dir.glob("*.meta.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def upload_one_from_sidecar(
    sidecar_path: Path,
    mode: Optional[str] = None,
    webhook_url: Optional[str] = None,
    privacy_token: str = "private",
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Upload a single finished video using its metadata sidecar.

    Args:
        sidecar_path: path to a `<video>.meta.json` produced in local mode.
        mode: UPLOAD_MODE override (local/skip/pipedream/youtube_api).
        webhook_url: override for pipedream mode.
        privacy_token: privacy status for youtube_api uploads (private default).
        dry_run: True -> just log what WOULD happen, don't dispatch.

    Returns:
        A status dict. Never raises -- each return path has a "status" key.
    """
    try:
        meta = json.loads(sidecar_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.error("Cannot read sidecar %s: %s", sidecar_path, exc)
        return {"status": "error", "error": str(exc)}

    video_path = meta.get("video_path")
    if not video_path or not Path(video_path).exists():
        # Sidecar stores the absolute path at pipeline time; if it moved,
        # fall back to same-directory naming.
        video_path = str(sidecar_path.with_name(sidecar_path.stem))
        if not Path(video_path).exists():
            logger.error("Video file not found for sidecar %s (looked at %s)", sidecar_path, video_path)
            return {"status": "error", "error": "video file not found"}

    seo = _seo_from_meta(meta)
    channel = _channel_from_meta(meta)

    if dry_run:
        logger.info("[dry-run] would upload %s (mode=%s)", video_path, mode)
        return {"status": "dry_run", "video_path": video_path, "mode": mode}

    from config.settings import settings
    from core.pipedream_uploader import dispatch_upload
    from core.uploader import upload_video

    upload_mode = mode or settings.upload_mode
    if upload_mode == "youtube_api":
        video_id = upload_video(
            video_path=video_path,
            seo_result=seo,
            channel=channel,
            thumbnail_path=meta.get("thumbnail_path"),
            privacy_status=privacy_token,
        )
        if video_id:
            return {"status": "uploaded", "video_id": video_id, "video_path": video_path}
        return {"status": "error", "error": "youtube_api upload failed", "video_path": video_path}

    return dispatch_upload(
        mode=upload_mode,
        video_path=video_path,
        seo_result=seo,
        channel=channel,
        thumbnail_path=meta.get("thumbnail_path"),
        webhook_url=webhook_url,
    )


def upload_ready(
    ready_dir: Path = DEFAULT_READY_DIR,
    mode: Optional[str] = None,
    webhook_url: Optional[str] = None,
    dry_run: bool = False,
) -> List[Dict[str, Any]]:
    """Batch-upload all finished videos found in `ready_dir` (or local/skip)."""
    results: List[Dict[str, Any]] = []
    for sidecar in find_ready_videos(ready_dir):
        logger.info("Processing %s", sidecar)
        results.append(
            upload_one_from_sidecar(
                sidecar,
                mode=mode,
                webhook_url=webhook_url,
                dry_run=dry_run,
            )
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch upload finished videos.")
    parser.add_argument("--ready-dir", type=Path, default=DEFAULT_READY_DIR,
                        help="Directory containing *.meta.json + finished MP4s")
    parser.add_argument("--mode", choices=["local", "skip", "pipedream", "youtube_api"],
                        help="Override UPLOAD_MODE for this pass")
    parser.add_argument("--webhook-url", help="Override webhook URL (pipedream mode)")
    parser.add_argument("--dry-run", action="store_true", help="List what would be uploaded")
    args = parser.parse_args()

    results = upload_ready(
        ready_dir=args.ready_dir,
        mode=args.mode,
        webhook_url=args.webhook_url,
        dry_run=args.dry_run,
    )
    ok = [r for r in results if r.get("status") not in ("error",)]
    logger.info("Done: %d/%d processed successfully.", len(ok), len(results))
    for r in results:
        if r.get("status") == "error":
            logger.error("  %s: %s", r.get("video_path", "?"), r.get("error"))
    sys.exit(0 if len(ok) == len(results) else 1)


if __name__ == "__main__":
    main()