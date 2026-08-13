"""
Stage 2 of the content pipeline: voice narration.

Converts each scene's narration text into audio, then concatenates all
scenes into one final voice track for the video. Two engines are supported:

    edge_tts    - free Microsoft neural voices (default for all channels)
    elevenlabs  - cloned voice (used for the Thee3lite Speaks channel)

Per the Resilience Architecture in README.md: if a channel is configured for
ElevenLabs but no API key/voice ID is set, this module falls back to Edge-TTS
automatically rather than failing the whole pipeline.

Both the synthesis engine and the audio concatenation step are injected via
Protocols so this module can be fully unit-tested without a network call,
an ElevenLabs account, or even the `ffmpeg` binary being installed.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from config.channels import ChannelConfig
from config.settings import settings
from core import content_db
from core.script_writer import Script

logger = logging.getLogger(__name__)

MAX_RETRIES = 2


class VoiceGenerationError(Exception):
    """Raised when voice synthesis or concatenation fails after retries."""


class Synthesizer(Protocol):
    """Converts one block of text into an audio file at output_path."""

    def synthesize(self, text: str, voice_id: str, output_path: Path) -> None:
        ...


class AudioConcatenator(Protocol):
    """Joins multiple audio files, in order, into a single output file."""

    def concatenate(self, input_paths: list[Path], output_path: Path) -> None:
        ...


class EdgeTTSSynthesizer:
    """Free Microsoft neural voices via the edge-tts library."""

    def synthesize(self, text: str, voice_id: str, output_path: Path) -> None:
        import edge_tts

        async def _run():
            communicate = edge_tts.Communicate(text, voice_id)
            await communicate.save(str(output_path))

        asyncio.run(_run())


class ElevenLabsSynthesizer:
    """Cloned voice via the ElevenLabs API. Only constructed when
    settings.has_elevenlabs is True - see get_synthesizer()."""

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or settings.elevenlabs_api_key

    def synthesize(self, text: str, voice_id: str, output_path: Path) -> None:
        from elevenlabs.client import ElevenLabs

        client = ElevenLabs(api_key=self._api_key)
        audio = client.text_to_speech.convert(
            voice_id=voice_id,
            text=text,
            model_id=settings.elevenlabs_model_id,
            voice_settings={
                "stability": settings.elevenlabs_stability,
                "similarity_boost": settings.elevenlabs_similarity,
                "style": settings.elevenlabs_style,
                "use_speaker_boost": settings.elevenlabs_boost,
            },
        )
        with open(output_path, "wb") as f:
            for chunk in audio:
                f.write(chunk)


class FFmpegConcatenator:
    """Joins audio segments using ffmpeg's concat demuxer. Requires ffmpeg
    on PATH (see README Prerequisites)."""

    def concatenate(self, input_paths: list[Path], output_path: Path) -> None:
        import subprocess
        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as list_file:
            for p in input_paths:
                list_file.write(f"file '{p.resolve()}'\n")
            list_path = list_file.name

        try:
            result = subprocess.run(
                [
                    "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                    "-i", list_path, "-c", "copy", str(output_path),
                ],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                raise VoiceGenerationError(f"ffmpeg concat failed: {result.stderr}")
        finally:
            Path(list_path).unlink(missing_ok=True)


def get_synthesizer(channel: ChannelConfig) -> Synthesizer:
    """Pick the synthesis engine for a channel, honoring the graceful
    fallback rule: ElevenLabs configured but unavailable -> Edge-TTS."""
    if channel.voice_engine == "elevenlabs":
        if settings.has_elevenlabs:
            try:
                import elevenlabs  # noqa: F401
                return ElevenLabsSynthesizer()
            except ImportError:
                logger.warning(
                    "voice_gen: elevenlabs package not installed for channel %r, "
                    "falling back to Edge-TTS", channel.codename,
                )
        else:
            logger.warning(
                "voice_gen: channel %r configured for elevenlabs but no API key/voice "
                "ID set, falling back to Edge-TTS", channel.codename,
            )
    return EdgeTTSSynthesizer()


def _resolve_voice_id(channel: ChannelConfig, synthesizer: Synthesizer) -> str:
    if isinstance(synthesizer, ElevenLabsSynthesizer):
        return settings.elevenlabs_voice_id or channel.voice_id
    return channel.voice_id


@dataclass
class VoiceResult:
    output_path: Path
    scene_count: int


def generate_voice(
    channel: ChannelConfig,
    script: Script,
    video_id: int | None = None,
    synthesizer: Synthesizer | None = None,
    concatenator: AudioConcatenator | None = None,
) -> VoiceResult:
    """Synthesize narration for every scene in `script`, concatenate into
    one track, and return the final audio path. Persists voice_path into
    content_db metadata and updates status on success/failure."""

    active_synth = synthesizer or get_synthesizer(channel)
    active_concat = concatenator or FFmpegConcatenator()
    voice_id = _resolve_voice_id(channel, active_synth)

    if video_id is not None:
        content_db.update_status(video_id, "VOICING")

    work_dir = settings.content_path / "tmp" / f"video_{video_id or 'preview'}"
    work_dir.mkdir(parents=True, exist_ok=True)
    audio_dir = settings.content_path / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    final_path = audio_dir / f"{video_id or 'preview'}.mp3"

    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 2):
        try:
            segment_paths: list[Path] = []
            for i, scene in enumerate(script.scenes):
                seg_path = work_dir / f"scene_{i:02d}.mp3"
                active_synth.synthesize(scene.narration, voice_id, seg_path)
                segment_paths.append(seg_path)

            active_concat.concatenate(segment_paths, final_path)

            if video_id is not None:
                content_db.update_metadata(video_id, {"voice_path": str(final_path)})

            return VoiceResult(output_path=final_path, scene_count=len(segment_paths))

        except Exception as exc:  # noqa: BLE001 - synthesis/concat errors vary by engine
            last_error = exc
            logger.warning(
                "voice_gen: attempt %d/%d failed for video_id=%s: %s",
                attempt, MAX_RETRIES + 1, video_id, exc,
            )

    if video_id is not None:
        content_db.update_status(video_id, "FAILED", error_message=str(last_error))
        content_db.increment_retry(video_id)

    raise VoiceGenerationError(
        f"Failed to generate voice track after {MAX_RETRIES + 1} attempts: {last_error}"
    )
