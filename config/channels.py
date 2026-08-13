"""
Channel definitions for the YouTube Engine.
Each of the 7 built-in channels is a ChannelConfig instance registered in CHANNELS.
Freestyle mode builds new ChannelConfig instances dynamically at runtime — see core/freestyle.py.
"""

import os
from dataclasses import dataclass, field
from config.settings import settings


@dataclass
class ChannelConfig:
    codename: str                     # short key, e.g. "finance"
    display_name: str                 # human name, e.g. "Wealth Decoded"
    niche: str                        # e.g. "Finance"
    channel_id: str                   # YouTube channel ID (from .env)
    category_id: str                  # YouTube category ID
    voice_engine: str                 # "edge_tts" | "elevenlabs"
    voice_id: str                     # Edge-TTS voice name or ElevenLabs voice ID
    video_mode: str                   # "kenburns" | "sketch" | "animated" | "ai_video"
    post_time_est: str                # e.g. "08:00"
    videos_per_day: int = 1
    cpm_low: float | None = None
    cpm_high: float | None = None
    image_style_prefix: str = ""
    affiliate_placeholder: str | None = None

    @property
    def cpm_range(self) -> str:
        if self.cpm_low is None or self.cpm_high is None:
            return "—"
        return f"${self.cpm_low:g}-{self.cpm_high:g}"


CHANNELS: dict[str, ChannelConfig] = {}


def _register(cfg: ChannelConfig) -> ChannelConfig:
    CHANNELS[cfg.codename] = cfg
    return cfg


FINANCE = _register(ChannelConfig(
    codename="finance",
    display_name="Wealth Decoded",
    niche="Finance",
    channel_id=os.getenv("FINANCE_CHANNEL_ID", ""),
    category_id="25",  # News & Politics-adjacent; adjust per actual YT category
    voice_engine="edge_tts",
    voice_id="en-US-GuyNeural",
    video_mode=os.getenv("FINANCE_VIDEO_MODE", settings.default_video_mode),
    post_time_est="08:00",
    videos_per_day=int(os.getenv("VIDEOS_PER_DAY_FINANCE", "1")),
    cpm_low=15, cpm_high=22,
    image_style_prefix="Clean modern financial infographic style, muted blues and greens, professional",
    affiliate_placeholder="[AFFILIATE_FINANCE_1]",
))

MMO = _register(ChannelConfig(
    codename="mmo",
    display_name="Side Hustle Lab",
    niche="Make Money Online",
    channel_id=os.getenv("MMO_CHANNEL_ID", ""),
    category_id="26",  # Howto & Style
    voice_engine="edge_tts",
    voice_id="en-US-ChristopherNeural",
    video_mode=os.getenv("MMO_VIDEO_MODE", settings.default_video_mode),
    post_time_est="12:00",
    videos_per_day=int(os.getenv("VIDEOS_PER_DAY_MMO", "1")),
    cpm_low=15, cpm_high=20,
    image_style_prefix="Bright energetic hustle-culture aesthetic, bold colors, motivational",
    affiliate_placeholder="[AFFILIATE_MMO_1]",
))

TECH = _register(ChannelConfig(
    codename="tech",
    display_name="Future Proof Tech",
    niche="Technology",
    channel_id=os.getenv("TECH_CHANNEL_ID", ""),
    category_id="28",  # Science & Technology
    voice_engine="edge_tts",
    voice_id="en-US-EricNeural",
    video_mode=os.getenv("TECH_VIDEO_MODE", settings.default_video_mode),
    post_time_est="16:00",
    videos_per_day=int(os.getenv("VIDEOS_PER_DAY_TECH", "1")),
    cpm_low=12, cpm_high=18,
    image_style_prefix="Sleek futuristic tech aesthetic, dark background, neon accent lighting",
    affiliate_placeholder="[AFFILIATE_TECH_1]",
))

TRENDING = _register(ChannelConfig(
    codename="trending",
    display_name="Trending Pulse",
    niche="Viral/News",
    channel_id=os.getenv("TRENDING_CHANNEL_ID", ""),
    category_id="25",  # News & Politics
    voice_engine="edge_tts",
    voice_id="en-US-AriaNeural",
    video_mode=os.getenv("TRENDING_VIDEO_MODE", settings.default_video_mode),
    post_time_est="10:00",
    videos_per_day=int(os.getenv("VIDEOS_PER_DAY_TRENDING", "1")),
    cpm_low=None, cpm_high=None,
    image_style_prefix="Bold viral news-style graphic, high contrast, attention-grabbing",
))

THEE3LITE = _register(ChannelConfig(
    codename="thee3lite",
    display_name="Thee3lite Speaks",
    niche="Personal Brand",
    channel_id=os.getenv("THEE3LITE_CHANNEL_ID", ""),
    category_id="22",  # People & Blogs
    voice_engine="elevenlabs",
    voice_id=settings.elevenlabs_voice_id or "",
    video_mode=os.getenv("THEE3LITE_VIDEO_MODE", "animated"),
    post_time_est="14:00",
    videos_per_day=int(os.getenv("VIDEOS_PER_DAY_THEE3LITE", "1")),
    cpm_low=None, cpm_high=None,
    image_style_prefix="Personal, authentic, direct-to-camera energy, warm tones",
))

LEGAL = _register(ChannelConfig(
    codename="legal",
    display_name="Justice Files",
    niche="Legal/Crime",
    channel_id=os.getenv("LEGAL_CHANNEL_ID", ""),
    category_id="25",
    voice_engine="edge_tts",
    voice_id="en-US-DavisNeural",
    video_mode=os.getenv("LEGAL_VIDEO_MODE", settings.default_video_mode),
    post_time_est="18:00",
    videos_per_day=int(os.getenv("VIDEOS_PER_DAY_LEGAL", "1")),
    cpm_low=12, cpm_high=18,
    image_style_prefix="Serious courtroom-drama aesthetic, dramatic lighting, desaturated palette",
    affiliate_placeholder="[AFFILIATE_LEGAL_1]",
))

STORIES = _register(ChannelConfig(
    codename="stories",
    display_name="Dark Truth Tales",
    niche="Dark Stories",
    channel_id=os.getenv("STORIES_CHANNEL_ID", ""),
    category_id="24",  # Entertainment
    voice_engine="edge_tts",
    voice_id="en-US-JennyNeural",
    video_mode=os.getenv("STORIES_VIDEO_MODE", settings.default_video_mode),
    post_time_est="20:00",
    videos_per_day=int(os.getenv("VIDEOS_PER_DAY_STORIES", "1")),
    cpm_low=20, cpm_high=25,
    image_style_prefix="Moody atmospheric mystery aesthetic, deep shadows, cinematic",
    affiliate_placeholder="[AFFILIATE_STORIES_1]",
))


def get_channel(codename: str) -> ChannelConfig:
    """Fetch a registered channel config by codename. Raises KeyError if not found —
    use core/freestyle.py to build one dynamically for arbitrary categories instead."""
    if codename not in CHANNELS:
        raise KeyError(
            f"Unknown channel '{codename}'. Registered: {list(CHANNELS.keys())}. "
            f"For a custom category, use Freestyle mode (core/freestyle.py) instead."
        )
    return CHANNELS[codename]


def all_channels() -> list[ChannelConfig]:
    return list(CHANNELS.values())
