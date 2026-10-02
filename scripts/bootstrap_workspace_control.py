#!/usr/bin/env python3
"""Bootstrap or validate .workspace-control continuity state.

This utility is deliberately dependency-free so a fresh worker can run it
before installing the full project environment.
"""

from __future__ import annotations

import argparse
import json
import re
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

REQUIRED_STATE_KEYS = (
    "schema_version",
    "project",
    "governing_goal",
    "definition_of_done",
    "phase",
    "status",
    "active_workstream",
    "current_task",
    "completed",
    "verified",
    "in_progress",
    "blocked",
    "next_actions",
    "dependencies",
    "risks",
    "assumptions",
    "decisions",
    "artifacts",
    "relevant_files",
    "relevant_commits",
    "tests",
    "last_known_good_state",
    "updated_at",
)

PATH_LIKE_STATE_FIELDS = (
    "artifacts",
    "relevant_files",
)

WORK_PACKET_REQUIRED_KEYS = (
    "id",
    "goal",
    "workstream",
    "status",
    "inputs",
    "definition_of_done",
    "verification",
)

VALID_WORK_PACKET_STATUSES = {"ready", "active", "in_progress", "blocked", "complete"}


class ValidationError(Exception):
    """Raised when a local parser cannot safely interpret continuity files."""


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def is_probable_repo_path(value: str) -> bool:
    """Return true for values that should resolve inside the repository.

    Continuity state can contain URLs, branch names, PR labels, run labels, and
    plain prose. We only validate strings that have normal repository-path shape.
    """
    if not isinstance(value, str) or not value:
        return False
    if "://" in value:
        return False
    if value.startswith("GitHub Actions run "):
        return False
    if re.fullmatch(r"[0-9a-f]{7,40}", value):
        return False
    if value.startswith(("PR #", "PR-", "WP-")):
        return False
    return value.startswith(".") or "/" in value or value.endswith((".py", ".md", ".json", ".yaml", ".yml"))


def parse_scalar(value: str) -> str | bool | int:
    value = value.strip()
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value.isdigit():
        return int(value)
    return value.strip('"\'')


def parse_simple_yaml(path: Path) -> dict[str, object]:
    """Parse the small work-packet YAML subset used by this repository.

    The parser intentionally supports only top-level scalar keys, top-level
    lists, and one-level nested scalar maps. That keeps the validator
    dependency-free and prevents a fresh worker from needing PyYAML before it
    can validate continuity state.
    """
    data: dict[str, object] = {}
    current_key: str | None = None

    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if line.startswith("  - "):
            if current_key is None:
                raise ValidationError(f"{path}: list item before key at line {line_no}")
            if data.get(current_key) == []:
                data[current_key] = []
            if not isinstance(data.get(current_key), list):
                raise ValidationError(f"{path}: key {current_key!r} mixes scalar/map and list values")
            data[current_key].append(parse_scalar(stripped[2:].strip()))
            continue

        if line.startswith("  ") and ":" in stripped:
            if current_key is None:
                raise ValidationError(f"{path}: nested value before key at line {line_no}")
            nested_key, nested_value = stripped.split(":", 1)
            if data.get(current_key) == []:
                data[current_key] = {}
            if not isinstance(data.get(current_key), dict):
                raise ValidationError(f"{path}: key {current_key!r} mixes scalar/list and map values")
            data[current_key][nested_key.strip()] = parse_scalar(nested_value.strip())
            continue

        if not line.startswith(" ") and ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if not key:
                raise ValidationError(f"{path}: empty key at line {line_no}")
            if key in data:
                raise ValidationError(f"{path}: duplicate key {key!r} at line {line_no}")
            current_key = key
            data[key] = parse_scalar(value) if value else []
            continue

        raise ValidationError(f"{path}: unsupported YAML shape at line {line_no}: {raw!r}")

    return data


def validate_existing_repo_paths(root: Path, values: list[str], source: str) -> list[str]:
    errors: list[str] = []
    for rel in values:
        if not isinstance(rel, str):
            errors.append(f"{source} contains non-string path reference: {rel!r}")
            continue
        if not is_probable_repo_path(rel):
            continue
        if Path(rel).is_absolute() or ".." in Path(rel).parts or "\\" in rel:
            errors.append(f"{source} contains unsafe path reference: {rel}")
            continue
        resolved = (root / rel).resolve()
        if not resolved.is_relative_to(root.resolve()):
            errors.append(f"{source} contains unsafe path reference: {rel}")
        elif not resolved.exists():
            errors.append(f"{source} references missing file: {rel}")
    return errors


