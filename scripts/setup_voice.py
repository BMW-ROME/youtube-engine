"""
scripts/setup_voice.py

Local setup wizard for Chatterbox voice cloning (Thee3lite Speaks channel).

Chatterbox has no remote "upload and train" step -- setting up a cloned
voice just means pointing the pipeline at a good local reference audio
clip. This wizard:

    1. Confirms chatterbox-tts is importable (installed correctly).
    2. Validates a reference clip you provide (format, duration, exists).
    3. Runs one real, cheap test synthesis (a short sentence) so you can
       actually LISTEN to the cloned voice before wiring it into the full
       pipeline -- catching a bad/noisy reference clip early, before it's
       baked into every video on the channel.
    4. Prints the exact .env line to set (CHATTERBOX_VOICE_SAMPLE_PATH or
       the per-channel override) so you can copy-paste it in.

This never modifies your .env automatically -- matching the pattern used
throughout this repo (core modules never do file-IO side effects beyond
what you explicitly ask for).

Usage:
    python scripts/setup_voice.py --clip /path/to/your_voice_sample.wav
    python scripts/setup_voice.py --clip /path/to/clip.wav --channel thee3lite
    python scripts/setup_voice.py --clip /path/to/clip.wav --skip-synthesis-test
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure the repo root (parent of scripts/) is importable as `core`/`config`
# when this file is run directly (python scripts/setup_voice.py) -- Python
# only auto-adds the SCRIPT'S OWN directory to sys.path, not its parent,
# so without this, `from core.voice_clone import ...` fails with
# ModuleNotFoundError no matter what directory you run this from.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def check_chatterbox_importable() -> bool:
    print("=" * 60)
    print("Step 1: Checking chatterbox-tts installation")
    print("=" * 60)
    try:
        import chatterbox  # noqa: F401
        print("[OK] chatterbox package is importable.")
    except ImportError as exc:
        print(f"[FAIL] chatterbox package not importable: {exc}")
        print("       Run: pip install chatterbox-tts")
        return False

    try:
        from chatterbox.tts import ChatterboxTTS  # noqa: F401
        print("[OK] chatterbox.tts.ChatterboxTTS is importable.")
    except ImportError as exc:
        print(f"[FAIL] chatterbox.tts.ChatterboxTTS not importable: {exc}")
        return False

    try:
        import torch
        cuda_available = torch.cuda.is_available()
        print(f"[OK] torch installed (version {torch.__version__}). CUDA available: {cuda_available}")
        if not cuda_available:
            print("[WARN] No CUDA GPU detected -- synthesis will run on CPU (much slower,")
            print("       but will still work). Set CHATTERBOX_DEVICE=cpu in .env.")
    except ImportError as exc:
        print(f"[FAIL] torch not importable: {exc}")
        print("       Install a torch build matching your GPU: https://pytorch.org/get-started/locally/")
        return False

    return True


def validate_clip(clip_path: Path) -> bool:
    print()
    print("=" * 60)
    print("Step 2: Validating reference audio clip")
    print("=" * 60)
    try:
        from core.voice_clone import validate_reference_clip, VoiceCloneError
    except ImportError:
        print("[WARN] Could not import core.voice_clone (run this from the repo root). "
              "Falling back to basic checks only.")
        if not clip_path.exists():
            print(f"[FAIL] File not found: {clip_path}")
            return False
        print(f"[OK] File exists: {clip_path} ({clip_path.stat().st_size} bytes)")
        return True

    try:
        validate_reference_clip(clip_path)
        print(f"[OK] {clip_path} passed validation (format, non-empty, duration check).")
        return True
    except VoiceCloneError as exc:
        print(f"[FAIL] {exc}")
        return False


def run_test_synthesis(clip_path: Path, device: str) -> bool:
    print()
    print("=" * 60)
    print("Step 3: Running one real test synthesis (this loads the model - may take a")
    print("        minute the first time as weights download/load)")
    print("=" * 60)
    try:
        from chatterbox.tts import ChatterboxTTS
        import torchaudio as ta
    except ImportError as exc:
        print(f"[FAIL] Cannot run test synthesis: {exc}")
        return False

    test_sentence = (
        "This is a test of my cloned voice. If this sounds like me, "
        "the setup is working correctly."
    )

    try:
        print(f"Loading Chatterbox model on device={device!r} ...")
        model = ChatterboxTTS.from_pretrained(device=device)
        print("Model loaded. Synthesizing test sentence...")
        wav = model.generate(
            test_sentence,
            audio_prompt_path=str(clip_path),
            exaggeration=0.5,
            cfg_weight=0.5,
        )
        out_path = Path("output") / "voice_test" / "chatterbox_test_output.wav"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        ta.save(str(out_path), wav, model.sr)
        print(f"[OK] Test synthesis saved to: {out_path.resolve()}")
        print(">>> LISTEN TO THIS FILE. Does it sound like your reference clip's voice?")
        print(">>> If it sounds wrong (robotic, wrong accent, artifacts), try a cleaner/")
        print(">>> longer reference clip before wiring this into the full pipeline.")
        return True
    except Exception as exc:  # noqa: BLE001 - surface any real synthesis error to the user
        print(f"[FAIL] Test synthesis failed: {exc}")
        return False


def print_env_instructions(clip_path: Path, channel: str) -> None:
    print()
    print("=" * 60)
    print("Step 4: Wire this into your .env")
    print("=" * 60)
    resolved = clip_path.resolve()
    if channel:
        var_name = f"CHATTERBOX_VOICE_SAMPLE_PATH_{channel.upper()}"
        print(f"Add this line to your .env (per-channel override for {channel!r}):")
        print(f"\n    {var_name}={resolved}\n")
    else:
        print("Add this line to your .env (global default reference clip):")
        print(f"\n    CHATTERBOX_VOICE_SAMPLE_PATH={resolved}\n")
    print("Then re-run scripts/verify_environment.py to confirm it's picked up,")
    print("and scripts/run_once.py --channel thee3lite --topic \"...\" to test the full")
    print("pipeline stage using this voice.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Chatterbox voice cloning setup wizard.")
    parser.add_argument("--clip", required=True, help="Path to your reference audio clip (wav/mp3/flac/m4a/ogg)")
    parser.add_argument("--channel", default="thee3lite", help="Channel codename for the .env var name (default: thee3lite)")
    parser.add_argument("--device", default="cuda", help="cuda | cpu | mps (default: cuda)")
    parser.add_argument("--skip-synthesis-test", action="store_true",
                         help="Skip the real test synthesis (only validate the clip, don't load the model)")
    args = parser.parse_args()

    clip_path = Path(args.clip)

    if not check_chatterbox_importable():
        print("\n[FAIL] Fix the installation issues above before continuing.")
        sys.exit(1)

    if not validate_clip(clip_path):
        print("\n[FAIL] Fix the reference clip issues above before continuing.")
        sys.exit(1)

    if not args.skip_synthesis_test:
        if not run_test_synthesis(clip_path, args.device):
            print("\n[FAIL] Test synthesis failed. See error above.")
            sys.exit(1)
    else:
        print("\n[SKIPPED] Test synthesis skipped per --skip-synthesis-test.")

    print_env_instructions(clip_path, args.channel)
    print("\nSetup wizard complete.")


if __name__ == "__main__":
    main()
