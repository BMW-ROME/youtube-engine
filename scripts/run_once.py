"""
scripts/run_once.py — Phase 1 "Prove the Loop" tool.

Manually runs the currently-built portion of the pipeline for ONE video on
ONE channel: content_db (create) -> script_writer (Stage 1) -> voice_gen
(Stage 2). This intentionally stops after voice generation — music/images/
assembly/upload don't exist yet (see BUILD_LOG.md Phase 2+).

This is the checkpoint that proves script_writer.py and voice_gen.py, which
were each unit-tested in isolation with fake clients, actually work together
against the real content_db and (optionally) real OpenAI/Edge-TTS calls.

Usage:
    python scripts/run_once.py --channel finance --topic "3 Index Funds That Beat the S&P 500"
    python scripts/run_once.py --channel finance --topic "..." --dry-run   # fake clients, no API cost
"""

from __future__ import annotations

import argparse
import logging
import sys

from config.channels import get_channel
from core import content_db
from core.script_writer import Script, Scene, generate_script, ScriptGenerationError
from core.voice_gen import generate_voice, VoiceGenerationError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run_once")


class FakeChatClient:
    """Dry-run stand-in for script_writer.ChatClient — no OpenAI cost."""

    def create_chat_completion(self, *, model, messages, response_format):
        import json
        return json.dumps({
            "hook": "What if everything you were taught about saving money was backwards?",
            "scenes": [
                {"narration": "Most people are told to save first, spend later. "
                               "But the top 1% do the opposite, and here's why.",
                 "visual_description": "Split screen comparing two paths, clean financial "
                                        "infographic style, muted blues and greens"},
                {"narration": "They pay themselves first by automating investments "
                               "before a single bill gets paid.",
                 "visual_description": "Animated diagram of automatic transfer into an "
                                        "index fund, professional style"},
                {"narration": "That single habit compounds into six figures over a decade, "
                               "and it costs zero extra effort once it's set up.",
                 "visual_description": "Growth chart climbing over a 10 year timeline, "
                                        "clean modern financial style"},
            ],
            "outro": "Set it up once, and let the system do the saving for you.",
            "seo_keywords": ["personal finance", "investing", "index funds"],
            "chapter_timestamps": [{"time": "00:00", "title": "The Backwards Rule"}],
            "affiliate_slots": ["AFFILIATE_FINANCE_1"],
        })


class FakeSynthesizer:
    """Dry-run stand-in for voice_gen.Synthesizer — no edge-tts/ElevenLabs call."""

    def synthesize(self, text, voice_id, output_path):
        output_path.write_bytes(b"FAKE_AUDIO")


class FakeConcatenator:
    """Dry-run stand-in for voice_gen.AudioConcatenator — no ffmpeg call."""

    def concatenate(self, input_paths, output_path):
        output_path.write_bytes(b"FAKE_AUDIO_CONCAT")


def run_once(channel_codename: str, topic: str, dry_run: bool = False) -> int:
    channel = get_channel(channel_codename)
    content_db.init_db()

    video_id = content_db.create_video(
        channel=channel.codename, topic=topic, video_mode=channel.video_mode
    )
    logger.info("Created video id=%s channel=%s topic=%r", video_id, channel.codename, topic)

    chat_client = FakeChatClient() if dry_run else None
    try:
        script: Script = generate_script(
            channel=channel, topic=topic, client=chat_client, video_id=video_id
        )
        logger.info("Script generated: hook=%r, %d scenes", script.hook, len(script.scenes))
    except ScriptGenerationError as exc:
        logger.error("Script generation failed: %s", exc)
        return video_id

    synthesizer = FakeSynthesizer() if dry_run else None
    concatenator = FakeConcatenator() if dry_run else None
    try:
        voice_result = generate_voice(
            channel=channel, script=script, video_id=video_id,
            synthesizer=synthesizer, concatenator=concatenator,
        )
        logger.info(
            "Voice generated: %s (%d scenes synthesized)",
            voice_result.output_path, voice_result.scene_count,
        )
    except VoiceGenerationError as exc:
        logger.error("Voice generation failed: %s", exc)
        return video_id

    content_db.update_status(video_id, "MUSIC")
    record = content_db.get_video(video_id)
    logger.info(
        "run_once complete for video_id=%s. status=%s (pipeline stops here until "
        "music_mixer.py / Phase 2 is built). metadata keys=%s",
        video_id, record.status, list(record.metadata.keys()),
    )
    return video_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Run script+voice stages for one video.")
    parser.add_argument("--channel", required=True, help="Channel codename, e.g. finance")
    parser.add_argument("--topic", required=True, help="Video topic")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Use fake script/voice clients — no OpenAI/Edge-TTS/ffmpeg calls, zero cost.",
    )
    args = parser.parse_args()

    try:
        video_id = run_once(args.channel, args.topic, dry_run=args.dry_run)
    except KeyError as exc:
        logger.error(str(exc))
        sys.exit(1)

    logger.info("Done. video_id=%s — inspect with content_db.get_video(%s)", video_id, video_id)


if __name__ == "__main__":
    main()
