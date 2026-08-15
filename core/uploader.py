"""
core/uploader.py

Stage 10 of the content pipeline: YouTube Upload (UPLOAD_MODE=youtube_api).

Handles the direct YouTube Data API v3 resumable upload path. This is one of
four upload modes described in the README (local, skip, pipedream,
youtube_api); the other three are handled by core/pipedream_uploader.py
and the pipeline orchestrator directly. This module isolates the Google
API client imports so a missing/unconfigured Google Cloud project never
crashes the rest of the pipeline -- it degrades to a clear log + None
return, matching the resilience architecture used throughout this repo.

Public API:
    upload_video(video_path, seo_result, channel, thumbnail_path=None,
                 privacy_status="private") -> str | None

Design notes:
- google-auth / google-auth-oauthlib / google-api-python-client are
  imported lazily inside functions (not at module load) so environments
  without YouTube API set up (UPLOAD_MODE=local/skip/pipedream) never pay
  the import cost or risk an ImportError crashing the process.
- Resumable upload via MediaFileUpload(resumable=True) with chunked
  status polling, per YouTube Data API best practice for large video files.
- OAuth2 refresh-token flow: credentials are rebuilt from env vars
  (YOUTUBE_CLIENT_ID/SECRET/REFRESH_TOKEN) set up once via scripts/setup.py,
  never interactive at upload time.
- Category/channel targeting comes from the ChannelConfig passed in
  (category_id, channel_id) -- see config/channels.py.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

REQUIRED_ENV_VARS = ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN")


def _has_youtube_credentials() -> bool:
    return all(os.getenv(var) for var in REQUIRED_ENV_VARS)


def _build_youtube_client():
    """
    Lazily import google-auth/google-api-python-client and build an
    authenticated YouTube Data API v3 client from env-var OAuth2 credentials.
    Returns None (with a logged error) if the packages aren't installed or
    credentials are missing/invalid -- never raises.
    """
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError as exc:
        logger.error(
            "[uploader] google-api-python-client / google-auth not installed - "
            "run: pip install google-auth google-auth-oauthlib google-api-python-client (%s)",
            exc,
        )
        return None
    if not _has_youtube_credentials():
        logger.error(
            "[uploader] Missing YouTube OAuth2 env vars (%s) - run scripts/setup.py first.",
            ", ".join(REQUIRED_ENV_VARS),
        )
        return None
    try:
        creds = Credentials(
            token=None,
            refresh_token=os.getenv("YOUTUBE_REFRESH_TOKEN"),
            client_id=os.getenv("YOUTUBE_CLIENT_ID"),
            client_secret=os.getenv("YOUTUBE_CLIENT_SECRET"),
            token_uri="https://oauth2.googleapis.com/token",
            scopes=["https://www.googleapis.com/auth/youtube.upload"],
        )
        return build("youtube", "v3", credentials=creds)
    except Exception as exc:  # noqa: BLE001 - any auth/build failure is non-fatal here
        logger.error("[uploader] Failed to build YouTube API client: %s", exc)
        return None


def upload_video(
    video_path: str,
    seo_result,
    channel,
    thumbnail_path: Optional[str] = None,
    privacy_status: str = "private",
) -> Optional[str]:
    """
    Upload a finished video to YouTube via the Data API v3.

    Args:
        video_path: path to the final assembled MP4 (video_assembler.py output).
        seo_result: SEOResult from seo_optimizer.py (title/description/tags).
        channel: ChannelConfig instance (provides category_id, channel_id
            for logging/verification; the API uploads to the account tied
            to the OAuth token, not an arbitrary channel_id).
        thumbnail_path: optional custom thumbnail (thumbnail_text.py output).
            If provided, it is set via a separate thumbnails().set() call.
        privacy_status: "private", "unlisted", or "public". Defaults to
            "private" so every upload requires a deliberate publish step --
            never auto-publishes per the safety-first design of this repo.

    Returns:
        The uploaded YouTube video ID on success, or None if upload failed
        for any reason (missing deps, bad credentials, API error, missing
        file). Never raises -- a failed upload should not crash the
        pipeline; the video remains on disk for manual/local retry.
    """
    if not os.path.exists(video_path):
        logger.error("[uploader] Video file not found: %s", video_path)
        return None

    youtube = _build_youtube_client()
    if youtube is None:
        return None

    try:
        from googleapiclient.http import MediaFileUpload
    except ImportError as exc:
        logger.error("[uploader] googleapiclient.http import failed: %s", exc)
        return None

    body = {
        "snippet": {
            "title": seo_result.title,
            "description": seo_result.description,
            "tags": seo_result.tags,
            "categoryId": getattr(channel, "category_id", "22"),
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype="video/mp4")

    try:
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                logger.info("[uploader] Upload progress: %d%%", int(status.progress() * 100))
        video_id = response.get("id")
        logger.info("[uploader] Uploaded video -> https://youtu.be/%s", video_id)
    except Exception as exc:  # noqa: BLE001 - any upload-time failure is non-fatal here
        logger.error("[uploader] Upload failed: %s", exc)
        return None

    if thumbnail_path and os.path.exists(thumbnail_path):
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumbnail_path, mimetype="image/jpeg"),
            ).execute()
            logger.info("[uploader] Custom thumbnail set for %s", video_id)
        except Exception as exc:  # noqa: BLE001 - thumbnail failure shouldn't fail the upload
            logger.warning("[uploader] Thumbnail upload failed (video still uploaded): %s", exc)

    return video_id
