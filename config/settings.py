"""
Global settings for the YouTube Engine.
Loads from environment variables (.env) via pydantic-settings.
Only OPENAI_API_KEY is required - everything else has safe defaults
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

    # ===== AI Backend (local-LLM support) =====
    # OPENAI_BASE_URL points the CHAT stages (script_writer.py, seo_optimizer.py)
    # at an OpenAI-compatible endpoint. Leave blank/unset for real OpenAI; set to
    # http://localhost:11434/v1 for a local Ollama server. Ollama ignores the
    # Authorization header, so OPENAI_API_KEY can be any non-empty string there.
    openai_base_url: str | None = Field(default=None, alias="OPENAI_BASE_URL")
    # IMAGE_BASE_URL points the IMAGE stage (image_gen.py) at an OpenAI-compatible
    # image server, e.g. LocalAI (http://localhost:8080/v1), whose /v1/images/generations
    # endpoint accepts the same payload shape as DALL-E. Leave blank for real DALL-E.
    image_base_url: str | None = Field(default=None, alias="IMAGE_BASE_URL")
    # Model names sent to the chat/image backends. For local servers these MUST match
    # a model the server actually hosts (e.g. `ollama list` for Ollama, the LocalAI
    # model registry for images).
    llm_model: str = Field(default="gpt-4o", alias="LLM_MODEL")
    image_model: str = Field(default="dall-e-3", alias="IMAGE_MODEL")

    # ===== Voice Cloning (Chatterbox) =====
    # MIGRATION (2026-08-17): replaced ElevenLabs with Resemble AI's
    # Chatterbox TTS - local, open-source (MIT), zero-shot voice cloning
    # from a single reference audio clip. No API key needed; runs on your
    # own GPU/CPU via the chatterbox-tts pip package.
    chatterbox_voice_sample_path: str | None = Field(
        default=None, alias="CHATTERBOX_VOICE_SAMPLE_PATH"
    )
    chatterbox_device: str = Field(default="cuda", alias="CHATTERBOX_DEVICE")  # "cuda" | "cpu" | "mps"
    chatterbox_exaggeration: float = Field(default=0.5, alias="CHATTERBOX_EXAGGERATION")
    chatterbox_cfg_weight: float = Field(default=0.5, alias="CHATTERBOX_CFG_WEIGHT")

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

    # ===== Transcript RAG =====
    # Hybrid retrieval over produced videos' transcripts: SQLite FTS5 keyword
    # search always works offline; embeddings add semantic ranking when a model
    # is available on EMBEDDINGS_BASE_URL (an Ollama-ish /api/embeddings). If the
    # embed model is missing the index degrades to FTS-only instead of failing.
    rag_enabled: bool = Field(default=True, alias="RAG_ENABLED")
    rag_embedding_model: str = Field(default="nomic-embed-text", alias="RAG_EMBEDDING_MODEL")
    rag_db_path: str | None = Field(default=None, alias="RAG_DB_PATH")
    embeddings_base_url: str = Field(default="http://localhost:11434", alias="EMBEDDINGS_BASE_URL")

    @property
    def rag_db_file(self) -> Path:
        if self.rag_db_path:
            path = Path(self.rag_db_path)
        else:
            path = self.content_path / "rag.db"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

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
    def has_chatterbox(self) -> bool:
        """True if a global default reference clip is configured. Individual
        channels can still override via ChannelConfig.voice_id even if this
        is False -- see core.voice_clone.resolve_reference_clip()."""
        return bool(self.chatterbox_voice_sample_path)

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


# Singleton - import `settings` everywhere else in the codebase.
settings = Settings()
