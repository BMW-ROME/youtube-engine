"""
Stage 3 of the content pipeline: background music mixing.

Mixes ambient background music under the narration track using FFmpeg's
`amix` filter, at a configurable low volume so it never competes with the
voice. Per the Resilience Architecture in README.md: if BACKGROUND_MUSIC is
disabled, or no music file is found for the channel's niche, this stage is
silently skipped rather than failing the pipeline — the voice track just
becomes the final audio.

The actual mixing subprocess is injected via a Protocol so this module is
fully unit-testable without ffmpeg installed or real audio files on disk.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from config.channels import ChannelConfig
from config.settings import settings
from core import content_db

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
MUSIC_DIR = Path("assets/music")

# Maps channel niche -> subfolder under assets/music/ so each niche gets an
# appropriately-moody track (e.g. dark ambient for Stories, upbeat for MMO).
NICHE_MUSIC_FOLDERS: dict[str, str] = {
    "Finance": "corporate",
    "Make Money Online": "upbeat",
    "Technology": "ambient_tech",
    "Viral/News": "news",
    "Personal Brand": "warm",
    "Legal/Crime": "dramatic",
    "Dark Stories": "dark_ambient",
}


class MusicMixError(Exception):
    """Raised when mixing fails after retries. Never raised for the
    'no music available' case — that's a graceful skip, not an error."""


class AudioMixer(Protocol):
    """Mixes a background music track under a voice track at low volume."""

    def mix(
        self, voice_path: Path, music_path: Path, output_path: Path, music_volume: float
    ) -> None:
        ...


class FFmpegAudioMixer:
    """Real implementation using ffmpeg's amix filter. Requires ffmpeg on PATH."""

    def mix(
        self, voice_path: Path, music_path: Path, output_path: Path, music_volume: float
    ) -> None:
        import subprocess

        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(voice_path),
                "-stream_loop", "-1", "-i", str(music_path),
                "-filter_complex",
                f"[1:a]volume={music_volume}[music];"
                f"[0:a][music]amix=inputs=2:duration=first:dropout_transition=2[out]",
                "-map", "[out]",
                "-shortest",
                str(output_path),
            ],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise MusicMixError(f"ffmpeg amix failed: {result.stderr}")


def _pick_music_file(channel: ChannelConfig, music_root: Path) -> Path | None:
    """Pick a random track from the channel's niche folder. Returns None if
    the folder doesn't exist or is empty — triggers a graceful skip."""
    folder_name = NICHE_MUSIC_FOLDERS.get(channel.niche)
    if folder_name is None:
        logger.info("music_mixer: no music folder mapped for niche %r, skipping", channel.niche)
        return None

    folder = music_root / folder_name
    if not folder.is_dir():
        logger.info("music_mixer: music folder %s does not exist, skipping", folder)
        return None

    tracks = [p for p in folder.glob("*.mp3")] + [p for p in folder.glob("*.wav")]
    if not tracks:
        logger.info("music_mixer: no tracks found in %s, skipping", folder)
        return None

    return random.choice(tracks)


@dataclass
class MusicMixResult:
    output_path: Path
    music_used: bool
    music_track: str | None = None


def mix_music(
    channel: ChannelConfig,
    voice_path: Path,
    video_id: int | None = None,
    mixer: AudioMixer | None = None,
    music_root: Path | None = None,
) -> MusicMixResult:
    """Mix background music under the voice track for `channel`, if enabled
    and a track is available. Always succeeds from the caller's perspective:
    either returns a mixed track, or gracefully returns the original voice
    track unchanged with music_used=False. Only raises MusicMixError if
    mixing was attempted but the ffmpeg process itself failed after retries.
    """
    if video_id is not None:
        content_db.update_status(video_id, "MUSIC")

    if not settings.background_music:
        logger.info("music_mixer: BACKGROUND_MUSIC disabled, skipping for video_id=%s", video_id)
        return MusicMixResult(output_path=voice_path, music_used=False)

    root = music_root or MUSIC_DIR
    music_path = _pick_music_file(channel, root)
    if music_path is None:
        return MusicMixResult(output_path=voice_path, music_used=False)

    active_mixer = mixer or FFmpegAudioMixer()
    output_dir = settings.content_path / "audio"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{video_id or 'preview'}_mixed.mp3"

    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 2):
        try:
            active_mixer.mix(voice_path, music_path, output_path, music_volume=0.12)

            if video_id is not None:
                content_db.update_metadata(video_id, {
                    "music_path": str(output_path),
                    "music_track": music_path.name,
                })

            return MusicMixResult(
                output_path=output_path, music_used=True, music_track=music_path.name
            )

        except Exception as exc:  # noqa: BLE001 - ffmpeg errors vary
            last_error = exc
            logger.warning(
                "music_mixer: attempt %d/%d failed for video_id=%s: %s",
                attempt, MAX_RETRIES + 1, video_id, exc,
            )

    # Mixing was attempted and failed every time — degrade gracefully to the
    # unmixed voice track rather than failing the whole pipeline over music.
    logger.error(
        "music_mixer: giving up after %d attempts for video_id=%s (%s), "
        "falling back to voice-only audio",
        MAX_RETRIES + 1, video_id, last_error,
    )
    if video_id is not None:
        content_db.update_metadata(video_id, {"music_mix_error": str(last_error)})

    return MusicMixResult(output_path=voice_path, music_used=False)
