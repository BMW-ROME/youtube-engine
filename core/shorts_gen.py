"""
core/shorts_gen.py

Stage 9 of the content pipeline: YouTube Shorts Generator.

Extracts SHORTS_PER_VIDEO (default 3) vertical (9:16) clips from the
highest-retention moments of the assembled long-form video, per README
Stage 9 spec (~$0.20/video extra, gated behind GENERATE_SHORTS=true).

Since this rebuild has no analytics/retention-tracking service yet, moment
selection uses a heuristic: prefer scene boundaries near the start (hook),
middle, and a strong closing beat, spread evenly across the runtime so
clips don't overlap. This keeps the module fully self-contained and
testable without any external dependency, matching the fallback-first
architecture used everywhere else in this codebase.

Public API:
    generate_shorts(source_video_path, output_dir, video_duration=None,
                     count=3, short_duration=30.0) -> list[str]

Design notes:
- Center-crop 16:9 source to 9:16 vertical via FFmpeg crop+scale filter.
- Every FFmpeg call is wrapped so a failure is logged and skipped rather
  than raising -- one failed short never blocks the others or the caller.
- Reuses _has_ffmpeg/_probe_duration patterns from video_assembler.py.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def _probe_duration(path: str) -> float:
    """Return media duration in seconds using ffprobe. Returns 0.0 on failure."""
    if shutil.which("ffprobe") is None:
        logger.warning("[shorts_gen] ffprobe not found - duration probing disabled.")
        return 0.0
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path,
    ]
    try:
        out = subprocess.run(cmd, check=True, capture_output=True, text=True)
        return float(out.stdout.strip())
    except (subprocess.CalledProcessError, ValueError) as exc:
        logger.warning("[shorts_gen] ffprobe failed for %s: %s", path, exc)
        return 0.0


def _pick_start_times(
    video_duration: float,
    count: int,
    short_duration: float,
) -> List[float]:
    """
    Heuristic retention-moment picker: spreads `count` non-overlapping
    windows across the video, biased toward the hook (early), a middle
    beat, and the closing beat -- without any analytics dependency.
    """
    if video_duration <= 0:
        return []
    usable = max(video_duration - short_duration, 0.0)
    if usable <= 0:
        # Video shorter than one short -- just take from the top.
        return [0.0]
    if count <= 1:
        return [0.0]
    # Evenly spaced fractions along the usable range, e.g. for count=3:
    # 0%, 50%, 100% of usable range (hook, middle, closer).
    starts = []
    for i in range(count):
        frac = i / (count - 1)
        starts.append(round(usable * frac, 2))
    return starts


def _extract_vertical_clip(
    source_video_path: str,
    start_time: float,
    duration: float,
    output_path: str,
) -> Optional[str]:
    """
    Cut a `duration`-second clip starting at `start_time` from the source
    and center-crop/scale it to 1080x1920 (9:16) vertical for Shorts.
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    # crop to 9:16 from the center of a 16:9 source, then scale to 1080x1920.
    vf = (
        "crop=ih*9/16:ih,scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920"
    )
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_time),
        "-i", source_video_path,
        "-t", str(duration),
        "-vf", vf,
        "-c:v", "libx264", "-c:a", "aac",
        "-movflags", "+faststart",
        output_path,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        logger.info("[shorts_gen] Extracted short -> %s (start=%.2fs)", output_path, start_time)
        return output_path
    except subprocess.CalledProcessError as exc:
        logger.error("[shorts_gen] ffmpeg extraction failed at %.2fs: %s", start_time, exc.stderr)
        return None


def generate_shorts(
    source_video_path: str,
    output_dir: str,
    video_duration: Optional[float] = None,
    count: int = 3,
    short_duration: float = 30.0,
) -> List[str]:
    """
    Generate up to `count` vertical Shorts clips from the assembled video.

    Args:
        source_video_path: path to the final assembled long-form MP4
            (output of video_assembler.assemble_video).
        output_dir: directory to write short_1.mp4, short_2.mp4, etc.
        video_duration: pre-known duration in seconds; probed via ffprobe
            if not provided.
        count: number of shorts to generate (SHORTS_PER_VIDEO, default 3).
        short_duration: length of each short in seconds.

    Returns:
        List of output paths for successfully generated shorts. Never
        raises -- a total failure returns an empty list so the pipeline
        continues (Shorts are a bonus feature, not a blocker per README's
        resilience architecture).
    """
    if not _has_ffmpeg():
        logger.error("[shorts_gen] ffmpeg not found on PATH - cannot generate shorts.")
        return []
    if not Path(source_video_path).exists():
        logger.error("[shorts_gen] Source video not found: %s", source_video_path)
        return []
    if count <= 0:
        return []

    duration = video_duration if video_duration else _probe_duration(source_video_path)
    if duration <= 0:
        logger.error("[shorts_gen] Could not determine video duration - skipping shorts.")
        return []

    starts = _pick_start_times(duration, count, short_duration)
    clamped_duration = min(short_duration, duration)

    results: List[str] = []
    for i, start in enumerate(starts, start=1):
        out_path = str(Path(output_dir) / f"short_{i}.mp4")
        clip = _extract_vertical_clip(source_video_path, start, clamped_duration, out_path)
        if clip:
            results.append(clip)
        else:
            logger.warning("[shorts_gen] Short %d/%d failed - skipping, continuing with rest.", i, len(starts))

    logger.info("[shorts_gen] Generated %d/%d shorts for %s", len(results), len(starts), source_video_path)
    return results
