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
- Same dependency-injection pattern as script_writer.py: a ChatClient
  protocol is accepted so this module is fully testable with a fake
  client and zero OpenAI API cost.
- Same retry-then-fail resilience: malformed JSON triggers up to 3
  attempts before raising SEOGenerationError.
- Title is hard-capped at 60 chars, tags at 500 chars total, per README.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Protocol

logger = logging.getLogger(__name__)

MAX_TITLE_CHARS = 60
MAX_TAGS_CHARS = 500
MAX_RETRIES = 3


class SEOGenerationError(Exception):
    """Raised when SEO metadata could not be generated after all retries."""


class ChatClient(Protocol):
    """Minimal interface this module needs from an OpenAI-style client,
    matching the protocol used in script_writer.py for consistency."""

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        ...


@dataclass
class SEOResult:
    title: str
    description: str
    tags: List[str]
    hashtags: List[str]
    pinned_comment: str
    end_screen_topics: List[str] = field(default_factory=list)


def _build_system_prompt(channel) -> str:
    return (
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
        "if chapter markers are provided."
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
        client: injected ChatClient (real OpenAI wrapper or fake for tests).
        channel: ChannelConfig instance (used for niche context).
        script: the script dict produced by script_writer.py (hook, scenes,
            seo_keywords, etc).
        chapter_markers: optional list of {timestamp_seconds, title} dicts
            from video_assembler.build_chapter_markers().

    Returns:
        SEOResult with title/description/tags/hashtags/pinned_comment/
        end_screen_topics, all length-capped per README limits.

    Raises:
        SEOGenerationError: if valid JSON could not be produced after
        MAX_RETRIES attempts.
    """
    system_prompt = _build_system_prompt(channel)
    user_prompt = _build_user_prompt(script, chapter_markers)

    last_error: Optional[Exception] = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            raw = client.complete(system_prompt, user_prompt)
            data = json.loads(raw)
            _validate(data)

            tags = data["tags"]
            tags_str = ",".join(tags)
            if len(tags_str) > MAX_TAGS_CHARS:
                while len(",".join(tags)) > MAX_TAGS_CHARS and tags:
                    tags.pop()

            return SEOResult(
                title=_truncate(data["title"].strip(), MAX_TITLE_CHARS),
                description=data["description"].strip(),
                tags=tags,
                hashtags=data["hashtags"],
                pinned_comment=_truncate(data["pinned_comment"].strip(), 200),
                end_screen_topics=data.get("end_screen_topics", []),
            )
        except (json.JSONDecodeError, ValueError, KeyError) as exc:
            last_error = exc
            logger.warning("[seo_optimizer] Attempt %d/%d failed: %s", attempt, MAX_RETRIES, exc)

    raise SEOGenerationError(
        f"Failed to generate valid SEO metadata after {MAX_RETRIES} attempts: {last_error}"
    )
