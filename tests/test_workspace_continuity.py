from __future__ import annotations

import json
import shutil
from pathlib import Path

from scripts.bootstrap_workspace_control import validate


ROOT = Path(__file__).resolve().parents[1]
WC = ROOT / ".workspace-control"


REQUIRED_STATE_KEYS = {
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
}


def test_workspace_control_bootstrap_exists():
    required = [
        WC / "mission.md",
        WC / "state.json",
        WC / "state.schema.json",
        WC / "decisions.md",
        WC / "blockers.md",
        WC / "next.md",
        WC / "handoff.md",
        WC / "workstreams" / "control-plane-resiliency.md",
        WC / "work-packets" / "WP-001.yaml",
        WC / "work-packets" / "WP-002.yaml",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    assert not missing, f"missing continuity files: {missing}"


def test_workspace_state_has_required_contract():
    state = json.loads((WC / "state.json").read_text(encoding="utf-8"))
    assert REQUIRED_STATE_KEYS <= set(state)
    assert state["schema_version"] == "0.1"
    assert state["project"] == "BMW-ROME/youtube-engine"
    assert state["active_workstream"]
    assert state["current_task"]
    assert state["next_actions"]


def test_state_relevant_paths_exist():
    state = json.loads((WC / "state.json").read_text(encoding="utf-8"))
    missing = [
        rel for rel in state["relevant_files"]
        if not (ROOT / rel).exists()
    ]
    assert not missing, f"state references missing files: {missing}"


def test_skill_bundle_is_installable_shape():
    skills = [
        "goal-control-plane",
        "context-budget-governor",
        "continuity-checkpoint",
        "limit-resilient-executor",
    ]
    for skill in skills:
        manifest = ROOT / ".codex" / "skills" / skill / "SKILL.md"
        assert manifest.exists(), f"missing {manifest.relative_to(ROOT)}"
        text = manifest.read_text(encoding="utf-8")
        assert text.startswith("---\n")
        assert "\nname:" in text
        assert "\ndescription:" in text


def test_handoff_is_compact_and_actionable():
    handoff = (WC / "handoff.md").read_text(encoding="utf-8")
    assert "## First next action" in handoff
    assert "## Do not redo" in handoff
    assert "tests/test_workspace_continuity.py" in handoff
    # Guard against handoff files growing back into full-chat-sized context.
    assert len(handoff.split()) < 1500


def test_validator_accepts_current_workspace_control_state():
    assert validate(ROOT) == []


def copy_workspace_control_tree(tmp_path: Path) -> Path:
    sandbox = tmp_path / "repo"
    shutil.copytree(ROOT / ".workspace-control", sandbox / ".workspace-control")
    for rel in [
        ".codex/skills/goal-control-plane/SKILL.md",
        ".codex/skills/context-budget-governor/SKILL.md",
        ".codex/skills/continuity-checkpoint/SKILL.md",
        ".codex/skills/limit-resilient-executor/SKILL.md",
        ".github/workflows/workspace-continuity.yml",
        "scripts/bootstrap_workspace_control.py",
        "tests/test_workspace_continuity.py",
        "tests/test_interruption_recovery.py",
    ]:
        src = ROOT / rel
        dst = sandbox / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return sandbox


def test_validator_rejects_missing_state_reference(tmp_path):
    sandbox = copy_workspace_control_tree(tmp_path)
    state_path = sandbox / ".workspace-control" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["relevant_files"].append("missing/future_file.py")
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    errors = validate(sandbox)
    assert any("state.json relevant_files references missing file: missing/future_file.py" in e for e in errors)


def test_validator_rejects_missing_work_packet_input(tmp_path):
    sandbox = copy_workspace_control_tree(tmp_path)
    packet = sandbox / ".workspace-control" / "work-packets" / "WP-002.yaml"
    packet.write_text(
        packet.read_text(encoding="utf-8") + "  - missing/work_packet_input.py\n",
        encoding="utf-8",
    )

    errors = validate(sandbox)
    assert any("WP-002.yaml references missing file: missing/work_packet_input.py" in e for e in errors)


def test_validator_rejects_missing_active_work_packet(tmp_path):
    sandbox = copy_workspace_control_tree(tmp_path)
    state_path = sandbox / ".workspace-control" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["current_task"] = "WP-999: impossible packet"
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    errors = validate(sandbox)
    assert any("state current_task references missing active work packet: WP-999" in e for e in errors)
