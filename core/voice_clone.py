"""
ElevenLabs voice cloning setup wizard.

Used to create/refresh an Instant Voice Clone for the Thee3lite Speaks
channel (or any channel switched to voice_engine="elevenlabs"). Accepts
1-25 audio samples, uploads them to ElevenLabs, and returns the resulting
voice_id so it can be saved into .env as ELEVENLABS_VOICE_ID.

This module never writes to .env directly - it returns the voice_id and
leaves persistence to the caller (scripts/setup_voice.py), keeping the
cloning logic itself free of file-IO side effects and easy to test.

The ElevenLabs client is injected via a Protocol, matching the pattern in
script_writer.py and voice_gen.py, so cloning can be tested without a real
ElevenLabs account or network access.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from config.settings import settings

logger = logging.getLogger(__name__)

MIN_SAMPLES = 1
MAX_SAMPLES = 25
ALLOWED_EXTENSIONS = {".mp3", ".wav", ".m4a", ".flac", ".ogg"}


class VoiceCloneError(Exception):
    """Raised when sample validation or the clone upload fails."""


class VoiceCloneClient(Protocol):
    """Minimal interface for what we need from an ElevenLabs-compatible client."""

    def clone_voice(self, name: str, description: str, file_paths: list[Path]) -> str:
        """Uploads samples and returns the new voice_id."""
        ...

    def delete_voice(self, voice_id: str) -> None:
        ...

    def list_voices(self) -> list[dict]:
        ...


class ElevenLabsCloneClient:
    """Thin wrapper around the real ElevenLabs SDK. Constructed lazily so
    importing this module never requires the elevenlabs package or an API key."""

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or settings.elevenlabs_api_key
        self._client = None

    def _get_client(self):
        if self._client is None:
            from elevenlabs.client import ElevenLabs
            self._client = ElevenLabs(api_key=self._api_key)
        return self._client

    def clone_voice(self, name: str, description: str, file_paths: list[Path]) -> str:
        client = self._get_client()
        files = [open(p, "rb") for p in file_paths]
        try:
            voice = client.voices.ivc.create(
                name=name,
                description=description,
                files=files,
            )
            return voice.voice_id
        finally:
            for f in files:
                f.close()

    def delete_voice(self, voice_id: str) -> None:
        client = self._get_client()
        client.voices.delete(voice_id)

    def list_voices(self) -> list[dict]:
        client = self._get_client()
        return [v.__dict__ for v in client.voices.get_all().voices]


@dataclass
class CloneResult:
    voice_id: str
    name: str
    sample_count: int


def validate_samples(file_paths: list[Path]) -> None:
    """Raises VoiceCloneError if the sample set doesn't meet ElevenLabs'
    requirements (1-25 files, valid audio extensions, files must exist)."""
    if not file_paths:
        raise VoiceCloneError("At least 1 audio sample is required")
    if len(file_paths) > MAX_SAMPLES:
        raise VoiceCloneError(
            f"Too many samples: got {len(file_paths)}, max is {MAX_SAMPLES}"
        )
    for p in file_paths:
        if not p.exists():
            raise VoiceCloneError(f"Sample file not found: {p}")
        if p.suffix.lower() not in ALLOWED_EXTENSIONS:
            raise VoiceCloneError(
                f"Unsupported audio format '{p.suffix}' for {p.name}. "
                f"Allowed: {sorted(ALLOWED_EXTENSIONS)}"
            )
        if p.stat().st_size == 0:
            raise VoiceCloneError(f"Sample file is empty: {p}")


def clone_voice(
    name: str,
    file_paths: list[Path],
    description: str = "",
    client: VoiceCloneClient | None = None,
) -> CloneResult:
    """Validate samples and create a new ElevenLabs Instant Voice Clone.
    Returns the voice_id - caller is responsible for saving it (e.g. to
    .env as ELEVENLABS_VOICE_ID)."""
    validate_samples(file_paths)

    active_client = client or ElevenLabsCloneClient()

    try:
        voice_id = active_client.clone_voice(
            name=name,
            description=description or f"Cloned voice for {name}",
            file_paths=file_paths,
        )
    except Exception as exc:  # noqa: BLE001 - upload failures vary by transport
        logger.error("voice_clone: failed to clone voice %r: %s", name, exc)
        raise VoiceCloneError(f"Failed to clone voice {name!r}: {exc}") from exc

    if not voice_id:
        raise VoiceCloneError(f"Clone succeeded but no voice_id was returned for {name!r}")

    logger.info("voice_clone: created voice_id=%s for name=%r (%d samples)",
                voice_id, name, len(file_paths))

    return CloneResult(voice_id=voice_id, name=name, sample_count=len(file_paths))


def voice_exists(voice_id: str, client: VoiceCloneClient | None = None) -> bool:
    """Check whether a given voice_id still exists in the account (useful
    for setup_voice.py to detect a stale ELEVENLABS_VOICE_ID in .env)."""
    active_client = client or ElevenLabsCloneClient()
    voices = active_client.list_voices()
    return any(v.get("voice_id") == voice_id for v in voices)


def delete_voice(voice_id: str, client: VoiceCloneClient | None = None) -> None:
    active_client = client or ElevenLabsCloneClient()
    active_client.delete_voice(voice_id)
    logger.info("voice_clone: deleted voice_id=%s", voice_id)
