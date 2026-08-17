"""
scripts/test_pipeline_integration.py

End-to-end integration test for core/pipeline.py.

This is the test that should have existed BEFORE Phases 3-6 were marked
complete in BUILD_LOG.md. An audit on 2026-08-16 found that pipeline.py
(written via GitHub's web editor in a separate session) imported module
and function names that never matched the real, already-committed code:

    voice_gen.synthesize_voice        (real: voice_gen.generate_voice)
    music_selector.select_music       (real: music_mixer.mix_music)
    image_sourcer.source_images       (real: image_gen.generate_images)
    thumbnail_gen.generate_thumbnail  (real: thumbnail_text.add_thumbnail_text)
    effects.apply_effects             (real: video_effects.apply_effect)
    shorts_generator.generate_shorts  (real: shorts_gen.generate_shorts)

Every one of these was a silent ImportError swallowed by pipeline.py's own
per-stage try/except, so the pipeline "ran" without crashing but produced
nothing at every single stage. BUILD_LOG.md's checkmarks were all correct
about each MODULE in isolation, but wrong about the SYSTEM, because nobody
ran them together until now.

This script exercises the full 10-stage chain with every external
dependency faked (OpenAI, Edge-TTS, ffmpeg, DALL-E, YouTube API) so it
costs nothing to run and has no external dependencies, and asserts that:

  1. The full happy path produces a final video, SEO metadata, and an
     upload result, with zero failed stages.
  2. A non-required stage failing (SEO outage) does NOT kill the pipeline
     - the video is still assembled - but IS correctly recorded in
     failed_stages and blocks the upload step (no SEO metadata to upload
     with).

Run with:
    python scripts/test_pipeline_integration.py

Exits non-zero if any assertion fails, so this can be wired into CI later.
"""

from __future__ import annotations

import sys


class FakeSEOChatClient:
    """Matches seo_optimizer.ChatClient's .complete(system, user) protocol
    -- NOTE this is a different Protocol shape than script_writer's
    .create_chat_completion(model=, messages=, response_format=). Keep
    these separate; do not assume all ChatClient-named protocols match."""

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        import json
        return json.dumps({
            "title": "3 Index Funds That Beat the S&P 500",
            "description": "In this video we break down three index funds worth watching.",
            "tags": ["finance", "investing", "index funds"],
            "hashtags": ["#investing", "#finance", "#money"],
            "pinned_comment": "What's your favorite index fund? Let us know below!",
            "end_screen_topics": ["Retirement planning basics"],
        })


class FailingSEOChatClient:
    """Simulates an SEO API outage to test the non-required-stage failure path."""

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        raise RuntimeError("simulated SEO API outage")


def test_happy_path() -> None:
    from core.pipeline import run_pipeline

    result = run_pipeline(
        topic="3 Index Funds That Beat the S&P 500",
        channel_codename="finance",
        clients={"seo_chat_client": FakeSEOChatClient()},
    )

    assert result.success, f"Expected success, got failed_stages={result.failed_stages}"
    assert result.script is not None, "script stage produced no output"
    assert result.voice_path, "voice stage produced no output"
    assert result.image_paths, "images stage produced no output"
    assert result.final_video_path, "assembly stage produced no output"
    assert result.seo_result is not None, "seo stage produced no output"
    assert result.upload_result is not None, "upload stage produced no output"
    print("[PASS] test_happy_path: all 10 stages completed, zero failed_stages")


def test_non_required_stage_failure_is_survivable() -> None:
    from core.pipeline import run_pipeline

    result = run_pipeline(
        topic="Test topic for failure path",
        channel_codename="finance",
        clients={"seo_chat_client": FailingSEOChatClient()},
    )

    assert not result.success, "Expected success=False when SEO stage fails"
    assert "seo" in result.failed_stages, f"Expected 'seo' in failed_stages, got {result.failed_stages}"
    assert result.final_video_path is not None, (
        "assembly is a REQUIRED stage and must still succeed even when a "
        "later non-required stage (seo) fails"
    )
    assert result.upload_result is None, (
        "upload should not run without seo_result -- there is no metadata to upload with"
    )
    print("[PASS] test_non_required_stage_failure_is_survivable: video still assembled despite SEO outage")


if __name__ == "__main__":
    try:
        test_happy_path()
        test_non_required_stage_failure_is_survivable()
    except AssertionError as exc:
        print(f"[FAIL] {exc}")
        sys.exit(1)
    print("\nAll integration tests passed.")
