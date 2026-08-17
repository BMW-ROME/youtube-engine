"""
Local voice reference setup for Chatterbox TTS (zero-shot voice cloning).

MIGRATION (2026-08-17): replaces the ElevenLabs Instant Voice Clone wizard.
Chatterbox does NOT have a remote "upload samples, get a voice_id back"
step like ElevenLabs did -- it clones a voice directly from a single
reference audio clip passed as `audio_prompt_path` at generation time
(see core/voice_gen.py's ChatterboxSynthesizer). So "cloning" here means:

    1. Validate the reference clip (exists, correct format, right length).
    2. Resolve which file path to use for a given channel (explicit
       channel override, else the global default reference clip).

There is no voice_id to persist to .env anymore -- the reference clip's
file path IS the "voice," and it's expected to live on local disk
(committed to the assets/ directory or referenced via .env, never
committed to git if it's a real personal voice sample).

This module never writes to .env or the filesystem itself (other than
reading) -- it has no file-IO side effects beyond validation, matching the
pattern from the original ElevenLabs version.
"""

from __future__ import annotations

import logging
from pathlib import Path

from config.channels import ChannelConfig
from config.settings import settings

logger = logging.getLogger(__name__)

# Chatterbox's own docs recommend keeping reference clips short and clean --
# roughly 5-40 seconds of clear, single-speaker audio with minimal
# background noise. These are soft guardrails, not hard model limits.
MIN_CLIP_SECONDS = 3.0
RECOMMENDED_MAX_CLIP_SECONDS = 40.0
ALLOWED_EXTENSIONS = {".wav", ".mp3", ".flac", ".m4a", ".ogg"}


class VoiceCloneError(Exception):
    """Raised when the reference clip is missing, invalid, or unusable."""


def _get_audio_duration_seconds(path: Path) -> float | None:
    """Best-effort duration probe via torchaudio, if available. Returns
    None (rather than raising) if torchaudio isn't installed or the file
    can't be read -- duration is a soft-warning check, not a hard gate,
    since Chatterbox itself is tolerant of a range of clip lengths."""
    try:
        import torchaudio as ta
        info = ta.info(str(path))
        return info.num_frames / info.sample_rate
    except Exception as exc:  # noqa: BLE001 - duration probing is best-effort
        logger.debug("voice_clone: could not probe duration for %s: %s", path, exc)
        return None


def validate_reference_clip(path: Path) -> None:
    """Raises VoiceCloneError if `path` isn't usable as a Chatterbox
    audio_prompt_path. Duration is only a soft warning (logged), not a
    hard failure, since Chatterbox tolerates a range of clip lengths."""
    if not path.exists():
        raise VoiceCloneError(f"Reference audio clip not found: {path}")
    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise VoiceCloneError(
            f"Unsupported audio format '{path.suffix}' for {path.name}. "
            f"Allowed: {sorted(ALLOWED_EXTENSIONS)}"
        )
    if path.stat().st_size == 0:
        raise VoiceCloneError(f"Reference audio clip is empty: {path}")

    duration = _get_audio_duration_seconds(path)
    if duration is not None:
        if duration < MIN_CLIP_SECONDS:
            logger.warning(
                "voice_clone: reference clip %s is only %.1fs (recommended >= %.0fs) "
                "-- cloning quality may suffer", path, duration, MIN_CLIP_SECONDS,
            )
        elif duration > RECOMMENDED_MAX_CLIP_SECONDS:
            logger.warning(
                "voice_clone: reference clip %s is %.1fs (recommended <= %.0fs) "
                "-- consider trimming to the clearest single segment", path, duration,
                RECOMMENDED_MAX_CLIP_SECONDS,
            )


def resolve_reference_clip(channel: ChannelConfig) -> Path:
    """Resolve which reference audio clip to use for `channel`'s
    Chatterbox synthesis. Precedence:

        1. channel.voice_id, if set and non-empty (per-channel override --
           channels.py can point specific channels at specific clips).
        2. settings.chatterbox_voice_sample_path (global default clip).

    Raises VoiceCloneError if neither is set, or if the resolved path
    fails validate_reference_clip(). Callers (voice_gen.get_synthesizer)
    catch this and fall back to Edge-TTS rather than crashing the pipeline.
    """
    candidate = channel.voice_id or settings.chatterbox_voice_sample_path
    if not candidate:
        raise VoiceCloneError(
            f"No Chatterbox reference clip configured for channel {channel.codename!r} "
            f"-- set channel.voice_id or CHATTERBOX_VOICE_SAMPLE_PATH in .env"
        )

    path = Path(candidate)
    validate_reference_clip(path)
    return path


def preview_clip_info(channel: ChannelConfig) -> dict:
    """Convenience helper for a setup script / CLI: resolves and reports
    on the reference clip for a channel without raising, so a setup wizard
    can show the user what's configured and any warnings. Returns a dict
    with at least a "status" key ("ok" or "error")."""
    try:
        path = resolve_reference_clip(channel)
        duration = _get_audio_duration_seconds(path)
        return {
            "status": "ok",
            "path": str(path),
            "duration_seconds": duration,
            "size_bytes": path.stat().st_size,
        }
    except VoiceCloneError as exc:
        return {"status": "error", "error": str(exc)}
