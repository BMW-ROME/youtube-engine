"""
core/video_assembler.py

Stage 7 of the content pipeline: Final Assembly.

Stitches per-scene video clips (from video_effects.py), the narration
track (from voice_gen.py), and optionally a mixed background-music track
(from music_mixer.py) into one final MP4, ready for SEO metadata
(seo_optimizer.py) and upload (uploader.py). Also exposes a chapter-marker
helper used to build YouTube chapter timestamps from scene durations.

Output spec (per README): 1080p H.264 + AAC audio, faststart flag for
fast web playback, crossfade transitions between scenes.

Public API:
    assemble_video(clip_paths, narration_path, output_path,
                    music_path=None, transition_duration=0.5) -> str | None
    build_chapter_markers(scene_durations, scene_titles) -> list[dict]

Design notes:
- Every FFmpeg call is wrapped so a failure is logged and returns None
  rather than raising -- matches the resilience architecture in README.md.
- Crossfade uses FFmpeg's xfade filter, chained across N clips via a
  dynamically built filter_complex graph.
- If there is only one clip, no crossfade graph is needed -- it's
  concatenated directly with the narration/music.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional, Dict

logger = logging.getLogger(__name__)


def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def _probe_duration(path: str) -> float:
    """Return media duration in seconds using ffprobe. Returns 0.0 on failure."""
    if shutil.which("ffprobe") is None:
        logger.warning("[video_assembler] ffprobe not found - duration probing disabled.")
        return 0.0
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path,
    ]
    try:
        out = subprocess.run(cmd, check=True, capture_output=True, text=True)
        return float(out.stdout.strip())
    except (subprocess.CalledProcessError, ValueError) as exc:
        logger.warning("[video_assembler] ffprobe failed for %s: %s", path, exc)
        return 0.0


def _build_crossfade_filter(clip_paths: List[str], transition_duration: float) -> tuple:
    """
    Build an ffmpeg filter_complex graph chaining xfade across all clips.

    Returns (filter_complex_string, final_output_label).
    """
    durations = [_probe_duration(p) for p in clip_paths]
    filters = []
    prev_label = "0:v"
    running_offset = durations[0] if durations[0] else 4.0

    for i in range(1, len(clip_paths)):
        this_label = f"v{i}"
        offset = max(running_offset - transition_duration, 0)
        filters.append(
            f"[{prev_label}][{i}:v]xfade=transition=fade:"
            f"duration={transition_duration}:offset={offset}[{this_label}]"
        )
        prev_label = this_label
        next_dur = durations[i] if durations[i] else 4.0
        running_offset = offset + next_dur

    return ";".join(filters), prev_label


def assemble_video(
    clip_paths: List[str],
    narration_path: str,
    output_path: str,
    music_path: Optional[str] = None,
    transition_duration: float = 0.5,
) -> Optional[str]:
    """
    Combine scene clips + narration (+ optional music) into the final video.

    Args:
        clip_paths: ordered list of per-scene .mp4 clips from video_effects.py.
        narration_path: path to the final narration audio track.
        output_path: where to save the assembled .mp4.
        music_path: optional pre-mixed narration+music track from
            music_mixer.py. If provided, this is used as the audio track
            INSTEAD of narration_path (music_mixer already mixed them).
        transition_duration: crossfade duration in seconds between scenes.

    Returns:
        output_path on success, or None if assembly failed (missing
        ffmpeg, no clips, or an ffmpeg error) -- pipeline continues
        without crashing per the resilience architecture.
    """
    if not _has_ffmpeg():
        logger.error("[video_assembler] ffmpeg not found on PATH - cannot assemble video.")
        return None

    if not clip_paths:
        logger.error("[video_assembler] No clips provided - cannot assemble video.")
        return None

    audio_path = music_path if music_path else narration_path
    if not Path(audio_path).exists():
        logger.error("[video_assembler] Audio track not found: %s", audio_path)
        return None

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    inputs = []
    for clip in clip_paths:
        inputs += ["-i", clip]
    inputs += ["-i", audio_path]
    audio_input_index = len(clip_paths)

    if len(clip_paths) == 1:
        # No crossfade graph needed for a single clip.
        cmd = [
            "ffmpeg", "-y", *inputs,
            "-map", "0:v", "-map", f"{audio_input_index}:a",
            "-c:v", "libx264", "-c:a", "aac",
            "-shortest", "-movflags", "+faststart",
            output_path,
        ]
    else:
        filter_complex, final_label = _build_crossfade_filter(clip_paths, transition_duration)
        cmd = [
            "ffmpeg", "-y", *inputs,
            "-filter_complex", filter_complex,
            "-map", f"[{final_label}]", "-map", f"{audio_input_index}:a",
            "-c:v", "libx264", "-c:a", "aac",
            "-shortest", "-movflags", "+faststart",
            output_path,
        ]

    try:
        subprocess.run(cmd, check=True, capture_output=True)
        logger.info("[video_assembler] Assembled final video -> %s", output_path)
        return output_path
    except subprocess.CalledProcessError as exc:
        logger.error("[video_assembler] ffmpeg assembly failed: %s", exc.stderr)
        return None


def build_chapter_markers(
    scene_durations: List[float],
    scene_titles: List[str],
) -> List[Dict[str, object]]:
    """
    Build YouTube chapter markers from per-scene durations and titles.

    YouTube requires the first chapter to start at 00:00 and chapters to
    be at least 10 seconds apart; this helper does not enforce the latter
    (caller/seo_optimizer.py is responsible for final formatting) but does
    guarantee the first timestamp is always 0.

    Args:
        scene_durations: seconds per scene, in order.
        scene_titles: matching titles per scene (same length as durations).

    Returns:
        List of {"timestamp_seconds": float, "title": str} dicts.
    """
    if len(scene_durations) != len(scene_titles):
        logger.warning(
            "[video_assembler] scene_durations (%d) and scene_titles (%d) length mismatch - truncating to shortest.",
            len(scene_durations), len(scene_titles),
        )

    n = min(len(scene_durations), len(scene_titles))
    markers = []
    elapsed = 0.0

    for i in range(n):
        markers.append({"timestamp_seconds": elapsed, "title": scene_titles[i]})
        elapsed += scene_durations[i]

    return markers
