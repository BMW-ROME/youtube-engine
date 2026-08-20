"""
core/pipeline.py

Master orchestration module for the YouTube automation engine.

Chains together all 10 pipeline stages using their REAL module/function
names and signatures (audited 2026-08-16 against the actual committed
code, not the README's stage names):

  1. Script      -> core.script_writer.generate_script
  2. Voice       -> core.voice_gen.generate_voice
  3. Music       -> core.music_mixer.mix_music
  4. Images      -> core.image_gen.generate_images
  5. Thumbnail   -> core.thumbnail_text.add_thumbnail_text
  6. Effects     -> core.video_effects.apply_effect
  7. Assembly    -> core.video_assembler.assemble_video
  8. SEO         -> core.seo_optimizer.optimize_seo
  9. Shorts      -> core.shorts_gen.generate_shorts
  10. Upload     -> core.uploader.upload_video (youtube_api mode) OR
                    core.pipedream_uploader.dispatch_upload (local/skip/pipedream)

Fix 2026-08-16 (second pass): added the missing content_db.init_db() call
before create_video(). This was invisible in earlier tests because they
used a fake content_db stub that didn't require table creation -- once
tested against the REAL content_db.py, every run failed with
"sqlite3.OperationalError: no such table: videos". Lesson: fakes that are
too permissive hide real integration bugs just as effectively as broken
imports do.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from config.channels import ChannelConfig, get_channel
from config.settings import settings
from core import content_db

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("pipeline")

REQUIRED_STAGES = {"script", "assembly"}


@dataclass
class PipelineResult:
    topic: str
    channel_codename: str
    video_id: Optional[int] = None
    script: Any = None
    voice_path: Optional[str] = None
    music_path: Optional[str] = None
    image_paths: list = field(default_factory=list)
    thumbnail_path: Optional[str] = None
    effect_clip_paths: list = field(default_factory=list)
    final_video_path: Optional[str] = None
    chapter_markers: list = field(default_factory=list)
    seo_result: Any = None
    shorts_paths: list = field(default_factory=list)
    upload_result: Any = None
    failed_stages: list = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.failed_stages) == 0


def _run_stage(name: str, result: PipelineResult, func, *args, **kwargs):
    try:
        logger.info("Starting stage: %s", name)
        output = func(*args, **kwargs)
        logger.info("Completed stage: %s", name)
        return output
    except Exception as exc:
        logger.error("Stage '%s' failed: %s", name, exc, exc_info=True)
        result.failed_stages.append(name)
        if name in REQUIRED_STAGES:
            logger.critical("Required stage '%s' failed. Aborting pipeline.", name)
            _mark_failed(result, f"required stage '{name}' failed: {exc}")
            raise
        return None


def _mark_failed(result: PipelineResult, message: str) -> None:
    """Best-effort FAILED status write so a crashed run always lands in FAILED
    (never stuck half-way through the stage chain). Never masks the original
    error -- failures here are logged at debug level and swallowed."""
    try:
        if result.video_id is not None:
            content_db.update_status(result.video_id, "FAILED", error_message=message)
    except Exception as exc:  # noqa: BLE001 - status writes must never crash a run
        logger.debug("pipeline: could not mark video %s FAILED: %s", result.video_id, exc)


def _parse_mmss(value: Any) -> Optional[float]:
    """Parse a clock string ('MM:SS' or 'HH:MM:SS') into seconds.
    Returns None if the value isn't parseable."""
    if not isinstance(value, str):
        return None
    try:
        parts = value.strip().split(":")
        if len(parts) == 2:
            return float(int(parts[0]) * 60 + int(parts[1]))
        if len(parts) == 3:
            return float(int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2]))
    except (TypeError, ValueError):
        return None
    return None


