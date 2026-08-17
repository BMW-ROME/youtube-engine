"""
core/brand_aware_prompts.py

Thin integration layer between the marketing-ops brand/CTA config and the
content-generation stages (script_writer.py, seo_optimizer.py).

This module exists so those two files can be wired to brand_identity.yaml
and lead_capture.yaml with a SINGLE import + SINGLE function call each,
without needing to know the internals of config/brand_loader.py or fetch
lead_capture.yaml themselves. Kept separate from brand_loader.py so the
"fetch raw config" concern and the "build a prompt-ready text block" concern
don't live in the same function.

Usage in script_writer.py:

    from core.brand_aware_prompts import get_script_style_block
    style_block = get_script_style_block()
    # fold `style_block` into the existing system/style prompt construction

Usage in seo_optimizer.py:

    from core.brand_aware_prompts import get_seo_style_block, get_video_cta_text
    style_block = get_seo_style_block()
    cta_text = get_video_cta_text(long=False)
    # fold `style_block` into the SEO prompt; append `cta_text` to the
    # generated video description
"""

import logging
import os
from typing import Any, Dict

import requests
import yaml

from config.brand_loader import get_brand_identity

logger = logging.getLogger(__name__)

LEAD_CAPTURE_REPO_OWNER = "BMW-ROME"
LEAD_CAPTURE_REPO_NAME = "marketing-ops"
LEAD_CAPTURE_FILE_PATH = "lead_capture.yaml"
LEAD_CAPTURE_BRANCH = os.environ.get("BRAND_IDENTITY_BRANCH", "main")

LEAD_CAPTURE_RAW_URL = (
    f"https://raw.githubusercontent.com/{LEAD_CAPTURE_REPO_OWNER}/{LEAD_CAPTURE_REPO_NAME}"
    f"/{LEAD_CAPTURE_BRANCH}/{LEAD_CAPTURE_FILE_PATH}"
)

_DEFAULT_LEAD_CAPTURE: Dict[str, Any] = {
    "funnel": {
        "landing_page_url": "",
        "fallback_contact_method": "",
    },
    "youtube_description_cta": {
        "short": "Need a voice for your next project? Get a quote: {primary_or_fallback_contact}",
        "long": "Need a voice for your next project? Get a quote: {primary_or_fallback_contact}",
    },
}

_lead_capture_cache: Dict[str, Any] = {}


def _fetch_lead_capture() -> Dict[str, Any]:
    """Fetches lead_capture.yaml from marketing-ops. Mirrors brand_loader's resilience pattern."""
    global _lead_capture_cache
    if _lead_capture_cache:
        return _lead_capture_cache

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    headers = {"Authorization": f"token {token}"} if token else {}

    try:
        resp = requests.get(LEAD_CAPTURE_RAW_URL, headers=headers, timeout=8)
        resp.raise_for_status()
        data = yaml.safe_load(resp.text)
        if isinstance(data, dict):
            _lead_capture_cache = data
            return data
    except Exception as exc:  # noqa: BLE001
        logger.warning("brand_aware_prompts: failed to fetch lead_capture.yaml: %s", exc)

    return _DEFAULT_LEAD_CAPTURE


def _resolve_contact_url(lead_capture: Dict[str, Any]) -> str:
    """Picks landing_page_url if set, else fallback_contact_method, else a placeholder."""
    funnel = lead_capture.get("funnel", {})
    landing = funnel.get("landing_page_url", "").strip()
    if landing:
        return landing
    fallback = funnel.get("fallback_contact_method", "").strip()
    if fallback:
        return fallback
    return "[CONTACT INFO NOT YET CONFIGURED -- see marketing-ops/lead_capture.yaml]"


def get_script_style_block() -> str:
    """
    Returns a text block for script_writer.py's prompt construction, derived
    from brand_identity.yaml's voice_tone and language_rules.
    """
    brand = get_brand_identity()
    tone = brand.get("voice_tone", {})
    descriptors = tone.get("primary_descriptors", [])
    register = tone.get("register", "")
    delivery_notes = tone.get("delivery_notes", "")
    lang_rules = brand.get("language_rules", {"do": [], "dont": []})

    lines = [
        f"Voice/tone: {', '.join(descriptors)}. Register: {register}.",
        delivery_notes.strip(),
        "Do: " + "; ".join(lang_rules.get("do", [])),
        "Don't: " + "; ".join(lang_rules.get("dont", [])),
    ]
    return "\n".join(line for line in lines if line)


def get_seo_style_block() -> str:
    """
    Returns a text block for seo_optimizer.py's prompt construction --
    same tone/language rules as get_script_style_block(), plus the niches
    to favor when relevant to the video's subject matter.
    """
    brand = get_brand_identity()
    tone = brand.get("voice_tone", {})
    descriptors = tone.get("primary_descriptors", [])
    lang_rules = brand.get("language_rules", {"do": [], "dont": []})
    niches = brand.get("niches", {}).get("primary", [])

    lines = [
        f"Voice/tone for title/description copy: {', '.join(descriptors)}.",
        "Do: " + "; ".join(lang_rules.get("do", [])),
        "Don't: " + "; ".join(lang_rules.get("dont", [])),
        "Favor these niches/topics when relevant: " + ", ".join(niches),
    ]
    return "\n".join(line for line in lines if line)


def get_video_cta_text(long: bool = False) -> str:
    """
    Returns the ready-to-append CTA text for a video description, with the
    contact URL/placeholder already substituted in from lead_capture.yaml.
    """
    lead_capture = _fetch_lead_capture()
    contact = _resolve_contact_url(lead_capture)
    cta_block = lead_capture.get("youtube_description_cta", {})
    template = cta_block.get("long" if long else "short", "")
    if not template:
        return ""
    return template.replace("{primary_or_fallback_contact}", contact).replace(
        "{primary_or_fallback_url}", contact
    )


def get_pinned_comment_cta() -> str:
    """Returns the short pinned-comment CTA text, if configured."""
    lead_capture = _fetch_lead_capture()
    return lead_capture.get("pinned_comment_cta", {}).get("short", "")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("--- script style block ---")
    print(get_script_style_block())
    print("\n--- seo style block ---")
    print(get_seo_style_block())
    print("\n--- video CTA (short) ---")
    print(get_video_cta_text(long=False))
    print("\n--- pinned comment CTA ---")
    print(get_pinned_comment_cta())
