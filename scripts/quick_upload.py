"""
scripts/quick_upload.py

Quick single-video upload for one finished MP4. Reuses the shared upload
engine from scripts/upload_ready.py so there's exactly one upload path.

Usage:
    python scripts/quick_upload.py output/videos/2.mp4
    python scripts/quick_upload.py path/to/video.mp4 --mode youtube_api
    python scripts/quick_upload.py path/to/video.mp4 --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure the repo root (parent of scripts/) is importable as core/config
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.upload_ready import upload_one_from_sidecar  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Quick single-video upload.")
    parser.add_argument("video_path", help="Path to the finished MP4")
    parser.add_argument("--mode", choices=["local", "skip", "pipedream", "youtube_api"],
                        help="Override UPLOAD_MODE for this upload")
    parser.add_argument("--webhook-url", help="Override webhook URL (pipedream mode)")
    parser.add_argument("--privacy", default="private",
                        help="Privacy for youtube_api uploads (private/unlisted/public)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen, don't upload")
    args = parser.parse_args()

    video = Path(args.video_path)
    if not video.exists():
        print(f"[FAIL] Video not found: {video}")
        sys.exit(1)

    # Sidecar naming convention from core/pipedream_uploader.py local mode:
    #   <video>.meta.json  (same directory, stem + ".meta.json")
    meta_path_candidates = [
        video.with_name(video.stem + ".meta.json"),
        video.with_name(video.name + ".meta.json"),
    ]

    chosen = next((c for c in meta_path_candidates if c.exists()), None)
    if chosen is None:
        print(f"[FAIL] No metadata sidecar found for {video}. Looked for:")
        for c in meta_path_candidates:
            print(f"  {c}")
        print("Run the pipeline with UPLOAD_MODE=local first so a sidecar is written,")
        print("or pass the sidecar path via --mode for bare upload.")
        sys.exit(1)

    result = upload_one_from_sidecar(
        chosen,
        mode=args.mode,
        webhook_url=args.webhook_url,
        privacy_token=args.privacy,
        dry_run=args.dry_run,
    )
    print(f"[{result.get('status', '?')}] {result}")
    if result.get("status") == "error":
        sys.exit(1)


if __name__ == "__main__":
    main()