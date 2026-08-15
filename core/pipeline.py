"""
core/pipeline.py

Master orchestration module for the YouTube automation engine.

Chains together all 10 pipeline stages defined in README.md:
  1. Script generation (script_writer.py)
  2. Voice synthesis (voice_gen.py)
  3. Music selection (music_selector.py)
  4. Image/B-roll sourcing (image_sourcer.py)
  5. Thumbnail generation (thumbnail_gen.py)
  6. Visual effects (effects.py)
  7. Video assembly (video_assembler.py)
  8. SEO optimization (seo_optimizer.py)
  9. Shorts clipping (shorts_generator.py)
  10. Upload to YouTube (uploader.py)

Resilience contract:
  - Every stage is wrapped in try/except.
  - A failed stage logs the error and returns None instead of raising,
    unless the stage is marked as REQUIRED, in which case the pipeline
    aborts gracefully and reports which stage failed.
  - Partial results are preserved in the PipelineResult object so a
    failed run can be inspected or resumed manually.
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("pipeline")


@dataclass
class PipelineResult:
    """Holds the output of each stage plus overall success state."""

    topic: str
    script: Optional[Dict[str, Any]] = None
    voice_audio_path: Optional[str] = None
    music_track_path: Optional[str] = None
    images: Optional[list] = None
    thumbnail_path: Optional[str] = None
    effects_applied: Optional[list] = None
    final_video_path: Optional[str] = None
    seo_metadata: Optional[Dict[str, Any]] = None
    shorts_paths: Optional[list] = None
    upload_result: Optional[Dict[str, Any]] = None
    failed_stages: list = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.failed_stages) == 0


REQUIRED_STAGES = {"script", "assembly"}


def _run_stage(name: str, func, result: PipelineResult, *args, **kwargs):
    """Run a single pipeline stage with resilience/fallback handling."""
    try:
        logger.info("Starting stage: %s", name)
        output = func(*args, **kwargs)
        logger.info("Completed stage: %s", name)
        return output
    except Exception as exc:
        logger.error("Stage '%s' failed: %s", name, exc, exc_info=True)
        result.failed_stages.append(name)
        if name in REQUIRED_STAGES:
            logger.critical(
                "Required stage '%s' failed. Aborting pipeline.", name
            )
            raise
        return None


def run_pipeline(topic: str, config: Optional[Dict[str, Any]] = None) -> PipelineResult:
    """
    Execute the full 10-stage content pipeline for a given topic.

    Each stage is imported lazily inside the function so that a missing
    or broken module in one stage does not prevent the others (or the
    pipeline module itself) from being imported and used.
    """
    config = config or {}
    result = PipelineResult(topic=topic)

    try:
        from core.script_writer import generate_script
        result.script = _run_stage("script", generate_script, result, topic, config)
    except ImportError as exc:
        logger.error("script_writer module unavailable: %s", exc)
        result.failed_stages.append("script")

    try:
        from core.voice_gen import synthesize_voice
        if result.script:
            result.voice_audio_path = _run_stage(
                "voice", synthesize_voice, result, result.script, config
            )
    except ImportError as exc:
        logger.error("voice_gen module unavailable: %s", exc)
        result.failed_stages.append("voice")

    try:
        from core.music_selector import select_music
        result.music_track_path = _run_stage(
            "music", select_music, result, result.script, config
        )
    except ImportError as exc:
        logger.error("music_selector module unavailable: %s", exc)
        result.failed_stages.append("music")

    try:
        from core.image_sourcer import source_images
        result.images = _run_stage(
            "images", source_images, result, result.script, config
        )
    except ImportError as exc:
        logger.error("image_sourcer module unavailable: %s", exc)
        result.failed_stages.append("images")

    try:
        from core.thumbnail_gen import generate_thumbnail
        result.thumbnail_path = _run_stage(
            "thumbnail", generate_thumbnail, result, result.script, config
        )
    except ImportError as exc:
        logger.error("thumbnail_gen module unavailable: %s", exc)
        result.failed_stages.append("thumbnail")

    try:
        from core.effects import apply_effects
        result.effects_applied = _run_stage(
            "effects", apply_effects, result, result.images, config
        )
    except ImportError as exc:
        logger.error("effects module unavailable: %s", exc)
        result.failed_stages.append("effects")

    try:
        from core.video_assembler import assemble_video
        result.final_video_path = _run_stage(
            "assembly",
            assemble_video,
            result,
            result.voice_audio_path,
            result.music_track_path,
            result.images,
            config,
        )
    except ImportError as exc:
        logger.error("video_assembler module unavailable: %s", exc)
        result.failed_stages.append("assembly")

    try:
        from core.seo_optimizer import optimize_seo
        result.seo_metadata = _run_stage(
            "seo", optimize_seo, result, result.script, config
        )
    except ImportError as exc:
        logger.error("seo_optimizer module unavailable: %s", exc)
        result.failed_stages.append("seo")

    try:
        from core.shorts_generator import generate_shorts
        result.shorts_paths = _run_stage(
            "shorts", generate_shorts, result, result.final_video_path, config
        )
    except ImportError as exc:
        logger.error("shorts_generator module unavailable: %s", exc)
        result.failed_stages.append("shorts")

    try:
        from core.uploader import upload_video
        result.upload_result = _run_stage(
            "upload",
            upload_video,
            result,
            result.final_video_path,
            result.seo_metadata,
            config,
        )
    except ImportError as exc:
        logger.error("uploader module unavailable: %s", exc)
        result.failed_stages.append("upload")

    if result.success:
        logger.info("Pipeline completed successfully for topic: %s", topic)
    else:
        logger.warning(
            "Pipeline completed with failures in stages: %s", result.failed_stages
        )

    return result


if __name__ == "__main__":
    import sys

    topic_arg = sys.argv[1] if len(sys.argv) > 1 else "default topic"
    run_pipeline(topic_arg)
