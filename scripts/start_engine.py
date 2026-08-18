"""
scripts/start_engine.py

Main CLI entry point for the YouTube Engine. Wraps core/pipeline.py's
run_pipeline() with argument parsing for both modes described in
README.md's Quick Start:

    Freestyle Mode:
        python scripts/start_engine.py --category "true crime" \\
            --topic "Unsolved Mysteries of 2026" --video-mode kenburns

    Single Channel Test:
        python scripts/start_engine.py --channel finance
        python scripts/start_engine.py --channel tech --topic "GPT-5 Changes Everything"

    No arguments -> interactive menu (Run ALL Channels, Run ONE Channel,
    Dashboard Only, Setup & Diagnostics, Freestyle).

This is the file scripts/start_engine.bat launches on Windows.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Ensure the repo root (parent of scripts/) is importable as `core`/`config`
# when this file is run directly (python scripts/start_engine.py) -- Python
# only auto-adds the SCRIPT'S OWN directory to sys.path, not its parent,
# so without this, `from core.pipeline import run_pipeline` fails with
# ModuleNotFoundError no matter what directory you run this from.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("start_engine")


def run_freestyle(category: str, topic: str, video_mode: str | None) -> None:
    from core.freestyle import build_freestyle_channel
    from core.pipeline import run_pipeline
    from config.channels import CHANNELS

    channel = build_freestyle_channel(category, video_mode=video_mode)
    logger.info(
        "Freestyle mode: category=%r topic=%r video_mode=%r codename=%r",
        category, topic, channel.video_mode, channel.codename,
    )

    # run_pipeline() looks up channels by codename via config.channels.get_channel(),
    # so a freestyle channel (which is intentionally NOT registered there) is
    # registered here just long enough for this one run, then removed --
    # keeps CHANNELS from growing unbounded across repeated freestyle calls
    # in a long-lived process (e.g. the dashboard triggering multiple runs).
    CHANNELS[channel.codename] = channel
    try:
        result = run_pipeline(topic=topic, channel_codename=channel.codename)
    finally:
        CHANNELS.pop(channel.codename, None)

    _report_result(result)


def run_single_channel(channel_codename: str, topic: str | None) -> None:
    from core.pipeline import run_pipeline
    from config.channels import get_channel

    channel = get_channel(channel_codename)  # raises KeyError with a helpful message if unknown
    chosen_topic = topic or f"Untitled {channel.display_name} video"
    logger.info("Single channel run: channel=%r topic=%r", channel_codename, chosen_topic)

    result = run_pipeline(topic=chosen_topic, channel_codename=channel_codename)
    _report_result(result)


def run_all_channels() -> None:
    from core.pipeline import run_pipeline
    from config.channels import all_channels

    channels = all_channels()
    logger.info("Running ALL %d channels (autopilot)...", len(channels))
    results = []
    for channel in channels:
        topic = f"Untitled {channel.display_name} video"
        logger.info("--- Channel: %s ---", channel.codename)
        result = run_pipeline(topic=topic, channel_codename=channel.codename)
        results.append(result)
        _report_result(result)

    succeeded = sum(1 for r in results if r.success)
    logger.info("ALL channels complete: %d/%d succeeded.", succeeded, len(results))


def run_dashboard_only() -> None:
    try:
        from dashboard.app import app
    except ImportError as exc:
        logger.error("Dashboard not available: %s", exc)
        sys.exit(1)
    from config.settings import settings
    logger.info("Starting dashboard at http://%s:%d", settings.dashboard_host, settings.dashboard_port)
    app.run(host=settings.dashboard_host, port=settings.dashboard_port)


def run_setup_diagnostics() -> None:
    import subprocess
    subprocess.run([sys.executable, "scripts/verify_environment.py"])


def _report_result(result) -> None:
    logger.info(
        "Run complete for topic=%r channel=%r: success=%s failed_stages=%s",
        result.topic, result.channel_codename, result.success, result.failed_stages,
    )
    if result.final_video_path:
        logger.info("Final video: %s", result.final_video_path)
    if result.upload_result:
        logger.info("Upload result: %s", result.upload_result)


def interactive_menu() -> None:
    print("=" * 60)
    print("YouTube Engine -- Interactive Menu")
    print("=" * 60)
    print("1. Run ALL Channels (autopilot)")
    print("2. Run ONE Channel")
    print("3. Dashboard Only")
    print("4. Setup & Diagnostics")
    print("5. Freestyle (any category)")
    print("0. Exit")
    choice = input("\nChoose an option: ").strip()

    if choice == "1":
        run_all_channels()
    elif choice == "2":
        from config.channels import CHANNELS
        print(f"Available channels: {list(CHANNELS.keys())}")
        channel_codename = input("Channel codename: ").strip()
        topic = input("Topic (blank for default): ").strip() or None
        run_single_channel(channel_codename, topic)
    elif choice == "3":
        run_dashboard_only()
    elif choice == "4":
        run_setup_diagnostics()
    elif choice == "5":
        category = input("Category: ").strip()
        topic = input("Topic: ").strip()
        video_mode = input("Video mode (blank for default): ").strip() or None
        run_freestyle(category, topic, video_mode)
    elif choice == "0":
        sys.exit(0)
    else:
        print("Unknown option.")


def main() -> None:
    parser = argparse.ArgumentParser(description="YouTube Engine main CLI.")
    parser.add_argument("--category", help="Freestyle mode: arbitrary category, e.g. 'true crime'")
    parser.add_argument("--topic", help="Video topic (required for --category; optional override for --channel)")
    parser.add_argument("--video-mode", dest="video_mode",
                         choices=["kenburns", "sketch", "animated", "ai_video"],
                         help="Video effect mode (Freestyle mode only; built-in channels use their configured mode)")
    parser.add_argument("--channel", help="Run a single built-in channel by codename, e.g. 'finance'")
    parser.add_argument("--all", action="store_true", help="Run all 7 built-in channels")
    parser.add_argument("--dashboard", action="store_true", help="Start the dashboard only")
    parser.add_argument("--setup", action="store_true", help="Run setup & diagnostics (verify_environment.py)")
    args = parser.parse_args()

    try:
        if args.category:
            if not args.topic:
                parser.error("--topic is required when using --category (Freestyle mode)")
            run_freestyle(args.category, args.topic, args.video_mode)
        elif args.channel:
            run_single_channel(args.channel, args.topic)
        elif args.all:
            run_all_channels()
        elif args.dashboard:
            run_dashboard_only()
        elif args.setup:
            run_setup_diagnostics()
        else:
            interactive_menu()
    except KeyError as exc:
        logger.error(str(exc))
        sys.exit(1)
    except Exception:
        logger.exception("start_engine failed with an unhandled exception")
        sys.exit(1)


if __name__ == "__main__":
    main()
