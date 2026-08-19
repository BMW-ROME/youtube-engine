"""
core/seo_optimizer.py

Stage 8 of the content pipeline: SEO Optimization.

Generates AI-powered SEO metadata for a finished video: title, description
(with timestamps/keywords), tags, hashtags, pinned comment draft, and end
screen topic suggestions. Consumes the script's hook/scenes/seo_keywords
(from script_writer.py) and the chapter markers (from video_assembler.py).

Public API:
    optimize_seo(client, channel, script, chapter_markers=None) -> SEOResult

Design notes:
- Uses the SAME ChatClient protocol as script_writer.py --
  create_chat_completion(model=, messages=, response_format=) -- fixed
  2026-08-16. The original version of this module used a different,
  incompatible .complete(system, user) protocol, meaning a single real
  OpenAIChatClient wrapper couldn't be reused across script_writer.py and
  seo_optimizer.py without writing two adapter shims. Now one client
  class/fake works for both stages.
- Same retry-then-fail resilience: malformed JSON triggers up to 3
  attempts before raising SEOGenerationError.
- Title is hard-capped at 60 chars, tags at 500 chars total, per README.

Brand wiring (2026-08-17): pulls voice/tone + niche guidance from the shared
marketing-ops brand file, and appends a lead-gen CTA to the description and
pinned comment, via core.brand_aware_prompts. The CTA is appended AFTER the
LLM-generated content rather than left for the LLM to invent, per
BRAND_INTEGRATION_SNIPPET.md -- the model should never fabricate contact
info. All brand/CTA calls are wrapped in try/except; a failure there never
blocks SEO metadata generation, it just omits the CTA/brand block for that
run.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Protocol

from config.settings import settings

logger = logging.getLogger(__name__)

MAX_TITLE_CHARS = 60
MAX_TAGS_CHARS = 500
MAX_RETRIES = 3
# Model used for chat completions. Overridable via LLM_MODEL so local
# OpenAI-compatible backends (Ollama) can send a model name they actually host.
MODEL = settings.llm_model


class SEOGenerationError(Exception):
    """Raised when SEO metadata could not be generated after all retries."""


class ChatClient(Protocol):
    """Same protocol as core.script_writer.ChatClient, so a single real
    OpenAIChatClient implementation can be shared across both stages."""

    def create_chat_completion(self, *, model: str, messages: list[dict[str, str]],
                                response_format: dict[str, str]) -> str:
        ...


@dataclass
class SEOResult:
    title: str
    description: str
    tags: List[str]
    hashtags: List[str]
    pinned_comment: str
    end_screen_topics: List[str] = field(default_factory=list)


def _get_brand_style_block() -> str:
    """Fetches the SEO-facing brand voice/tone + niches block from
    marketing-ops via core.brand_aware_prompts. Never raises -- returns ""
    if brand wiring is unavailable, so SEO generation always proceeds."""
    try:
        from core.brand_aware_prompts import get_seo_style_block
        return get_seo_style_block()
    except Exception as exc:  # noqa: BLE001 - brand wiring is best-effort here
        logger.warning("seo_optimizer: brand style block unavailable: %s", exc)
        return ""


def _get_video_cta() -> str:
    """Fetches the ready-to-append video description CTA from
    core.brand_aware_prompts (lead_capture.yaml). Never raises -- returns ""
    if unavailable, so the description is simply left without a CTA rather
    than blocking SEO generation."""
    try:
        from core.brand_aware_prompts import get_video_cta_text
        return get_video_cta_text(long=False)
    except Exception as exc:  # noqa: BLE001
        logger.warning("seo_optimizer: video CTA unavailable: %s", exc)
        return ""


def _get_pinned_comment_cta() -> str:
    """Fetches the ready-to-use pinned comment CTA from
    core.brand_aware_prompts. Never raises -- returns "" if unavailable."""
    try:
        from core.brand_aware_prompts import get_pinned_comment_cta
        return get_pinned_comment_cta()
    except Exception as exc:  # noqa: BLE001
        logger.warning("seo_optimizer: pinned comment CTA unavailable: %s", exc)
        return ""


_CTA_PLACEHOLDER_MARKER = "[CONTACT INFO NOT YET CONFIGURED"


def _is_unconfigured_placeholder(text: str) -> bool:
    """True if `text` is brand_aware_prompts' known placeholder for an
    unconfigured lead_capture.yaml contact field. Per
    BRAND_INTEGRATION_SNIPPET.md: never ship this placeholder in real
    output, so callers should skip appending it."""
    return _CTA_PLACEHOLDER_MARKER in text


def _build_system_prompt(channel) -> str:
    brand_block = _get_brand_style_block()
    base = (
        "You are a YouTube SEO specialist. Given a video script, generate metadata "
        "that maximizes click-through rate and search discoverability while staying "
        "accurate to the content. Respond with ONLY valid JSON, no markdown fences, "
        "matching this exact shape:\n"
        '{"title": str, "description": str, "tags": [str, ...], '
        '"hashtags": [str, ...], "pinned_comment": str, "end_screen_topics": [str, ...]}\n\n'
        f"Channel niche: {getattr(channel, 'niche', 'general')}. "
        f"Title must be {MAX_TITLE_CHARS} characters or fewer. "
        f"Tags combined must be {MAX_TAGS_CHARS} characters or fewer. "
        "pinned_comment must be under 200 characters and should seed replies/engagement. "
        "Include 3-5 relevant hashtags. Weave in chapter timestamps into the description "
        "if chapter markers are provided. Do NOT invent or include any contact info, "
        "links, or calls-to-action in the description or pinned_comment -- those are "
        "appended separately after generation."
    )
    if not brand_block:
        return base
    return (
        f"{base}\n\n"
        f"Brand voice/tone for this copy (from the shared marketing-ops brand identity):"
        f"\n{brand_block}"
    )


def _build_user_prompt(script: dict, chapter_markers: Optional[list]) -> str:
    parts = [
        f"Hook: {script.get('hook', '')}",
        f"SEO keywords: {', '.join(script.get('seo_keywords', []))}",
    ]
    scenes = script.get("scenes", [])
    if scenes:
        summary = " | ".join(s.get("narration", "")[:80] for s in scenes[:5])
        parts.append(f"Scene summary: {summary}")

    if chapter_markers:
        chapters_str = "; ".join(
            f"{int(m['timestamp_seconds'] // 60):02d}:{int(m['timestamp_seconds'] % 60):02d} {m['title']}"
            for m in chapter_markers
        )
        parts.append(f"Chapter markers: {chapters_str}")

    return "\n".join(parts)


def _truncate(text: str, max_chars: int) -> str:
    return text if len(text) <= max_chars else text[: max_chars - 1].rstrip() + "\u2026"


def _validate(data: dict) -> None:
    required = ("title", "description", "tags", "hashtags", "pinned_comment")
    missing = [k for k in required if k not in data]
    if missing:
        raise ValueError(f"SEO response missing required fields: {missing}")
    if not isinstance(data["tags"], list) or not isinstance(data["hashtags"], list):
        raise ValueError("'tags' and 'hashtags' must be lists")
    if not data["title"].strip():
        raise ValueError("'title' must not be empty")


def optimize_seo(
    client: ChatClient,
    channel,
    script: dict,
    chapter_markers: Optional[list] = None,
) -> SEOResult:
    """
    Generate SEO metadata for a finished video.

    Args:
        client: injected ChatClient (real OpenAI wrapper or fake for tests),
            using the SAME create_chat_completion(model=, messages=,
            response_format=) protocol as core.script_writer.ChatClient.
        channel: ChannelConfig instance (used for niche context).
        script: the script dict produced by script_writer.py (hook, scenes,
            seo_keywords, etc).
        chapter_markers: optional list of {timestamp_seconds, title} dicts
            from video_assembler.build_chapter_markers().

    Returns:
        SEOResult with title/description/tags/hashtags/pinned_comment/
        end_screen_topics, all length-capped per README limits. The
        description and pinned_comment have the brand CTA appended, unless
        the CTA is unavailable or still an unconfigured placeholder.

    Raises:
        SEOGenerationError: if valid JSON could not be produced after
        MAX_RETRIES attempts.
    """
    system_prompt = _build_system_prompt(channel)
    user_prompt = _build_user_prompt(script, chapter_markers)

    last_error: Optional[Exception] = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            raw = client.create_chat_completion(
                model=MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
            )
            data = json.loads(raw)
            _validate(data)

            tags = data["tags"]
            tags_str = ",".join(tags)
            if len(tags_str) > MAX_TAGS_CHARS:
                while len(",".join(tags)) > MAX_TAGS_CHARS and tags:
                    tags.pop()

            description = data["description"].strip()
            cta_text = _get_video_cta()
            if cta_text and not _is_unconfigured_placeholder(cta_text):
                description = f"{description}\n\n{cta_text}"

            pinned_comment = _truncate(data["pinned_comment"].strip(), 200)
            pinned_cta = _get_pinned_comment_cta()
            if pinned_cta and not _is_unconfigured_placeholder(pinned_cta):
                combined = f"{pinned_comment} {pinned_cta}".strip()
                pinned_comment = _truncate(combined, 200)

            return SEOResult(
                title=_truncate(data["title"].strip(), MAX_TITLE_CHARS),
                description=description,
                tags=tags,
                hashtags=data["hashtags"],
                pinned_comment=pinned_comment,
                end_screen_topics=data.get("end_screen_topics", []),
            )
        except (json.JSONDecodeError, ValueError, KeyError) as exc:
            last_error = exc
            logger.warning("[seo_optimizer] Attempt %d/%d failed: %s", attempt, MAX_RETRIES, exc)

    raise SEOGenerationError(
        f"Failed to generate valid SEO metadata after {MAX_RETRIES} attempts: {last_error}"
    )
