from __future__ import annotations

import base64
import io
import sys
import wave
from pathlib import Path

# Ensure the repo root (parent of scripts/) is importable as `core`/`config`
# when this file is run directly (python scripts/test_pipeline_integration.py) --
# Python only auto-adds the SCRIPT'S OWN directory to sys.path, not its parent,
# so without this, `from core.pipeline import ...` fails with
# ModuleNotFoundError no matter what directory you run this from.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Tiny valid 1x1 transparent PNG (fallback if Pillow is unavailable).
_MINIMAL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _fake_png(size: str = "1024x1024") -> bytes:
    """Return valid PNG bytes so real ffmpeg stages can decode the image."""
    try:
        from PIL import Image, ImageDraw

        w, h = (int(part) for part in size.split("x"))
        img = Image.new("RGB", (w, h), (28, 40, 64))
        ImageDraw.Draw(img).ellipse((0, 0, w, h), fill=(210, 130, 50))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:  # noqa: BLE001 - Pillow is optional-ish here; use fallback
        return _MINIMAL_PNG


def _fake_wav(seconds: float = 0.5, rate: int = 16000) -> bytes:
    """Return valid (silent) WAV bytes so ffmpeg can decode the voice track."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(rate * seconds))
    return buf.getvalue()


class FakeScriptClient:
    """Matches the UNIFIED ChatClient protocol (create_chat_completion(model=,
    messages=, response_format=)) and returns a Script-shaped JSON object that
    satisfies script_writer._validate_script (>=3 scenes, non-empty fields)."""

    def create_chat_completion(self, *, model, messages, response_format):
        import json
        return json.dumps({
            "hook": "These 3 index funds quietly beat the market for 20 straight years.",
            "scenes": [
                {"narration": "Scene one explains what an index fund actually is.",
                 "visual_description": "A clean growth chart of an index fund."},
                {"narration": "Scene two breaks down expense ratios and fees.",
                 "visual_description": "A magnifying glass over a fee table."},
                {"narration": "Scene three shows how to start investing today.",
                 "visual_description": "A simple step-by-step investment checklist."},
            ],
            "outro": "Like and subscribe for more investing breakdowns.",
            "seo_keywords": ["index funds", "investing", "retirement"],
            "chapter_timestamps": [
                {"time": "00:00", "title": "Intro"},
                {"time": "00:15", "title": "Fund 1"},
            ],
            "affiliate_slots": [],
        })


class FakeSynthesizer:
    """Implements voice_gen.Synthesizer: synthesize(text, voice_id, output_path).
    Writes real WAV bytes so downstream ffmpeg can decode the track."""

    def synthesize(self, text: str, voice_id: str, output_path: Path) -> None:
        Path(output_path).write_bytes(_fake_wav())


class FakeConcatenator:
    """Implements voice_gen.AudioConcatenator: concatenate(input_paths, output).
    Concatenates the (silent) segments into one WAV track."""

    def concatenate(self, input_paths: list[Path], output_path: Path) -> None:
        frames = b"".join(Path(p).read_bytes() if p.exists() else b"" for p in input_paths)
        Path(output_path).write_bytes(frames or _fake_wav())


class FakeMixer:
    """Implements music_mixer.AudioMixer: mix(voice_path, music_path, output_path,
    music_volume). Writes a valid WAV so assembly can still read the track."""

    def mix(
        self, voice_path: Path, music_path: Path, output_path: Path, music_volume: float
    ) -> None:
        Path(output_path).write_bytes(_fake_wav())


class FakeImageClient:
    """Implements image_gen.ImageClient: generate_image(model, prompt, size).
    Returns a real PNG so the kenburns/sketch effect stages can decode it."""

    def generate_image(self, *, model, prompt, size):
        return _fake_png(size)


class FakePlaceholderGenerator:
    """Implements image_gen.PlaceholderGenerator: generate(size) -> bytes."""

    def generate(self, size: str = "1024x1024") -> bytes:
        return _fake_png(size)


class FakeSEOChatClient:
    """Matches the UNIFIED ChatClient protocol shared by script_writer.py
    and seo_optimizer.py: create_chat_completion(model=, messages=,
    response_format=). Fixed 2026-08-16 -- seo_optimizer.py previously used
    a different, incompatible .complete(system, user) shape."""

    def create_chat_completion(self, *, model, messages, response_format):
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

    def create_chat_completion(self, *, model, messages, response_format):
        raise RuntimeError("simulated SEO API outage")


def _fake_clients(seo_client=None) -> dict:
    """Every external backend injected as a fake: script, voice, music, images,
    and SEO. Only ffmpeg remains real (it processes the fake PNG/WAV files)."""
    return {
        "script_chat_client": FakeScriptClient(),
        "synthesizer": FakeSynthesizer(),
        "concatenator": FakeConcatenator(),
        "mixer": FakeMixer(),
        "image_client": FakeImageClient(),
        "placeholder_gen": FakePlaceholderGenerator(),
        "seo_chat_client": seo_client or FakeSEOChatClient(),
    }


def test_happy_path() -> None:
    from core.pipeline import run_pipeline

    result = run_pipeline(
        topic="3 Index Funds That Beat the S&P 500",
        channel_codename="finance",
        config={"upload_mode": "local"},
        clients=_fake_clients(),
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
        config={"upload_mode": "local"},
        clients=_fake_clients(seo_client=FailingSEOChatClient()),
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


def test_get_next_topic_retry_queue() -> None:
    """Confirms content_db.get_next_topic() (added 2026-08-16 to fix
    orchestrator.py's previously-nonexistent call) actually returns the
    oldest FAILED video's topic when one exists, and None otherwise.
    Uses a dedicated test channel so pre-existing FAILED rows in the real
    content.db can't break the assertions."""
    from core import content_db

    test_channel = "__retry_test__"
    content_db.init_db()
    # Remove any rows a previous run of this test left behind (the channel is
    # unique to this test, so real videos are never touched).
    with content_db.get_connection() as conn:
        conn.execute("DELETE FROM videos WHERE channel = ?", (test_channel,))
    assert content_db.get_next_topic(channel=test_channel) is None, (
        "Expected None with no FAILED videos for the test channel yet"
    )

    vid = content_db.create_video(channel=test_channel, topic="Topic needing retry")
    content_db.update_status(vid, "FAILED", error_message="simulated failure")

    next_topic = content_db.get_next_topic(channel=test_channel)
    assert next_topic == "Topic needing retry", f"Expected retry topic, got {next_topic!r}"
    print("[PASS] test_get_next_topic_retry_queue: FAILED video topic correctly surfaced for retry")


if __name__ == "__main__":
    try:
        test_happy_path()
        test_non_required_stage_failure_is_survivable()
        test_get_next_topic_retry_queue()
    except AssertionError as exc:
        print(f"[FAIL] {exc}")
        sys.exit(1)
    print("\nAll integration tests passed.")