def _build_chapter_markers(result: PipelineResult) -> list:
    """Build REAL YouTube chapter markers. Prefers the LLM's
    chapter_timestamps ({"time": "MM:SS", "title": ...}) carried on the script;
    falls back to probing the actual rendered effect-clip durations so markers
    still track the real video even when the model left timestamps empty."""
    script = result.script

    markers: list[dict] = []
    for item in getattr(script, "chapter_timestamps", None) or []:
        if not isinstance(item, dict):
            continue
        ts = _parse_mmss(item.get("time"))
        if ts is None:
            continue
        if markers and ts < markers[-1]["timestamp_seconds"]:
            continue
        markers.append({
            "timestamp_seconds": ts,
            "title": str(item.get("title", "")).strip() or f"Scene {len(markers) + 1}",
        })
    if markers:
        logger.info("pipeline: using %d LLM chapter_timestamps", len(markers))
        return markers

    scene_count = len(script.scenes)
    durations: list[float] = []
    try:
        from core.video_assembler import _probe_duration
        for clip in result.effect_clip_paths:
            probed = _probe_duration(clip)
            durations.append(probed if probed and probed > 0 else 4.0)
    except Exception as exc:  # noqa: BLE001 - probing is best-effort
        logger.warning("pipeline: clip duration probing unavailable (%s), using defaults", exc)
    if len(durations) != scene_count:
        durations = [4.0] * scene_count
    titles = [f"Scene {i + 1}" for i in range(scene_count)]
    from core.video_assembler import build_chapter_markers
    return build_chapter_markers(durations, titles)


