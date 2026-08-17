"""
config/brand_loader.py

Loads the canonical brand identity from the shared `marketing-ops` repo
(BMW-ROME/marketing-ops/brand_identity.yaml) so that youtube-engine never
hardcodes tone, voice descriptors, niches, or copy rules locally.

Usage:
    from config.brand_loader import get_brand_identity

    brand = get_brand_identity()
    tone = brand["voice_tone"]["primary_descriptors"]  # ["versatile", "deep", "warm", "hypnotic"]
    niches = brand["niches"]["primary"]
    dos = brand["language_rules"]["do"]
    donts = brand["language_rules"]["dont"]

Design notes:
- Fetches brand_identity.yaml from the marketing-ops GitHub repo via the
  raw content API, with a local on-disk cache as a fallback if the network
  call fails (rate limit, offline, auth issue, etc.).
- Never raises on failure to fetch; falls back to cached copy, then to a
  minimal built-in default so pipeline stages relying on this don't crash.
- Does NOT pull anything trading-related -- marketing-ops brand_identity.yaml
  explicitly excludes trading workflows from its scope, and this loader
  only reads the single brand file.
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import yaml  # PyYAML
except ImportError:  # pragma: no cover
    yaml = None

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

logger = logging.getLogger(__name__)

BRAND_REPO_OWNER = "BMW-ROME"
BRAND_REPO_NAME = "marketing-ops"
BRAND_FILE_PATH = "brand_identity.yaml"
BRAND_BRANCH = "main"

RAW_URL = (
    f"https://raw.githubusercontent.com/{BRAND_REPO_OWNER}/{BRAND_REPO_NAME}"
    f"/{BRAND_BRANCH}/{BRAND_FILE_PATH}"
)

# Local cache so pipeline runs are resilient to transient network/auth issues.
CACHE_DIR = Path(__file__).resolve().parent / ".brand_cache"
CACHE_FILE = CACHE_DIR / "brand_identity.cache.yaml"
CACHE_TTL_SECONDS = 6 * 60 * 60  # refresh at most every 6 hours

# Minimal built-in fallback so downstream code never crashes even if both
# the network fetch and the local cache are unavailable (e.g. first run,
# no cache yet, no network). Keep this in sync loosely with marketing-ops,
# but marketing-ops/brand_identity.yaml remains the source of truth.
_DEFAULT_BRAND: Dict[str, Any] = {
    "identity": {
        "name": "Tyrie Braxton",
        "role": "Versatile Voice Actor",
        "location": "Laurel, Maryland, US",
    },
    "voice_tone": {
        "primary_descriptors": ["versatile", "deep", "warm", "hypnotic"],
        "register": "conversational, narration, and character-driven",
        "delivery_notes": (
            "Should read as an authentic, original human presence -- never "
            "generic, never obviously AI-written."
        ),
    },
    "canonical_copy": {
        "headline": "Versatile Voice Actor with a Deep, Warm, Hypnotic Tone",
        "bio_short": (
            "A fresh, versatile voice with a deep, warm, and hypnotic tone."
        ),
        "tagline_options": ["Deep. Warm. Hypnotic. Versatile."],
    },
    "niches": {
        "primary": [
            "SaaS explainer videos and product demos",
            "Narration for business/finance/education content and courses",
            "Calm, hypnotic reads for wellness, meditation, and premium brand films",
        ],
        "secondary": [
            "Commercial / conversational reads",
            "Character-driven / narrative reads",
        ],
    },
    "language_rules": {
        "do": [
            "Use specific, outcome-oriented language",
            "Reference niche-specific use cases explicitly",
            "Keep copy original, plain-spoken, and human",
        ],
        "dont": [
            "Do not use generic AI-marketing phrases (e.g. 'unlock', 'supercharge')",
            "Do not invent tone independent of the shared brand file",
        ],
    },
    "_source": "built-in-default (fetch and cache both unavailable)",
}


def _load_cache() -> Optional[Dict[str, Any]]:
    if not CACHE_FILE.exists():
        return None
    try:
        age = time.time() - CACHE_FILE.stat().st_mtime
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) if yaml else json.load(f)
        if data:
            data["_source"] = f"local-cache (age={int(age)}s)"
        return data
    except Exception as exc:  # noqa: BLE001
        logger.warning("brand_loader: failed to read cache: %s", exc)
        return None


def _write_cache(raw_text: str) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            f.write(raw_text)
    except Exception as exc:  # noqa: BLE001
        logger.warning("brand_loader: failed to write cache: %s", exc)


def _cache_is_fresh() -> bool:
    if not CACHE_FILE.exists():
        return False
    return (time.time() - CACHE_FILE.stat().st_mtime) < CACHE_TTL_SECONDS


def _fetch_remote() -> Optional[Dict[str, Any]]:
    if requests is None:
        logger.warning("brand_loader: 'requests' not installed, cannot fetch remote brand file")
        return None
    if yaml is None:
        logger.warning("brand_loader: 'pyyaml' not installed, cannot parse brand file")
        return None

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    headers = {"Authorization": f"token {token}"} if token else {}

    try:
        resp = requests.get(RAW_URL, headers=headers, timeout=8)
        resp.raise_for_status()
        raw_text = resp.text
        data = yaml.safe_load(raw_text)
        if not isinstance(data, dict):
            raise ValueError("brand_identity.yaml did not parse to a dict")
        _write_cache(raw_text)
        data["_source"] = "remote (marketing-ops/brand_identity.yaml)"
        return data
    except Exception as exc:  # noqa: BLE001
        logger.warning("brand_loader: remote fetch failed (%s): %s", RAW_URL, exc)
        return None


def get_brand_identity(force_refresh: bool = False) -> Dict[str, Any]:
    """
    Returns the brand identity dict, preferring (in order):
      1. Fresh remote fetch from marketing-ops (if cache stale or force_refresh)
      2. Local cache (if fetch fails or cache still fresh)
      3. Built-in default (if nothing else is available)

    This function never raises -- pipeline stages can call it unconditionally.
    """
    if force_refresh or not _cache_is_fresh():
        remote = _fetch_remote()
        if remote:
            return remote

    cached = _load_cache()
    if cached:
        return cached

    logger.warning("brand_loader: falling back to built-in default brand identity")
    return _DEFAULT_BRAND


def get_voice_tone_descriptors() -> list:
    """Convenience accessor: ['versatile', 'deep', 'warm', 'hypnotic']"""
    brand = get_brand_identity()
    return brand.get("voice_tone", {}).get("primary_descriptors", [])


def get_language_rules() -> Dict[str, list]:
    """Convenience accessor: {'do': [...], 'dont': [...]}"""
    brand = get_brand_identity()
    return brand.get("language_rules", {"do": [], "dont": []})


def get_primary_niches() -> list:
    """Convenience accessor: list of primary content/voice niches."""
    brand = get_brand_identity()
    return brand.get("niches", {}).get("primary", [])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    b = get_brand_identity(force_refresh=True)
    print(f"Loaded brand identity from: {b.get('_source', 'unknown')}")
    print(f"Tone descriptors: {get_voice_tone_descriptors()}")
    print(f"Primary niches: {get_primary_niches()}")
