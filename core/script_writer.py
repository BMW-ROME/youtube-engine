"""
Stage 1 of the content pipeline: GPT-4o script generation.

Produces a structured script (hook, scenes, outro, SEO keywords, chapter
timestamps, affiliate slots) following the Retention Architecture defined
in README.md:

    Hook (0-3s)      -> bold claim / unanswered question
    Opening (0-60s)  -> open loop + pattern interrupt
    Body (60s-80%)   -> curiosity gaps + micro-value delivery every ~90s
    Outro (final 20%)-> payoff resolves the open loop, CTA after payoff

The OpenAI client is injected rather than constructed at import time so this
module can be unit-tested with a fake/mock client and never accidentally
burn real API credits during tests.

Brand wiring (2026-08-17): pulls voice/tone + language do/don't rules from
the shared marketing-ops brand file via core.brand_aware_prompts, so this
channel's scripts don't drift from the canonical brand identity used across
YouTube, n8n, and the voice-acting profiles. Import is wrapped in try/except
and the call itself never raises (brand_aware_prompts/brand_loader already
degrade to a built-in default) -- if brand wiring is ever unavailable for
any reason, script generation continues with the Retention Architecture
prompt alone rather than failing the whole stage.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from config.channels import ChannelConfig
from config.settings import settings
from core import content_db

logger = logging.getLogger(__name__)

# Model used for chat completions. Overridable via LLM_MODEL so local
# OpenAI-compatible backends (Ollama) can send a model name they actually host.
MODEL = settings.llm_model
MAX_RETRIES = 2


class ChatClient(Protocol):
    """Minimal protocol for what we need from an OpenAI-compatible client.
    Lets tests pass a fake object without importing the real openai package."""

    def create_chat_completion(self, *, model: str, messages: list[dict[str, str]],
                                response_format: dict[str, str]) -> str:
        ...


class OpenAIChatClient:
    """Thin wrapper around the real openai SDK. Constructed lazily so importing
    this module never requires an API key to be present. Honors an optional
    OpenAI-compatible base_url (e.g. a local Ollama server) via settings."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self._api_key = api_key or settings.openai_api_key
        # "" (empty env value from .env.template) must coerce to None so the
        # SDK falls back to real OpenAI rather than receiving an empty base_url.
        self._base_url = (base_url if base_url is not None else settings.openai_base_url) or None
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self._api_key, base_url=self._base_url)
        return self._client

    def create_chat_completion(self, *, model: str, messages: list[dict[str, str]],
                                response_format: dict[str, str]) -> str:
        client = self._get_client()
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            response_format=response_format,
        )
        return resp.choices[0].message.content


@dataclass
class Scene:
    narration: str
    visual_description: str


@dataclass
class Script:
    hook: str
    scenes: list[Scene]
    outro: str
    seo_keywords: list[str] = field(default_factory=list)
    chapter_timestamps: list[dict[str, str]] = field(default_factory=list)
    affiliate_slots: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "hook": self.hook,
            "scenes": [s.__dict__ for s in self.scenes],
            "outro": self.outro,
            "seo_keywords": self.seo_keywords,
            "chapter_timestamps": self.chapter_timestamps,
            "affiliate_slots": self.affiliate_slots,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Script":
        scenes = [Scene(**s) for s in data.get("scenes", [])]
        return cls(
            hook=data["hook"],
            scenes=scenes,
            outro=data["outro"],
            seo_keywords=data.get("seo_keywords", []),
            chapter_timestamps=data.get("chapter_timestamps", []),
            affiliate_slots=data.get("affiliate_slots", []),
        )


class ScriptGenerationError(Exception):
    """Raised when the LLM output can't be parsed into a valid Script after retries."""


