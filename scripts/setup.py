"""
scripts/setup.py

First-time setup wizard for the YouTube Engine.

What this does:
  1. Bootstrap .env from .env.template if it doesn't exist yet (never
     overwrites an existing .env).
  2. Run scripts/verify_environment.py diagnostics (ffmpeg, deps, env vars).
  3. Optionally run the YouTube Data API v3 OAuth flow so you can set
     UPLOAD_MODE=youtube_api (lazy google-auth import; skipped with a
     clear hint if the packages aren't installed).

Design notes:
  - Matching the repo-wide convention, this script never writes secrets
    to disk automatically. It prints the exact .env lines to add and
    lets you paste them in.
  - Every step is guarded so the wizard explains what's missing instead
    of crashing halfway through.

Usage:
    python scripts/setup.py                # bootstrap .env + diagnostics
    python scripts/setup.py --run-diagnostics
    python scripts/setup.py --oauth         # start YouTube OAuth flow (needs client_secret.json)
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

# Ensure the repo root (parent of scripts/) is importable as core/config
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

ENV_TEMPLATE = REPO_ROOT / ".env.template"
ENV_FILE = REPO_ROOT / ".env"


def bootstrap_env() -> bool:
    """Copy .env.template -> .env if missing. Never overwrites an existing .env."""
    print("=" * 60)
    print("Step 1: Environment file (.env)")
    print("=" * 60)
    if ENV_FILE.exists():
        print(f"[OK] .env already exists at {ENV_FILE}")
        return True
    if not ENV_TEMPLATE.exists():
        print(f"[FAIL] {ENV_TEMPLATE} not found. Clone the repo fresh or recreate the template.")
        return False
    shutil.copyfile(ENV_TEMPLATE, ENV_FILE)
    print(f"[OK] Created {ENV_FILE} from template.")
    print(">>> Edit it and set OPENAI_API_KEY (required) plus optional keys.")
    return True


def run_diagnostics() -> bool:
    """Delegate to scripts/verify_environment.py."""
    print()
    print("=" * 60)
    print("Step 2: Environment diagnostics")
    print("=" * 60)
    script = REPO_ROOT / "scripts" / "verify_environment.py"
    code = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(REPO_ROOT),
    ).returncode
    print()
    if code == 0:
        print("[OK] Diagnostics passed. You can run the pipeline now.")
    else:
        print("[WARN] Diagnostics found issues. Fix the items above before a real run.")
    return code == 0


def oauth_flow(client_secrets: Path) -> None:
    """Run the YouTube Data API v3 OAuth flow to obtain a refresh token."""
    print()
    print("=" * 60)
    print("Step 3: YouTube Data API OAuth flow")
    print("=" * 60)
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.oauth2.credentials import Credentials
    except ImportError as exc:
        print(f"[FAIL] google-auth-oauthlib not installed: {exc}")
        print("       Run: pip install google-auth google-auth-oauthlib google-api-python-client")
        return

    client_file = client_secrets or REPO_ROOT / "client_secret.json"
    if not Path(client_file).exists():
        print(f"[FAIL] Client secrets file not found: {client_file}")
        print("       Enable the YouTube Data API v3 in Google Cloud, create an")
        print("       OAuth2 desktop client, download its client_secret.json here,")
        print("       then re-run: python scripts/setup.py --oauth --client-secrets client_secret.json")
        return

    SCOPES = [
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube.readonly",
    ]
    try:
        flow = InstalledAppFlow.from_client_secrets_file(str(client_file), SCOPES)
        creds = flow.run_local_server(port=0, open_browser=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] OAuth flow failed: {exc}")
        return

    print()
    print(">>> Add these lines to your .env (UPLOAD_MODE=youtube_api), then re-run")
    print(">>> scripts/verify_environment.py to confirm:")
    print()
    print(f"    YOUTUBE_CLIENT_ID={creds.client_id}")
    print(f"    YOUTUBE_CLIENT_SECRET={creds.client_secret}")
    print(f"    YOUTUBE_REFRESH_TOKEN={creds.refresh_token}")
    print()
    print("Then: python scripts/quick_upload.py output/videos/your_video.mp4")
    print("      (or scripts/upload_ready.py to batch-upload finished videos)")


def main() -> None:
    parser = argparse.ArgumentParser(description="YouTube Engine first-time setup wizard.")
    parser.add_argument("--run-diagnostics", action="store_true",
                        help="Skip .env bootstrap and only run diagnostics")
    parser.add_argument("--oauth", action="store_true",
                        help="Run the YouTube OAuth flow after diagnostics")
    parser.add_argument("--client-secrets", type=Path, default=None,
                        help="Path to Google OAuth client_secret.json (for --oauth)")
    args = parser.parse_args()

    print("YouTube Engine — Setup Wizard")
    print("=" * 60)

    if not args.run_diagnostics:
        if not bootstrap_env():
            sys.exit(1)

    diag_ok = run_diagnostics()

    if args.oauth:
        oauth_flow(args.client_secrets)

    if not args.oauth and diag_ok:
        print()
        print("Next steps:")
        print("  1. Run a single video:  python scripts/start_engine.py --channel finance --topic \"...\"")
        print("  2. Batch upload:        python scripts/upload_ready.py")
        print("  3. Dashboard:           python dashboard/app.py")
        print("  4. Scheduler:           python -m core.orchestrator")


if __name__ == "__main__":
    main()