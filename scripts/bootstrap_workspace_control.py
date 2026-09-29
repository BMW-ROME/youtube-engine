#!/usr/bin/env python3
"""Bootstrap or validate .workspace-control continuity state.

This utility is deliberately dependency-free so a fresh worker can run it
before installing the full project environment.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


REQUIRED = (
    "mission.md",
    "state.json",
    "state.schema.json",
    "decisions.md",
    "blockers.md",
    "next.md",
    "handoff.md",
)


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def validate(root: Path) -> list[str]:
    wc = root / ".workspace-control"
    errors: list[str] = []

    for name in REQUIRED:
        if not (wc / name).exists():
            errors.append(f"missing .workspace-control/{name}")

    state_path = wc / "state.json"
    if not state_path.exists():
        return errors

    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"invalid state.json: {exc}")
        return errors

    for key in (
        "schema_version",
        "project",
        "governing_goal",
        "status",
        "active_workstream",
        "current_task",
        "next_actions",
        "relevant_files",
        "updated_at",
    ):
        if key not in state:
            errors.append(f"state.json missing key: {key}")

    for rel in state.get("relevant_files", []):
        if not (root / rel).exists():
            errors.append(f"state.json references missing file: {rel}")

    handoff = wc / "handoff.md"
    if handoff.exists():
        words = handoff.read_text(encoding="utf-8").split()
        if len(words) >= 1500:
            errors.append(f"handoff.md too large: {len(words)} words")

    return errors


def touch_state(root: Path) -> None:
    path = root / ".workspace-control" / "state.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    state["updated_at"] = utcnow()
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".", help="repository root")
    parser.add_argument("--touch", action="store_true", help="refresh state updated_at before validation")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if args.touch:
        touch_state(root)

    errors = validate(root)
    if errors:
        print("workspace-control validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("workspace-control validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
