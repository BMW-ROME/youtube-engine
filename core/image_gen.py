"""
Stage 4 of the content pipeline: scene image generation via DALL-E 3.

Generates one image per scene, using the channel's image_style_prefix to
keep visuals consistent with the channel's brand. Per README.md's Resilience
Architecture: DALL-E content-filter rejections are handled with
sanitize -> safety suffix -> 2-attempt retry -> gradient placeholder, so a
single flagged prompt never fails the whole video.

The image generation client is injected via a Protocol so this module is
fully unit-testable without an OpenAI API key or real network calls.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from config.channels import ChannelConfig
from config.settings import settings
from core import content_db
from core.script_writer import Script

logger = logging.getLogger(__name__)

# Image model sent to the backend. Overridable via IMAGE_MODEL so OpenAI-
# compatible local image servers (e.g. LocalAI at IMAGE_BASE_URL) can use a
# model name they actually host (like sdxl-turbo).
MODEL = settings.image_model
MAX_FILTER_RETRIES = 2  # sanitize attempt + safety-suffix attempt

# Words/phrases that commonly trigger DALL-E's content filter. Stripped out
# during sanitization before the first retry.
_FILTER_TRIGGERS = [
    r"\bviolen\w*\b", r"\bkill\w*\b", r"\bweapon\w*\b", r"\bblood\w*\b",
    r"\bnude\w*\b", r"\bnaked\b", r"\bdrug\w*\b", r"\bsuicide\w*\b",
    r"\breal (person|people|celebrity|politician)\b",
]

_SAFETY_SUFFIX = (
    ", tasteful editorial illustration style, no real people, no logos, no text, "
    "no graphic violence, suitable for all audiences"
)


class ImageGenerationError(Exception):
    """Raised only if even the placeholder fallback fails (e.g. disk write error).
    A DALL-E content-filter rejection alone never raises this - it falls through
    to the placeholder instead."""


class ImageClient(Protocol):
    """Minimal protocol for what we need from an OpenAI-compatible image client."""

    def generate_image(self, *, model: str, prompt: str, size: str) -> bytes:
        """Returns raw image bytes, or raises on content-filter rejection /
        API error (implementation-specific exception types)."""
        ...


class OpenAIImageClient:
    """Thin wrapper around the openai SDK's image generation endpoint.
    Honors an optional OpenAI-compatible base_url (e.g. LocalAI's
    /v1/images/generations) so the DALL-E stage can run against a local
    server providing the same payload shape."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self._api_key = api_key or settings.openai_api_key
        # "" (empty env value from .env.template) must coerce to None so the
        # SDK falls back to real OpenAI rather than receiving an empty base_url.
        self._base_url = (base_url if base_url is not None else settings.image_base_url) or None
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self._api_key, base_url=self._base_url)
        return self._client

    def generate_image(self, *, model: str, prompt: str, size: str) -> bytes:
        import base64
        client = self._get_client()
        resp = client.images.generate(
            model=model, prompt=prompt, size=size, n=1, response_format="b64_json",
        )
        return base64.b64decode(resp.data[0].b64_json)


class PlaceholderGenerator(Protocol):
    """Generates a fallback image when DALL-E generation fails entirely."""

    def generate(self, size: str) -> bytes:
        ...


class GradientPlaceholderGenerator:
    """Real implementation: solid gradient PNG via Pillow. Skipped gracefully
    if Pillow isn't installed (returns a 1x1 transparent PNG stub instead)."""

    def generate(self, size: str) -> bytes:
        import io
        try:
            from PIL import Image
        except ImportError:
            logger.warning("image_gen: Pillow not installed, returning stub placeholder bytes")
            return b"\x89PNG\r\n\x1a\n"  # minimal PNG signature stub, not a valid image

        w, h = (int(x) for x in size.split("x"))
        img = Image.new("RGB", (w, h))
        top, bottom = (30, 30, 60), (10, 10, 25)
        for y in range(h):
            t = y / max(h - 1, 1)
            row_color = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
            for x in range(w):
                img.putpixel((x, y), row_color)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()


def _sanitize_prompt(prompt: str) -> str:
    sanitized = prompt
    for pattern in _FILTER_TRIGGERS:
        sanitized = re.sub(pattern, "", sanitized, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", sanitized).strip()


def _build_prompt(channel: ChannelConfig, visual_description: str, attempt: int) -> str:
    base = f"{channel.image_style_prefix}. {visual_description}" if channel.image_style_prefix \
        else visual_description
    if attempt == 0:
        return base
    if attempt == 1:
        return _sanitize_prompt(base)
    return _sanitize_prompt(base) + _SAFETY_SUFFIX


@dataclass
class SceneImage:
    scene_index: int
    output_path: Path
    was_placeholder: bool


@dataclass
class ImageGenResult:
    images: list[SceneImage]
    placeholder_count: int


def _generate_one_scene_image(
    channel: ChannelConfig,
    visual_description: str,
    scene_index: int,
    output_dir: Path,
    client: ImageClient,
    placeholder_gen: PlaceholderGenerator,
    size: str = "1792x1024",
) -> SceneImage:
    output_path = output_dir / f"scene_{scene_index:02d}.png"

    for attempt in range(MAX_FILTER_RETRIES + 1):
        prompt = _build_prompt(channel, visual_description, attempt)
        try:
            image_bytes = client.generate_image(model=MODEL, prompt=prompt, size=size)
            output_path.write_bytes(image_bytes)
            return SceneImage(scene_index, output_path, was_placeholder=False)
        except Exception as exc:  # noqa: BLE001 - content-filter/API errors vary by SDK
            logger.warning(
                "image_gen: scene %d attempt %d/%d rejected/failed: %s",
                scene_index, attempt + 1, MAX_FILTER_RETRIES + 1, exc,
            )

    logger.error(
        "image_gen: scene %d exhausted %d attempts, using gradient placeholder",
        scene_index, MAX_FILTER_RETRIES + 1,
    )
    output_path.write_bytes(placeholder_gen.generate(size))
    return SceneImage(scene_index, output_path, was_placeholder=True)


def generate_images(
    channel: ChannelConfig,
    script: Script,
    video_id: int | None = None,
    client: ImageClient | None = None,
    placeholder_gen: PlaceholderGenerator | None = None,
    max_concurrent: int = 3,
) -> ImageGenResult:
    """Generate one image per scene in `script`. Never raises for individual
    content-filter rejections - those fall back to placeholders. Persists
    image paths into content_db metadata."""

    active_client = client or OpenAIImageClient()
    active_placeholder = placeholder_gen or GradientPlaceholderGenerator()

    if video_id is not None:
        content_db.update_status(video_id, "IMAGING")

    output_dir = settings.content_path / "images" / f"video_{video_id or 'preview'}"
    output_dir.mkdir(parents=True, exist_ok=True)

    images: list[SceneImage] = []
    for i, scene in enumerate(script.scenes):
        result = _generate_one_scene_image(
            channel, scene.visual_description, i, output_dir, active_client, active_placeholder
        )
        images.append(result)

    placeholder_count = sum(1 for img in images if img.was_placeholder)

    if video_id is not None:
        content_db.update_metadata(video_id, {
            "image_paths": [str(img.output_path) for img in images],
            "image_placeholder_count": placeholder_count,
        })

    if placeholder_count:
        logger.warning(
            "image_gen: video_id=%s completed with %d/%d placeholder image(s)",
            video_id, placeholder_count, len(images),
        )

    return ImageGenResult(images=images, placeholder_count=placeholder_count)
