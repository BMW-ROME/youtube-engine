"""
core/video_effects.py

Stage 6 of the content pipeline: Video Effects.

Applies one of four visual treatment modes to a sequence of scene images,
turning static images into short video clips ready for final assembly by
video_assembler.py (Stage 7). Matches the resilience architecture in
README.md: 'animated' and 'ai_video' both depend on Replicate; if the
'replicate' package is missing or REPLICATE_API_TOKEN is unset, both
modes fall back automatically to 'kenburns' rather than raising.

Modes (per README):
    kenburns  - free, local, FFmpeg zoompan (default / fallback target)
    sketch    - free, local, FFmpeg edge-detect style filter
    animated  - $, Replicate image-to-video model
    ai_video  - $$, Replicate higher-fidelity image-to-video model

Public API:
    apply_effect(image_paths, mode, output_dir, duration_per_image=4.0) -> list[str]

Design notes:
- FFmpeg calls are wrapped in subprocess with resilient error handling --
  a single failed image never crashes the whole batch; it's logged and
  skipped so the pipeline can continue with the remaining scenes.
- Replicate client is dependency-injected via a thin protocol so this
  module is fully unit-testable without any network calls or API cost.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional, Protocol

logger = logging.getLogger(__name__)

try:
    import replicate as _replicate_sdk
    REPLICATE_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised via REPLICATE_AVAILABLE flag
    REPLICATE_AVAILABLE = False
    logger.warning("replicate package not installed - animated/ai_video modes will fall back to kenburns.")

VALID_MODES = ("kenburns", "sketch", "animated", "ai_video")
_PAID_MODES = ("animated", "ai_video")


class EffectError(Exception):
    """Raised only for programmer errors (bad mode name). Runtime/API
    failures are handled internally via fallback, never raised."""


class ReplicateClient(Protocol):
    """Minimal interface video_effects.py needs from a Replicate client,
    so tests can inject a fake implementation with zero API cost."""

    def run(self, model: str, input: dict) -> str:
        ...


def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def _kenburns_clip(image_path: str, output_path: str, duration: float) -> bool:
    """Slow zoom+pan effect on a still image using FFmpeg's zoompan filter."""
    if not _has_ffmpeg():
        logger.error("[video_effects] ffmpeg not found on PATH - cannot render kenburns clip.")
        return False

    fps = 30
    frames = int(duration * fps)
    filter_str = (
        f"scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,"
        f"zoompan=z='min(zoom+0.0015,1.15)':"
        f"d={frames}:s=1920x1080:fps={fps}"
    )
    cmd = [
        "ffmpeg", "-y", "-loop", "1", "-i", image_path,
        "-vf", filter_str, "-t", str(duration),
        "-pix_fmt", "yuv420p", output_path,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError as exc:
        logger.error("[video_effects] kenburns ffmpeg failed for %s: %s", image_path, exc.stderr)
        return False


def _sketch_clip(image_path: str, output_path: str, duration: float) -> bool:
    """Pencil-sketch style clip using FFmpeg edge-detect + grayscale filters."""
    if not _has_ffmpeg():
        logger.error("[video_effects] ffmpeg not found on PATH - cannot render sketch clip.")
        return False

    filter_str = (
        "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,"
        "edgedetect=mode=colormix:high=0.4,format=gray"
    )
    cmd = [
        "ffmpeg", "-y", "-loop", "1", "-i", image_path,
        "-vf", filter_str, "-t", str(duration),
        "-pix_fmt", "yuv420p", output_path,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError as exc:
        logger.error("[video_effects] sketch ffmpeg failed for %s: %s", image_path, exc.stderr)
        return False


def _replicate_clip(
    image_path: str,
    output_path: str,
    model: str,
    client: Optional[ReplicateClient],
) -> bool:
    """Run an image-to-video Replicate model and download the result.

    Returns False on ANY failure so the caller can fall back to kenburns --
    this stage must never crash the pipeline over a paid API hiccup.
    """
    if client is None or not REPLICATE_AVAILABLE:
        return False

    try:
        with open(image_path, "rb") as f:
            result_url = client.run(model, input={"image": f})

        import urllib.request
        urllib.request.urlretrieve(result_url, output_path)
        return True
    except Exception as exc:  # noqa: BLE001 - resilience: any failure -> fallback
        logger.warning("[video_effects] Replicate model %s failed, falling back to kenburns: %s", model, exc)
        return False


def apply_effect(
    image_paths: List[str],
    mode: str,
    output_dir: str,
    duration_per_image: float = 4.0,
    replicate_client: Optional[ReplicateClient] = None,
) -> List[str]:
    """
    Convert a list of still scene images into video clips using the given mode.

    Args:
        image_paths: ordered list of scene image file paths.
        mode: one of VALID_MODES ('kenburns', 'sketch', 'animated', 'ai_video').
        output_dir: directory to write the resulting .mp4 clips into.
        duration_per_image: seconds each clip should last.
        replicate_client: injected client for 'animated'/'ai_video' modes,
            used only for testing or to supply a real replicate.Client().

    Returns:
        List of output clip paths, in the same order as image_paths. Any
        image that fails to render (in any mode) is skipped and omitted
        from the returned list rather than raising.
    """
    if mode not in VALID_MODES:
        raise EffectError(f"Unknown video effect mode: {mode!r}. Valid modes: {VALID_MODES}")

    effective_mode = mode
    if mode in _PAID_MODES and (replicate_client is None or not REPLICATE_AVAILABLE):
        logger.info("[video_effects] Mode '%s' unavailable (no client/package) - falling back to kenburns.", mode)
        effective_mode = "kenburns"

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    replicate_models = {
        "animated": "stability-ai/stable-video-diffusion",
        "ai_video": "minimax/video-01",
    }

    clips: List[str] = []
    for i, image_path in enumerate(image_paths):
        output_path = str(out_dir / f"scene_{i:03d}.mp4")
        success = False

        if effective_mode == "kenburns":
            success = _kenburns_clip(image_path, output_path, duration_per_image)
        elif effective_mode == "sketch":
            success = _sketch_clip(image_path, output_path, duration_per_image)
        elif effective_mode in _PAID_MODES:
            model = replicate_models[effective_mode]
            success = _replicate_clip(image_path, output_path, model, replicate_client)
            if not success:
                # Per-image fallback: this one image failed via Replicate,
                # still render it with kenburns so the video isn't short a scene.
                success = _kenburns_clip(image_path, output_path, duration_per_image)

        if success:
            clips.append(output_path)
        else:
            logger.error("[video_effects] Skipping scene %d (%s) - all render attempts failed.", i, image_path)

    logger.info("[video_effects] Rendered %d/%d clips using mode '%s'.", len(clips), len(image_paths), effective_mode)
    return clips