def validate_work_packets(root: Path, wc: Path, state: dict[str, object]) -> list[str]:
    errors: list[str] = []
    packets_dir = wc / "work-packets"
    if not packets_dir.exists():
        return ["missing .workspace-control/work-packets"]

    packet_paths = sorted(packets_dir.glob("*.yaml")) + sorted(packets_dir.glob("*.yml"))
    if not packet_paths:
        return ["no workspace-control work packets found"]

    seen_ids: set[str] = set()
    for packet_path in packet_paths:
        rel_packet = str(packet_path.relative_to(root))
        try:
            packet = parse_simple_yaml(packet_path)
        except ValidationError as exc:
            errors.append(str(exc))
            continue

        for key in WORK_PACKET_REQUIRED_KEYS:
            if key not in packet:
                errors.append(f"{rel_packet} missing key: {key}")

        packet_id = packet.get("id")
        if isinstance(packet_id, str):
            if packet_id in seen_ids:
                errors.append(f"duplicate work packet id: {packet_id}")
            seen_ids.add(packet_id)
            if packet_id not in packet_path.stem:
                errors.append(f"{rel_packet} filename does not contain id {packet_id}")
        else:
            errors.append(f"{rel_packet} id must be a string")

        status = packet.get("status")
        if not isinstance(status, str) or status not in VALID_WORK_PACKET_STATUSES:
            errors.append(f"{rel_packet} invalid status: {status!r}")

        inputs = packet.get("inputs")
        if not isinstance(inputs, list) or not inputs:
            errors.append(f"{rel_packet} inputs must be a non-empty list")
        else:
            errors.extend(validate_existing_repo_paths(root, inputs, rel_packet))

        next_packet = packet.get("next_on_success")
        if isinstance(next_packet, str) and next_packet.startswith("WP-"):
            candidate = packets_dir / f"{next_packet}.yaml"
            if status == "complete" and not candidate.exists():
                errors.append(f"{rel_packet} points to missing next_on_success packet: {next_packet}")

    current_task = state.get("current_task", "")
    match = re.search(r"\b(WP-\d+)\b", current_task if isinstance(current_task, str) else "")
    if match:
        active_packet = packets_dir / f"{match.group(1)}.yaml"
        if not active_packet.exists():
            errors.append(f"state current_task references missing active work packet: {match.group(1)}")

    return errors


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

    if not isinstance(state, dict):
        return errors + ["state.json must be an object"]

    schema = json.loads((wc / "state.schema.json").read_text(encoding="utf-8")) if (wc / "state.schema.json").exists() else {}
    for key, spec in schema.get("properties", {}).items():
        if key not in state:
            continue
        value = state[key]
        expected = spec.get("type")
        if expected == "string" and not isinstance(value, str):
            errors.append(f"state.json {key} must be a string")
        if expected == "array" and (not isinstance(value, list) or not all(isinstance(x, str) for x in value)):
            errors.append(f"state.json {key} must be a list of strings")
        if "enum" in spec and value not in spec["enum"]:
            errors.append(f"state.json {key} has invalid value: {value!r}")
        if isinstance(value, str) and len(value) < spec.get("minLength", 0):
            errors.append(f"state.json {key} must not be empty")
    if schema.get("additionalProperties") is False:
        for key in set(state) - set(schema.get("properties", {})):
            errors.append(f"state.json unknown key: {key}")

    for key in REQUIRED_STATE_KEYS:
        if key not in state:
            errors.append(f"state.json missing key: {key}")

    if state.get("schema_version") != "0.1":
        errors.append(f"state.json schema_version must be 0.1, got {state.get('schema_version')!r}")

    for field in PATH_LIKE_STATE_FIELDS:
        values = state.get(field, [])
        if not isinstance(values, list):
            errors.append(f"state.json {field} must be a list")
            continue
        errors.extend(validate_existing_repo_paths(root, values, f"state.json {field}"))

    handoff = wc / "handoff.md"
    if handoff.exists():
        words = handoff.read_text(encoding="utf-8").split()
        if len(words) >= 1500:
            errors.append(f"handoff.md too large: {len(words)} words")

    errors.extend(validate_work_packets(root, wc, state))
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
