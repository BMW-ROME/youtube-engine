"""
scripts/validate_e2e.py

Real end-to-end validation of the ACTUAL files in this repo checkout --
not a reconstruction, not a memory of the repo, not a sandbox stand-in.
This script runs from your repo root, imports your real core/ and config/
modules exactly as start_engine.py does, and drives the real 10-stage
pipeline through core/pipeline.run_pipeline() with ONLY the paid network
boundary faked (OpenAI chat completions, OpenAI image generation) so the
run costs $0 -- but every import, every function call, every file write
in between is 100% your real code, not a stand-in.

Why this exists: prior validation in this project happened by hand-copying
file contents into an isolated sandbox from memory/prior tool output. That
approach already produced one transcription error (a mis-escaped regex)
that had to be caught and corrected. Running actual imports against your
actual files removes that entire class of risk -- whatever this script
reports is true of YOUR checkout, not of anyone's memory of it.

What this fakes (network boundary only, never business logic):
    - OpenAI chat completions (script_writer.py, seo_optimizer.py) -- a
      fake httpx transport intercepts the HTTP call the real openai SDK
      makes and returns a valid JSON response, so OpenAIChatClient's real
      code runs untouched, only the actual network request is short-circuited.
    - OpenAI image generation (image_gen.py) -- same pattern, fake image
      bytes returned instead of a real DALL-E call.
    - Edge-TTS / ffmpeg / Pillow are NOT faked -- if you have ffmpeg and
      edge-tts installed (per scripts/verify_environment.py), this exercises
      the REAL audio synthesis, REAL video assembly, REAL thumbnail overlay.
    - Chatterbox is NOT exercised unless you've completed scripts/setup_voice.py
      and set CHATTERBOX_VOICE_SAMPLE_PATH -- this script uses the "finance"
      channel (Edge-TTS) by default specifically to avoid requiring GPU/model
      weights just to validate the pipeline shape.
    - Upload is forced to UPLOAD_MODE=local for this run regardless of your
      .env, so nothing is ever actually uploaded to YouTube during validation.

Usage (from repo root, with your real .env containing OPENAI_API_KEY set
to ANY non-empty string -- it is never actually sent anywhere real):
    python scripts/validate_e2e.py
    python scripts/validate_e2e.py --channel finance --topic "test topic"
    python scripts/validate_e2e.py --category "true crime" --topic "test"

Exit code 0 only if every stage that SHOULD have run (given your installed
optional deps) actually succeeded. Prints a per-stage report either way.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# Ensure repo root is importable, same fix applied to scripts/start_engine.py,
# scripts/run_once.py, scripts/setup_voice.py.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("validate_e2e")

# Force a harmless OPENAI_API_KEY if none is set, so config.settings.Settings()
# doesn't fail validation before we even get a chance to fake the network call.
os.environ.setdefault("OPENAI_API_KEY", "sk-validation-run-not-sent-anywhere")
os.environ["UPLOAD_MODE"] = "local"  # never actually upload during validation


def install_fake_openai_transport():
    """
    Monkeypatches the REAL openai SDK's HTTP transport so
    core.script_writer.OpenAIChatClient and core.seo_optimizer's real
    create_chat_completion() calls run their real code (build request,
    parse response, validate schema, retry logic) but the actual HTTP
    request never leaves this machine and costs $0.

    This patches at the httpx transport layer (what the openai SDK uses
    internally), NOT by replacing OpenAIChatClient itself -- so if
    OpenAIChatClient's real implementation has a bug in how it builds
    the request or parses the response, this WILL catch it, unlike a
    fake ChatClient that bypasses OpenAIChatClient entirely.
    """
    try:
        import httpx
    except ImportError:
        logger.error("httpx not installed -- cannot install fake transport. Install project requirements first.")
        raise

    fake_script_response = {
        "id": "chatcmpl-fake", "object": "chat.completion", "created": 0, "model": "gpt-4o",
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": json.dumps({
                    "hook": "What if everything you knew about saving money was backwards?",
                    "scenes": [
                        {"narration": "Most advice says save first, spend later. The wealthy do the opposite.",
                         "visual_description": "Clean financial infographic, split screen comparison"},
                        {"narration": "They automate investing before a single bill is paid.",
                         "visual_description": "Diagram of automatic transfer into an index fund"},
                        {"narration": "That habit compounds into real wealth with zero extra effort.",
                         "visual_description": "Growth chart climbing over a ten year timeline"},
                    ],
                    "outro": "Automate it once, and the system builds wealth for you.",
                    "seo_keywords": ["personal finance", "investing", "index funds"],
                    "chapter_timestamps": [{"time": "00:00", "title": "The Backwards Rule"}],
                    "affiliate_slots": ["AFFILIATE_FINANCE_1"],
                }),
            },
            "finish_reason": "stop",
        }],
    }

    fake_seo_response = {
        "id": "chatcmpl-fake2", "object": "chat.completion", "created": 0, "model": "gpt-4o",
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": json.dumps({
                    "title": "3 Index Funds That Quietly Beat the Market",
                    "description": "In this video we break down index funds worth watching in 2026.",
                    "tags": ["finance", "investing", "index funds"],
                    "hashtags": ["#investing", "#finance", "#money"],
                    "pinned_comment": "What's your favorite index fund? Drop it below!",
                    "end_screen_topics": ["Retirement planning basics"],
                }),
            },
            "finish_reason": "stop",
        }],
    }

    fake_image_b64 = __import__("base64").b64encode(
        b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    ).decode("ascii")
    fake_image_response = {"created": 0, "data": [{"b64_json": fake_image_b64}]}

    call_count = {"chat": 0}

    class FakeTransport(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if "chat/completions" in path:
                call_count["chat"] += 1
                # First distinct call is treated as script_writer, subsequent
                # distinct system-prompt content routes to seo_optimizer --
                # we detect by looking at the request body's system prompt.
                try:
                    body = json.loads(request.content.decode("utf-8"))
                    system_msg = next(
                        (m["content"] for m in body.get("messages", []) if m.get("role") == "system"), ""
                    )
                except Exception:
                    system_msg = ""
                if "SEO specialist" in system_msg:
                    payload = fake_seo_response
                else:
                    payload = fake_script_response
                return httpx.Response(200, json=payload, request=request)
            if "images/generations" in path:
                return httpx.Response(200, json=fake_image_response, request=request)
            return httpx.Response(404, json={"error": "unhandled fake endpoint"}, request=request)

    import openai
    original_init = openai.OpenAI.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["http_client"] = httpx.Client(transport=FakeTransport())
        original_init(self, *args, **kwargs)

    openai.OpenAI.__init__ = patched_init
    logger.info("Installed fake OpenAI network transport (real SDK code runs, $0 network calls).")


def run_validation(channel_codename: str | None, category: str | None, topic: str) -> bool:
    install_fake_openai_transport()

    from core.pipeline import run_pipeline

    if category:
        from core.freestyle import build_freestyle_channel
        from config.channels import CHANNELS
        channel = build_freestyle_channel(category, video_mode="kenburns")
        CHANNELS[channel.codename] = channel
        channel_codename = channel.codename

    logger.info("=" * 60)
    logger.info("Starting REAL end-to-end pipeline run (channel=%r, topic=%r)", channel_codename, topic)
    logger.info("This uses your ACTUAL core/ and config/ files, real ffmpeg/Pillow/Edge-TTS")
    logger.info("if installed, and a faked OpenAI network transport (real SDK code, $0 cost).")
    logger.info("=" * 60)

    result = run_pipeline(topic=topic, channel_codename=channel_codename)

    print()
    print("=" * 60)
    print("STAGE-BY-STAGE REPORT")
    print("=" * 60)
    stages = [
        ("1. Script (script_writer.py)", result.script is not None),
        ("2. Voice (voice_gen.py)", bool(result.voice_path)),
        ("3. Music (music_mixer.py)", result.music_path is not None),
        ("4. Images (image_gen.py)", bool(result.image_paths)),
        ("5. Thumbnail (thumbnail_text.py)", result.thumbnail_path is not None),
        ("6. Effects (video_effects.py)", bool(result.effect_clip_paths)),
        ("7. Assembly (video_assembler.py) [REQUIRED]", bool(result.final_video_path)),
        ("8. SEO (seo_optimizer.py)", result.seo_result is not None),
        ("9. Shorts (shorts_gen.py)", bool(result.shorts_paths) or "shorts" not in result.failed_stages),
        ("10. Upload (pipedream_uploader.py)", result.upload_result is not None),
    ]
    for name, ok in stages:
        marker = "PASS" if ok else "SKIP/FAIL"
        print(f"  [{marker:9s}] {name}")

    print()
    print(f"Overall success: {result.success}")
    print(f"Failed stages: {result.failed_stages}")
    if result.final_video_path:
        print(f"Final video written to: {result.final_video_path}")
        video_exists = Path(result.final_video_path).exists()
        print(f"  -> File actually exists on disk: {video_exists}")
        if video_exists:
            print(f"  -> File size: {Path(result.final_video_path).stat().st_size} bytes")
    if result.upload_result:
        print(f"Upload result (local mode, nothing sent to YouTube): {result.upload_result}")

    print()
    if result.final_video_path and Path(result.final_video_path).exists():
        print(">>> A REAL video file was produced end-to-end from your actual repo code.")
    else:
        print(">>> FAILED: no final video file was produced. Check failed_stages above")
        print(">>> and re-run with real ffmpeg/Pillow installed (scripts/verify_environment.py).")

    return result.success and bool(result.final_video_path) and Path(result.final_video_path or "").exists()


def main():
    parser = argparse.ArgumentParser(description="Real end-to-end $0 validation of the actual repo.")
    parser.add_argument("--channel", default="finance", help="Built-in channel to test (default: finance, Edge-TTS)")
    parser.add_argument("--category", help="Use Freestyle mode instead of --channel")
    parser.add_argument("--topic", default="Validation test run", help="Video topic")
    args = parser.parse_args()

    try:
        ok = run_validation(
            channel_codename=None if args.category else args.channel,
            category=args.category,
            topic=args.topic,
        )
    except Exception:
        logger.exception("Validation run crashed with an unhandled exception")
        sys.exit(1)

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
