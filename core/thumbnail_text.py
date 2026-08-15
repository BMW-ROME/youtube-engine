"""
core/thumbnail_text.py

Stage 5 of the content pipeline: Thumbnail Text Overlay.

Burns bold, high-contrast keyword text onto a generated thumbnail image
using Pillow, to improve click-through rate. Matches the resilience
architecture documented in README.md: if Pillow is not installed, this
stage is skipped gracefully and the pipeline continues with the plain
thumbnail image untouched.

Public API:
    add_thumbnail_text(image_path, text, output_path=None, ...) -> str | None

Design notes:
- Pure function, no network calls, no DB writes -- keeps this stage easy
  to unit test in isolation with a fake/generated image.
- Text is wrapped to fit within a max width, centered horizontally, and
  placed near the bottom third of the frame with a semi-transparent
  backing bar for legibility over busy images.
- A simple stroke (outline) is drawn around the text for extra contrast
  when a backing bar is disabled.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from PIL import Image, ImageDraw, ImageFont
    PILLOW_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised via PILLOW_AVAILABLE flag in tests
    PILLOW_AVAILABLE = False
    logger.warning("Pillow not installed - thumbnail text overlay will be skipped.")


# Candidate bold font paths, checked in order (Windows-first per README).
_FONT_CANDIDATES = [
    "C:/Windows/Fonts/impact.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]


@dataclass
class ThumbnailTextConfig:
    """Tunable parameters for the text overlay."""

    font_size: int = 90
    text_color: tuple = (255, 255, 255)
    stroke_color: tuple = (0, 0, 0)
    stroke_width: int = 6
    max_width_ratio: float = 0.9  # fraction of image width text may occupy
    bottom_margin_ratio: float = 0.08
    backing_bar: bool = True
    backing_bar_color: tuple = (0, 0, 0)
    backing_bar_opacity: int = 140  # 0-255


def _load_font(size: int):
    """Try each known bold font path; fall back to Pillow's default font."""
    for path in _FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    logger.warning("No bold TTF font found on system - using Pillow default font.")
    return ImageFont.load_default()


def _wrap_text(draw, text: str, font, max_width: int) -> list:
    """Greedy word-wrap so each line fits within max_width pixels."""
    words = text.split()
    lines = []
    current = ""

    for word in words:
        candidate = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), candidate, font=font)
        width = bbox[2] - bbox[0]
        if width <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word

    if current:
        lines.append(current)

    return lines


def add_thumbnail_text(
    image_path: str,
    text: str,
    output_path: Optional[str] = None,
    config: Optional[ThumbnailTextConfig] = None,
) -> Optional[str]:
    """
    Burn bold keyword text onto a thumbnail image.

    Args:
        image_path: path to the source thumbnail (PNG/JPEG).
        text: short keyword/phrase to overlay (e.g. "THEY LIED TO YOU").
        output_path: where to save the result. Defaults to overwriting
            image_path's directory with a "_text" suffix.
        config: optional ThumbnailTextConfig to override styling defaults.

    Returns:
        The output file path as a string, or None if this stage was
        skipped (Pillow missing, empty text, or source image not found).
    """
    if not PILLOW_AVAILABLE:
        logger.info("[thumbnail_text] Pillow unavailable - skipping overlay stage.")
        return None

    if not text or not text.strip():
        logger.info("[thumbnail_text] No text provided - skipping overlay stage.")
        return None

    src = Path(image_path)
    if not src.exists():
        logger.error("[thumbnail_text] Source image not found: %s", image_path)
        return None

    cfg = config or ThumbnailTextConfig()

    try:
        image = Image.open(src).convert("RGBA")
    except Exception as exc:  # noqa: BLE001 - resilience: never crash the pipeline
        logger.error("[thumbnail_text] Failed to open image %s: %s", image_path, exc)
        return None

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    font = _load_font(cfg.font_size)
    max_width = int(image.width * cfg.max_width_ratio)
    lines = _wrap_text(draw, text.strip().upper(), font, max_width)

    line_heights = []
    line_widths = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_widths.append(bbox[2] - bbox[0])
        line_heights.append(bbox[3] - bbox[1])

    line_spacing = 10
    total_text_height = sum(line_heights) + line_spacing * (len(lines) - 1)
    bottom_margin = int(image.height * cfg.bottom_margin_ratio)
    start_y = image.height - bottom_margin - total_text_height

    if cfg.backing_bar:
        bar_top = start_y - 24
        bar_bottom = image.height - bottom_margin + 24
        draw.rectangle(
            [(0, max(bar_top, 0)), (image.width, min(bar_bottom, image.height))],
            fill=(*cfg.backing_bar_color, cfg.backing_bar_opacity),
        )

    y = start_y
    for line, width, height in zip(lines, line_widths, line_heights):
        x = (image.width - width) // 2
        draw.text(
            (x, y),
            line,
            font=font,
            fill=cfg.text_color,
            stroke_width=cfg.stroke_width,
            stroke_fill=cfg.stroke_color,
        )
        y += height + line_spacing

    result = Image.alpha_composite(image, overlay).convert("RGB")

    if output_path is None:
        output_path = str(src.with_name(f"{src.stem}_text{src.suffix}"))

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    result.save(output_path)
    logger.info("[thumbnail_text] Saved thumbnail with text overlay -> %s", output_path)

    return output_path