RETENTION_SYSTEM_PROMPT = """You are a professional YouTube scriptwriter specializing in \
high-retention, algorithm-optimized long-form video scripts.

Follow this structure exactly (Retention Architecture):

1. HOOK (0-3 seconds): The first line must make a bold claim, pose an unanswered \
question, or drop a provocative statement. The viewer decides whether to keep \
watching within 3 seconds.

2. OPENING (0-60 seconds, first 1-2 scenes): Introduce an open loop - a central \
mystery, conflict, or promise that is NOT resolved yet. Use a pattern interrupt \
in tone or pacing.

3. BODY (60s to ~80% mark, most scenes): Each scene should end with a partial \
reveal or curiosity gap that makes the next scene feel necessary. Deliver a \
useful fact, surprising reveal, or emotional beat roughly every 90 seconds of \
narration.

4. OUTRO (final 20%, last scene + outro field): Resolve the open loop from the \
hook. Place the subscribe/CTA ask AFTER the payoff, not before.

Respond with strict JSON matching this schema, and nothing else:
{
  "hook": "string - the opening line",
  "scenes": [
    {"narration": "string", "visual_description": "string - DALL-E safe, no real \
people/logos/violence, describe style not brand names"}
  ],
  "outro": "string - closing line(s) resolving the hook's open loop",
  "seo_keywords": ["string", "..."],
  "chapter_timestamps": [{"time": "MM:SS", "title": "string"}],
  "affiliate_slots": ["string placeholder keys, e.g. AFFILIATE_1"]
}
"""


def _get_brand_style_block() -> str:
    """Fetches the brand voice/tone block from marketing-ops via
    core.brand_aware_prompts. Never raises -- returns "" if the brand
    wiring is unavailable for any reason (missing module, network issue,
    etc.), so script generation always proceeds regardless."""
    try:
        from core.brand_aware_prompts import get_script_style_block
        return get_script_style_block()
    except Exception as exc:  # noqa: BLE001 - brand wiring is best-effort here
        logger.warning("script_writer: brand style block unavailable: %s", exc)
        return ""


def _build_system_prompt() -> str:
    brand_block = _get_brand_style_block()
    if not brand_block:
        return RETENTION_SYSTEM_PROMPT
    return (
        f"{RETENTION_SYSTEM_PROMPT}\n\n"
        f"Brand voice/tone (from the shared marketing-ops brand identity - "
        f"apply this on top of the Retention Architecture above, never "
        f"instead of it):\n{brand_block}"
    )


def _build_user_prompt(channel: ChannelConfig, topic: str) -> str:
    return (
        f"Channel niche: {channel.niche}\n"
        f"Channel display name: {channel.display_name}\n"
        f"Video topic: {topic}\n\n"
        f"Write a long-form YouTube script (6-10 scenes) for this topic, "
        f"matching the channel's niche and tone. Follow the Retention Architecture "
        f"exactly as instructed in the system prompt."
    )


def generate_script(
    channel: ChannelConfig,
    topic: str,
    client: ChatClient | None = None,
    video_id: int | None = None,
) -> Script:
    """Generate a Script for the given channel/topic. If video_id is provided,
    persists the result into content_db metadata and updates status on success/
    failure. Raises ScriptGenerationError if the model output can't be parsed
    as valid JSON matching the Script schema after MAX_RETRIES attempts."""

    active_client = client or OpenAIChatClient()

    if video_id is not None:
        content_db.update_status(video_id, "SCRIPTING")

    system_prompt = _build_system_prompt()

    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 2):
        try:
            raw = active_client.create_chat_completion(
                model=MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": _build_user_prompt(channel, topic)},
                ],
                response_format={"type": "json_object"},
            )
            data = json.loads(raw)
            script = Script.from_dict(data)
            _validate_script(script)

            if video_id is not None:
                content_db.update_metadata(video_id, {"script": script.to_dict()})

            return script

        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            last_error = exc
            logger.warning(
                "script_writer: attempt %d/%d failed to parse output for topic %r: %s",
                attempt, MAX_RETRIES + 1, topic, exc,
            )

    if video_id is not None:
        content_db.update_status(video_id, "FAILED", error_message=str(last_error))
        content_db.increment_retry(video_id)

    raise ScriptGenerationError(
        f"Failed to generate a valid script for topic {topic!r} after "
        f"{MAX_RETRIES + 1} attempts: {last_error}"
    )


def _validate_script(script: Script) -> None:
    if not script.hook.strip():
        raise ValueError("hook is empty")
    if len(script.scenes) < 3:
        raise ValueError(f"expected at least 3 scenes, got {len(script.scenes)}")
    for i, scene in enumerate(script.scenes):
        if not scene.narration.strip():
            raise ValueError(f"scene {i} has empty narration")
        if not scene.visual_description.strip():
            raise ValueError(f"scene {i} has empty visual_description")
    if not script.outro.strip():
        raise ValueError("outro is empty")
