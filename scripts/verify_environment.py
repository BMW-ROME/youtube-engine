"""
scripts/verify_environment.py

Local pre-flight check for the youtube-engine pipeline, run BEFORE spending
any real API credits or attempting a full pipeline run. Checks every real
(non-fake) dependency the pipeline needs, in order of how the pipeline uses
them, and reports exactly what's missing/broken without touching the
network except where explicitly noted.

Usage:
    python scripts/verify_environment.py

Exit code 0 if everything required is present; non-zero if any REQUIRED
check fails (optional checks only warn).
"""

from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import sys

REQUIRED_BINARIES = ["ffmpeg", "ffprobe"]
REQUIRED_PY_PACKAGES = ["openai", "pydantic", "pydantic_settings", "dotenv"]
OPTIONAL_PY_PACKAGES = [
    ("edge_tts", "Edge-TTS voice synthesis (free tier for 6/7 channels)"),
    ("chatterbox", "Chatterbox local voice cloning (Thee3lite Speaks channel) + torch"),
    ("fastapi", "FastAPI dashboard server (dashboard/app.py)"),
    ("uvicorn", "ASGI server for the FastAPI dashboard"),
    ("PIL", "Pillow - thumbnail text overlay, image placeholders"),
    ("replicate", "Replicate - animated/ai_video effect modes"),
    ("googleapiclient", "YouTube Data API v3 uploads (UPLOAD_MODE=youtube_api)"),
    ("feedparser", "RSS topic discovery (core/trend_engine.py)"),
    ("apscheduler", "per-channel cron scheduling (core/orchestrator.py)"),
    ("requests", "marketing-ops brand sync (config/brand_loader.py)"),
    ("yaml", "marketing-ops brand sync (config/brand_loader.py)"),
]

results = {"required_ok": [], "required_fail": [], "optional_ok": [], "optional_missing": []}


def check_binary(name: str) -> bool:
    path = shutil.which(name)
    if path:
        try:
            out = subprocess.run([name, "-version"], capture_output=True, text=True, timeout=5)
            version_line = out.stdout.splitlines()[0] if out.stdout else "(no version output)"
        except Exception:
            version_line = "(found but -version failed)"
        print(f"  [OK] {name}: {path}  {version_line}")
        return True
    print(f"  [MISSING] {name}: not found on PATH")
    return False


def check_package(module_name: str) -> bool:
    try:
        mod = importlib.import_module(module_name)
        version = getattr(mod, "__version__", "unknown version")
        print(f"  [OK] {module_name} ({version})")
        return True
    except ImportError as exc:
        print(f"  [MISSING] {module_name}: {exc}")
        return False


def check_env_var(name: str, required: bool = True) -> bool:
    val = os.environ.get(name)
    if val:
        masked = val[:4] + "..." + val[-2:] if len(val) > 8 else "***"
        print(f"  [OK] {name} is set ({masked})")
        return True
    level = "MISSING" if required else "not set (optional)"
    print(f"  [{level}] {name}")
    return False


def probe_base_url(name: str, env_var: str, default_target: str) -> None:
    """Performs a read-only reachability probe against an OpenAI-compatible
    base URL. Never fails the run -- these are informational only."""
    base = os.environ.get(env_var)
    if not base:
        print(f"  [note] {name}: {default_target} (default; set {env_var} for a local backend)")
        return

    import urllib.request
    url = base.rstrip("/") + "/models"
    print(f"  [probe] {name}: {base}")
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            body = resp.read(1000)
            count = body.count(b'"id"')
            print(f"  [OK]   {name} reachable ({count} model(s) advertised)")
    except Exception as exc:
        print(f"  [ALERT] {name} configured ({base}) but NOT reachable: {exc}")

    model_env = "LLM_MODEL" if env_var == "OPENAI_BASE_URL" else "IMAGE_MODEL"
    model = os.environ.get(model_env)
    if model:
        print(f"         stage will request {model_env}={model}")


print("=" * 60)
print("1. Required system binaries (video assembly, effects, shorts)")
print("=" * 60)
for b in REQUIRED_BINARIES:
    ok = check_binary(b)
    (results["required_ok"] if ok else results["required_fail"]).append(b)

print()
print("=" * 60)
print("2. Required Python packages")
print("=" * 60)
for p in REQUIRED_PY_PACKAGES:
    ok = check_package(p)
    (results["required_ok"] if ok else results["required_fail"]).append(p)

print()
print("=" * 60)
print("3. Optional Python packages (pipeline degrades gracefully without these)")
print("=" * 60)
for p, desc in OPTIONAL_PY_PACKAGES:
    ok = check_package(p)
    if ok:
        results["optional_ok"].append(p)
    else:
        results["optional_missing"].append((p, desc))
        print(f"         -> impact if missing: {desc}")

print()
print("=" * 60)
print("4. Environment variables")
print("=" * 60)
check_env_var("OPENAI_API_KEY", required=True)
check_env_var("CHATTERBOX_VOICE_SAMPLE_PATH", required=False)
check_env_var("GITHUB_TOKEN", required=False)
check_env_var("UPLOAD_MODE", required=False)

print()
print("=" * 60)
print("5. AI Backend (local probes, informational only - never fails the run)")
print("=" * 60)
probe_base_url("Chat backend (script + SEO)", "OPENAI_BASE_URL", "OpenAI")
probe_base_url("Image backend (DALL-E stage)", "IMAGE_BASE_URL", "OpenAI DALL-E")

print()
print("=" * 60)
print("SUMMARY")
print("=" * 60)
if results["required_fail"]:
    print(f"REQUIRED CHECKS FAILED: {results['required_fail']}")
    print("Fix these before attempting any real pipeline run.")
else:
    print("All required checks passed.")

if results["optional_missing"]:
    print(f"\nOptional/degraded features ({len(results['optional_missing'])}):")
    for name, desc in results["optional_missing"]:
        print(f"  - {name}: {desc}")

print()
print("Recommended next step if all required checks pass:")
print('  python scripts/run_once.py --channel finance --topic "test topic" --dry-run')
print("  (confirms the wiring end-to-end with zero cost, then remove --dry-run)")

sys.exit(1 if results["required_fail"] else 0)
