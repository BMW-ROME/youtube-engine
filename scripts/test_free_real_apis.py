"""
scripts/test_free_real_apis.py

Real (non-fake) integration test for script_writer.py, seo_optimizer.py,
and image_gen.py -- using $0 local substitutes instead of real OpenAI/
DALL-E credits:

    - script_writer.py / seo_optimizer.py: pointed at a LOCAL OLLAMA model
      via its OpenAI-compatible /v1/chat/completions endpoint, using the
      exact same ChatClient protocol (create_chat_completion(model=,
      messages=, response_format=)) as the real OpenAIChatClient. This
      exercises real JSON parsing, real validation, and the real retry
      logic against real (if lower-quality) LLM output -- not a scripted
      fake string.

    - image_gen.py: pointed at a local "SometimesFailsImageClient" that
      deterministically rejects prompts containing trigger words (mimicking
      a real content-filter rejection) so the sanitize -> retry -> fallback
      chain runs against real control flow, without needing a paid image
      model to prove it works.

Prerequisites:
    - Ollama running locally (`ollama serve`) with a model pulled that
      supports JSON mode reasonably well (qwen2.5-coder:3B is proven to
      satisfy the strict script/SEO schema), e.g.:
          ollama pull qwen2.5-coder:3B
    - requests installed (already a project dependency)

Usage:
    python scripts/test_free_real_apis.py --model qwen2.5-coder:3B
    python scripts/test_free_real_apis.py --model qwen2.5-coder:3B --ollama-url http://localhost:11434

This costs nothing and never touches OPENAI_API_KEY.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure the repo root (parent of scripts/) is importable as `core`/`config`
# when this file is run directly (python scripts/test_free_real_apis.py) --
# Python only auto-adds the SCRIPT'S OWN directory to sys.path, not its
# parent, so without this, `from core.script_writer import ...` fails with
# ModuleNotFoundError no matter what directory you run this from.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class OllamaChatClient:
    """Matches the ChatClient protocol used by script_writer.py and
    seo_optimizer.py (create_chat_completion(model=, messages=,
    response_format=)), backed by a local Ollama instance instead of
    OpenAI. Zero cost, runs entirely on your own machine."""

    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url.rstrip("/")

    def create_chat_completion(self, *, model: str, messages: list[dict[str, str]],
                                response_format: dict[str, str]) -> str:
        import requests

        # Ollama's OpenAI-compatible endpoint accepts the same shape as the
        # real OpenAI client, including response_format={"type": "json_object"}.
        resp = requests.post(
            f"{self.base_url}/v1/chat/completions",
            json={
                "model": model,
                "messages": messages,
                "response_format": response_format,
            },
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


class SometimesFailsImageClient:
    """Deterministic local stand-in for image_gen.ImageClient. Rejects any
    prompt containing a trigger word (mimicking DALL-E's content filter),
    so the real sanitize -> retry -> placeholder chain in image_gen.py
    actually exercises its control flow against real rejections, not a
    scripted always-fail/always-succeed mock. Costs nothing, no network."""

    TRIGGER_WORDS = ("violent", "violence", "weapon", "blood")

    def generate_image(self, *, model: str, prompt: str, size: str) -> bytes:
        lowered = prompt.lower()
        if any(w in lowered for w in self.TRIGGER_WORDS):
            raise ValueError(f"content_policy_violation: prompt contains trigger word")
        # "success" -> return a tiny valid-looking PNG stub so downstream
        # Path.write_bytes() calls succeed without needing a real image.
        return b"\x89PNG\r\n\x1a\n" + prompt.encode("utf-8")[:64]


def test_script_writer(ollama_model: str, ollama_url: str) -> None:
    from core.script_writer import generate_script
    from config.channels import get_channel

    print("=" * 60)
    print("TEST 1: script_writer.py against local Ollama (real LLM call, $0)")
    print("=" * 60)

    channel = get_channel("finance")
    client = OllamaChatClient(base_url=ollama_url)

    try:
        script = generate_script(
            channel=channel,
            topic="3 index funds that quietly outperform the S&P 500",
            client=client,
        )
    except Exception as exc:
        print(f"[FAIL] script_writer raised: {exc}")
        print("       (If this is a JSON parsing error, your local model may not")
        print("        support strict JSON mode well -- try a larger/instruct model.)")
        raise

    print(f"[PASS] hook: {script.hook!r}")
    print(f"[PASS] {len(script.scenes)} scenes generated")
    print(f"[PASS] outro: {script.outro!r}")
    print(f"[PASS] seo_keywords: {script.seo_keywords}")
    print()
    print(">>> READ THE HOOK/SCENES ABOVE. Does it sound like your brand voice?")
    print(">>> (This is the judgment call no fake client can make for you.)")
    print()
    return script


def test_seo_optimizer(script, ollama_model: str, ollama_url: str) -> None:
    from core.seo_optimizer import optimize_seo
    from config.channels import get_channel

    print("=" * 60)
    print("TEST 2: seo_optimizer.py against local Ollama (real LLM call, $0)")
    print("=" * 60)

    channel = get_channel("finance")
    client = OllamaChatClient(base_url=ollama_url)

    try:
        seo = optimize_seo(client=client, channel=channel, script=script.to_dict())
    except Exception as exc:
        print(f"[FAIL] seo_optimizer raised: {exc}")
        raise

    print(f"[PASS] title ({len(seo.title)} chars): {seo.title!r}")
    print(f"[PASS] description:\n{seo.description}\n")
    print(f"[PASS] pinned_comment: {seo.pinned_comment!r}")
    print(f"[PASS] tags: {seo.tags}")
    print()
    print(">>> Check: did the real CTA get appended to the description/pinned_comment?")
    print(">>> (Only fires if marketing-ops brand sync + lead_capture.yaml CTA are live.)")
    print()


def test_image_gen() -> None:
    from core.image_gen import generate_images
    from core.script_writer import Script, Scene
    from config.channels import get_channel

    print("=" * 60)
    print("TEST 3: image_gen.py resilience chain, local-only, $0")
    print("=" * 60)

    channel = get_channel("finance")
    script = Script(
        hook="test",
        scenes=[
            Scene(narration="n1", visual_description="a clean bar chart, safe prompt"),
            Scene(narration="n2", visual_description="a violent car crash scene"),  # triggers rejection
        ],
        outro="test",
    )

    result = generate_images(channel, script, client=SometimesFailsImageClient())

    print(f"[PASS] {len(result.images)} image results")
    for img in result.images:
        kind = "PLACEHOLDER (rejected, sanitize/retry exhausted)" if img.was_placeholder else "REAL (client succeeded)"
        print(f"       scene {img.scene_index}: {kind} -> {img.output_path}")
    print(f"[PASS] placeholder_count: {result.placeholder_count}")
    print()
    print(">>> Scene 0 (safe prompt) should be REAL. Scene 1 (violent) should be")
    print(">>> PLACEHOLDER only if sanitize didn't remove 'violent' -- check the log")
    print(">>> above for whether sanitize recovered it on attempt 2.")


def main():
    parser = argparse.ArgumentParser(description="Free real-API smoke test using local Ollama.")
    parser.add_argument("--model", default="qwen2.5-coder:3B", help="Ollama model name (must be pulled already; qwen2.5-coder:3B is proven to satisfy the strict script/SEO JSON schema)")
    parser.add_argument("--ollama-url", default="http://localhost:11434", help="Ollama server URL")
    parser.add_argument("--skip-llm", action="store_true", help="Skip Ollama tests, run only image_gen test")
    args = parser.parse_args()

    # The stages send settings.llm_model (default gpt-4o). Ollama rejects a
    # model name it doesn't host, so --model must be surfaced through LLM_MODEL
    # BEFORE config.settings.Settings() is first instantiated by the stages.
    import os
    os.environ["LLM_MODEL"] = args.model

    print("This test costs $0.00 -- no OPENAI_API_KEY or paid API is used.\n")

    try:
        if not args.skip_llm:
            script = test_script_writer(args.model, args.ollama_url)
            test_seo_optimizer(script, args.model, args.ollama_url)
        test_image_gen()
    except Exception:
        print("\n[FAIL] One or more tests raised an exception. See above.")
        sys.exit(1)

    print("\nAll free real-API tests completed.")


if __name__ == "__main__":
    main()