def run_pipeline(
    topic: str,
    channel_codename: str = "finance",
    config: Optional[dict] = None,
    clients: Optional[dict] = None,
    video_id: Optional[int] = None,
) -> PipelineResult:
    """Run the full pipeline for a topic. By default a fresh video row is
    created (QUEUED). Pass `video_id` to RE-RUN an existing row in place --
    used by the orchestrator's failed-retry job so a retry updates the
    original row (PUBLISHED on success, FAILED on failure) instead of
    creating a duplicate video every 30 minutes."""
    config = config or {}
    clients = clients or {}
    channel = get_channel(channel_codename)
    result = PipelineResult(topic=topic, channel_codename=channel_codename)

    content_db.init_db()
    if video_id is None:
        video_id = content_db.create_video(
            channel=channel.codename, topic=topic, video_mode=channel.video_mode
        )
    else:
        content_db.update_status(video_id, "QUEUED")
    result.video_id = video_id

    try:
        from core.script_writer import generate_script
        result.script = _run_stage(
            "script", result, generate_script,
            channel=channel, topic=topic,
            client=clients.get("script_chat_client") or clients.get("chat_client"),
            video_id=video_id,
        )
    except ImportError as exc:
        logger.error("script_writer module unavailable: %s", exc)
        result.failed_stages.append("script")

    if result.script is not None:
        try:
            from core.voice_gen import generate_voice
            voice_result = _run_stage(
                "voice", result, generate_voice,
                channel=channel, script=result.script, video_id=video_id,
                synthesizer=clients.get("synthesizer"),
                concatenator=clients.get("concatenator"),
            )
            result.voice_path = str(voice_result.output_path) if voice_result else None
        except ImportError as exc:
            logger.error("voice_gen module unavailable: %s", exc)
            result.failed_stages.append("voice")

    if result.voice_path:
        try:
            from core.music_mixer import mix_music
            music_result = _run_stage(
                "music", result, mix_music,
                channel=channel, voice_path=Path(result.voice_path), video_id=video_id,
                mixer=clients.get("mixer"),
            )
            result.music_path = str(music_result.output_path) if music_result else result.voice_path
        except ImportError as exc:
            logger.error("music_mixer module unavailable: %s", exc)
            result.failed_stages.append("music")
            result.music_path = result.voice_path

    if result.script is not None:
        try:
            from core.image_gen import generate_images
            image_result = _run_stage(
                "images", result, generate_images,
                channel=channel, script=result.script, video_id=video_id,
                client=clients.get("image_client"),
                placeholder_gen=clients.get("placeholder_gen"),
            )
            result.image_paths = (
                [str(img.output_path) for img in image_result.images] if image_result else []
            )
        except ImportError as exc:
            logger.error("image_gen module unavailable: %s", exc)
            result.failed_stages.append("images")

    if result.image_paths:
        try:
            from core.thumbnail_text import add_thumbnail_text
            hook_text = getattr(result.script, "hook", "") if result.script else ""
            result.thumbnail_path = _run_stage(
                "thumbnail", result, add_thumbnail_text,
                image_path=result.image_paths[0], text=hook_text,
            )
        except ImportError as exc:
            logger.error("thumbnail_text module unavailable: %s", exc)
            result.failed_stages.append("thumbnail")

    if result.image_paths:
        try:
            from core.video_effects import apply_effect
            effects_out_dir = str(settings.content_path / "clips" / f"video_{video_id}")
            result.effect_clip_paths = _run_stage(
                "effects", result, apply_effect,
                image_paths=result.image_paths, mode=channel.video_mode,
                output_dir=effects_out_dir,
                replicate_client=clients.get("replicate_client"),
            ) or []
        except ImportError as exc:
            logger.error("video_effects module unavailable: %s", exc)
            result.failed_stages.append("effects")

    if result.effect_clip_paths and result.voice_path:
        try:
            from core.video_assembler import assemble_video
            final_path = str(settings.content_path / "videos" / f"{video_id}.mp4")
            content_db.update_status(video_id, "ASSEMBLING")
            result.final_video_path = _run_stage(
                "assembly", result, assemble_video,
                clip_paths=result.effect_clip_paths,
                narration_path=result.voice_path,
                output_path=final_path,
                music_path=result.music_path if result.music_path != result.voice_path else None,
            )
            if result.script is not None:
                result.chapter_markers = _build_chapter_markers(result)
            if result.final_video_path:
                content_db.set_output_path(video_id, result.final_video_path)
        except ImportError as exc:
            logger.error("video_assembler module unavailable: %s", exc)
            result.failed_stages.append("assembly")
            raise

    if result.script is not None:
        try:
            from core.seo_optimizer import optimize_seo
            from core.script_writer import OpenAIChatClient
            # Real runs use the same shared OpenAI-compatible chat client as
            # script_writer. SEO metadata is required before upload (stage 10 is
            # gated on seo_result), so it must never be silently skipped.
            content_db.update_status(video_id, "OPTIMIZING")
            seo_client = clients.get("seo_chat_client") or OpenAIChatClient()
            result.seo_result = _run_stage(
                "seo", result, optimize_seo,
                client=seo_client, channel=channel,
                script=result.script.to_dict(),
                chapter_markers=result.chapter_markers,
            )
            if result.seo_result is not None:
                content_db.update_metadata(video_id, {
                    "seo": {
                        "title": result.seo_result.title,
                        "description": result.seo_result.description,
                        "tags": result.seo_result.tags,
                        "hashtags": result.seo_result.hashtags,
                        "pinned_comment": result.seo_result.pinned_comment,
                        "end_screen_topics": getattr(result.seo_result, "end_screen_topics", []),
                    }
                })
        except ImportError as exc:
            logger.error("seo_optimizer module unavailable: %s", exc)
            result.failed_stages.append("seo")

    if result.final_video_path and settings.generate_shorts:
        try:
            from core.shorts_gen import generate_shorts
            shorts_out_dir = str(settings.content_path / "shorts" / f"video_{video_id}")
            result.shorts_paths = _run_stage(
                "shorts", result, generate_shorts,
                source_video_path=result.final_video_path, output_dir=shorts_out_dir,
                count=clients.get("shorts_count", settings.shorts_per_video),
            ) or []
        except ImportError as exc:
            logger.error("shorts_gen module unavailable: %s", exc)
            result.failed_stages.append("shorts")

    if result.final_video_path and result.seo_result is not None:
        upload_mode = config.get("upload_mode", settings.upload_mode)
        try:
            content_db.update_status(video_id, "UPLOADING")
            if upload_mode == "youtube_api":
                from core.uploader import upload_video
                result.upload_result = _run_stage(
                    "upload", result, upload_video,
                    video_path=result.final_video_path, seo_result=result.seo_result,
                    channel=channel, thumbnail_path=result.thumbnail_path,
                )
            else:
                from core.pipedream_uploader import dispatch_upload
                result.upload_result = _run_stage(
                    "upload", result, dispatch_upload,
                    mode=upload_mode, video_path=result.final_video_path,
                    seo_result=result.seo_result, channel=channel,
                    thumbnail_path=result.thumbnail_path,
                    webhook_url=config.get("webhook_url") or settings.pipedream_webhook_url,
                )
        except ImportError as exc:
            logger.error("uploader module unavailable: %s", exc)
            result.failed_stages.append("upload")

    if result.success:
        content_db.update_status(video_id, "PUBLISHED")
        logger.info("Pipeline completed successfully for topic: %s", topic)
    else:
        _mark_failed(result, "; ".join(result.failed_stages))
        logger.warning("Pipeline completed with failures in stages: %s", result.failed_stages)

    return result


if __name__ == "__main__":
    import sys
    topic_arg = sys.argv[1] if len(sys.argv) > 1 else "default topic"
    channel_arg = sys.argv[2] if len(sys.argv) > 2 else "finance"
    run_pipeline(topic_arg, channel_arg)
