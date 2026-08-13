"""
Global settings for the YouTube Engine.
Loads from environment variables (.env) via pydantic-settings.
Only OPENAI_API_KEY is required — everything else has safe defaults
so the system runs in "free mode" out of the box.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from pathlib import Path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ===== REQUIRED =====
    openai_api_key: str = Field(..., alias="OPENAI_API_KEY")

    # ===== Voice Cloning (ElevenLabs) =====
    elevenlabs_api_key: str | None = Field(default=None, alias="ELEVENLABS_API_KEY")
    elevenlabs_voice_id: str | None = Field(default=None, alias="ELEVENLABS_VOICE_ID")
    elevenlabs_model_id: str = Field(default="eleven_monolingual_v1", alias="ELEVENLABS_MODEL_ID")
    elevenlabs_stability: float = Field(default=0.65, alias="ELEVENLABS_STABILITY")
    elevenlabs_similarity: float = Field(default=0.80, alias="ELEVENLABS_SIMILARITY")
    elevenlabs_style: float = Field(default=0.35, alias="ELEVENLABS_STYLE")
    elevenlabs_boost: bool = Field(default=True, alias="ELEVENLABS_BOOST")

    # ===== Video Modes =====
    default_video_mode: str = Field(default="kenburns", alias="DEFAULT_VIDEO_MODE")
    replicate_api_token: str | None = Field(default=None, alias="REPLICATE_API_TOKEN")

    # ===== Shorts & Music =====
    generate_shorts: bool = Field(default=False, alias="GENERATE_SHORTS")
    shorts_per_video: int = Field(default=3, alias="SHORTS_PER_VIDEO")
    background_music: bool = Field(default=False, alias="BACKGROUND_MUSIC")

    # ===== Upload =====
    upload_mode: str = Field(default="local", alias="UPLOAD_MODE")  # local | skip | pipedream | youtube_api
    youtube_client_id: str | None = Field(default=None, alias="YOUTUBE_CLIENT_ID")
    youtube_client_secret: str | None = Field(default=None, alias="YOUTUBE_CLIENT_SECRET")
    youtube_refresh_token: str | None = Field(default=None, alias="YOUTUBE_REFRESH_TOKEN")
    pipedream_webhook_url: str | None = Field(default=None, alias="PIPEDREAM_WEBHOOK_URL")

    # ===== General =====
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    dashboard_host: str = Field(default="0.0.0.0", alias="DASHBOARD_HOST")
    dashboard_port: int = Field(default=8000, alias="DASHBOARD_PORT")
    content_dir: str = Field(default="./output", alias="CONTENT_DIR")

    @property
    def content_path(self) -> Path:
        path = Path(self.content_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def has_elevenlabs(self) -> bool:
        return bool(self.elevenlabs_api_key and self.elevenlabs_voice_id)

    @property
    def has_replicate(self) -> bool:
        return bool(self.replicate_api_token)

    @property
    def has_youtube_api(self) -> bool:
        return bool(
            self.youtube_client_id
            and self.youtube_client_secret
            and self.youtube_refresh_token
        )


# Singleton — import `settings` everywhere else in the codebase.
settings = Settings()
