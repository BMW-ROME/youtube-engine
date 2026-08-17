"""
Stage 2 of the content pipeline: voice narration.

Converts each scene's narration text into audio, then concatenates all
scenes into one final voice track for the video. Two engines are supported:

    edge_tts     - free Microsoft neural voices (default for all channels)
    chatterbox   - local, open-source (MIT) zero-shot voice cloning via
                   Resemble AI's Chatterbox TTS model (used for the
                   Thee3lite Speaks channel)

MIGRATION (2026-08-17): ElevenLabs replaced with Chatterbox per decision
made jointly with the marketing-ops/lead-gen agent. Chatterbox is local-first
(runs on your own GPU/CPU, no API key, no per-character cost, MIT license),
matching the local-first infrastructure preference used throughout this
project (Ollama, etc.) instead of paid cloud APIs. Chatterbox does zero-shot
voice cloning directly from a single reference audio clip at generation
time -- there's no separate "upload and train" step like ElevenLabs had, so
voice_clone.py's job changed from "call a remote API to create a voice_id"
to "validate and resolve a local reference audio file path."

Per the Resilience Architecture in README.md: if a channel is configured
for Chatterbox but the chatterbox-tts package isn't installed, no GPU is
available, or the reference audio file is missing, this module falls back
to Edge-TTS automatically rather than failing the whole pipeline.

Both the synthesis engine and the audio concatenation step are injected via
Protocols so this module can be fully unit-tested without a network call,
a GPU, or even the `ffmpeg` binary being installed.
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


class ChatterboxSynthesizer:
    """Local, open-source (MIT) zero-shot voice cloning via Resemble AI's
    Chatterbox TTS. Requires the `chatterbox-tts` package and a local
    GPU/CPU capable of running the model (500M-parameter backbone).

    `voice_id` here is actually a filesystem path to the reference audio
    clip used for zero-shot cloning (Chatterbox's "audio_prompt_path"),
    NOT a remote API voice_id like ElevenLabs used -- see
    core.voice_clone.resolve_reference_clip() for how this path is
    validated/resolved from settings.chatterbox_voice_sample_path.

    The model is loaded lazily and cached on the instance so repeated
    synthesize() calls within one voice_gen run don't reload the model
    from disk every scene.
    """

    def __init__(self, device: str | None = None):
        self._device = device or settings.chatterbox_device
        self._model = None

    def _get_model(self):
        if self._model is None:
            from chatterbox.tts import ChatterboxTTS
            self._model = ChatterboxTTS.from_pretrained(device=self._device)
        return self._model

    def synthesize(self, text: str, voice_id: str, output_path: Path) -> None:
        import torchaudio as ta

        model = self._get_model()
        wav = model.generate(
            text,
            audio_prompt_path=voice_id,
            exaggeration=settings.chatterbox_exaggeration,
            cfg_weight=settings.chatterbox_cfg_weight,
        )
        ta.save(str(output_path), wav, model.sr)


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
    fallback rule: Chatterbox configured but unavailable (package missing,
    no GPU, or reference clip missing) -> Edge-TTS."""
    if channel.voice_engine == "chatterbox":
        try:
            import chatterbox  # noqa: F401
        except ImportError:
            logger.warning(
                "voice_gen: chatterbox-tts package not installed for channel %r, "
                "falling back to Edge-TTS", channel.codename,
            )
            return EdgeTTSSynthesizer()

        from core.voice_clone import resolve_reference_clip, VoiceCloneError
        try:
            resolve_reference_clip(channel)
        except VoiceCloneError as exc:
            logger.warning(
                "voice_gen: channel %r configured for chatterbox but reference "
                "clip unavailable (%s), falling back to Edge-TTS", channel.codename, exc,
            )
            return EdgeTTSSynthesizer()

        return ChatterboxSynthesizer()
    return EdgeTTSSynthesizer()


def _resolve_voice_id(channel: ChannelConfig, synthesizer: Synthesizer) -> str:
    if isinstance(synthesizer, ChatterboxSynthesizer):
        from core.voice_clone import resolve_reference_clip
        return str(resolve_reference_clip(channel))
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
