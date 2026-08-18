"""
core/freestyle.py

Dynamic channel builder for Freestyle mode -- lets scripts/start_engine.py
(and any future caller) generate a video for an arbitrary category that
isn't one of the 7 built-in channels registered in config/channels.py,
without needing to hand-write a new ChannelConfig for every one-off topic.

Per README.md's spec:
    Freestyle | freestyle-{slug} | Any | -- | Edge-TTS | user choice | 12 PM

Freestyle channels:
    - Always use Edge-TTS (never Chatterbox -- that's reserved for the
      curated Thee3lite Speaks brand voice, not arbitrary one-off topics).
    - Use a generic, neutral Edge-TTS voice and a video_mode chosen by the
      caller (defaults to settings.default_video_mode if not specified).
    - Are NOT registered into config.channels.CHANNELS -- they're built
      fresh per-call and never persisted, since by definition there could
      be unlimited categories.
    - Still get a content_db row like any other channel (channel field is
      set to the freestyle-{slug} codename), so run history/dashboard
      queries work the same way for freestyle runs as built-in channels.

Public API:
    build_freestyle_channel(category, video_mode=None) -> ChannelConfig
    slugify(category) -> str
"""

from __future__ import annotations

import re

from config.channels import ChannelConfig
from config.settings import settings

# Neutral default voice for freestyle content -- no single niche/brand
# association, unlike the curated voice choices in config/channels.py.
DEFAULT_FREESTYLE_VOICE = "en-US-JennyNeural"
DEFAULT_FREESTYLE_CATEGORY_ID = "22"  # People & Blogs -- reasonable generic default


def slugify(category: str) -> str:
    """Turn an arbitrary category string into a safe codename fragment,
    e.g. "true crime" -> "true-crime", "AI & Robots!" -> "ai-robots"."""
    slug = category.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug or "freestyle"


def build_freestyle_channel(category: str, video_mode: str | None = None) -> ChannelConfig:
    """
    Build a one-off ChannelConfig for an arbitrary Freestyle category.

    Args:
        category: free-text category/niche, e.g. "true crime", "AI news".
        video_mode: one of "kenburns" | "sketch" | "animated" | "ai_video".
            Defaults to settings.default_video_mode if not provided.

    Returns:
        A ChannelConfig NOT registered in config.channels.CHANNELS -- pass
        it directly wherever a channel is needed (this module bypasses
        config.channels.get_channel() entirely for freestyle runs).
    """
    slug = slugify(category)
    return ChannelConfig(
        codename=f"freestyle-{slug}",
        display_name=f"Freestyle: {category.strip().title()}",
        niche=category.strip(),
        channel_id="",
        category_id=DEFAULT_FREESTYLE_CATEGORY_ID,
        voice_engine="edge_tts",
        voice_id=DEFAULT_FREESTYLE_VOICE,
        video_mode=video_mode or settings.default_video_mode,
        post_time_est="12:00",
        videos_per_day=1,
        cpm_low=None,
        cpm_high=None,
        image_style_prefix="Clean, versatile editorial illustration style, neutral tone",
        affiliate_placeholder=None,
    )
