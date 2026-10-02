"""Regression evidence for the stacked-PR merge-readiness review."""

import json
import os
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from control_plane.core.run_manager import RunManager


def running(tmp_path):
    manager = RunManager(tmp_path / "runs")
    run_id = manager.create("e2e_validation", {})
    manager.start(run_id)
    artifact = manager.root / run_id / "artifacts" / "script.txt"
    artifact.write_text("original", encoding="utf-8")
    return manager, run_id, artifact


def checkpoint_path(manager, run_id):
    return manager.root / run_id / manager.status(run_id)["last_checkpoint"]


def test_rejects_run_path_escape(tmp_path):
    manager, _, _ = running(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "status.json").write_text('{"lifecycle":"RUNNING"}')
    with pytest.raises(ValueError):
        manager.status("../outside")


@pytest.mark.parametrize("artifact_ref", ["../outside.txt", "/etc/hosts", "artifacts/missing.txt", "artifacts"])
def test_checkpoint_requires_existing_contained_files(tmp_path, artifact_ref):
    manager, run_id, _ = running(tmp_path)
    (tmp_path / "runs" / "outside.txt").write_text("outside")
    with pytest.raises((ValueError, RuntimeError)):
        manager.checkpoint(run_id, "script", [artifact_ref])
    assert manager.status(run_id)["last_checkpoint"] is None


def test_checkpoint_rejects_symlink_escape(tmp_path):
    manager, run_id, _ = running(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside")
    link = manager.root / run_id / "artifacts" / "link.txt"
    link.symlink_to(outside)
    with pytest.raises(ValueError):
        manager.checkpoint(run_id, "script", ["artifacts/link.txt"])


@pytest.mark.parametrize("change", ["content", "run_id", "resume_from", "verified", "malformed"])
def test_recovery_rejects_corrupt_evidence_and_stays_retryable(tmp_path, change):
    manager, run_id, artifact = running(tmp_path)
    manager.checkpoint(run_id, "script", ["artifacts/script.txt"])
    path = checkpoint_path(manager, run_id)
    original = path.read_text()
    cp = json.loads(original)
    if change == "content":
        artifact.write_text("altered")
    elif change == "malformed":
        path.write_text("{")
    else:
        cp[change] = {"run_id": "another-run", "resume_from": "upload", "verified": "true"}[change]
        path.write_text(json.dumps(cp))
    manager.interrupt(run_id)
    with pytest.raises((RuntimeError, ValueError)):
        manager.recover(run_id)
    status = manager.status(run_id)
    assert status["lifecycle"] == "RECOVERY_REQUIRED"
    assert status["execution"] == "INTERRUPTED"
    assert status["resumable"] is False
    assert status["error_class"] == "CheckpointValidationError"
    path.write_text(original)
    artifact.write_text("original")
    assert manager.recover(run_id) == "voice"
    assert manager.status(run_id)["error_class"] is None


def test_recovery_uses_status_pointer_not_checkpoint_mtime(tmp_path):
    manager, run_id, _ = running(tmp_path)
    manager.checkpoint(run_id, "script", ["artifacts/script.txt"])
    script_cp = checkpoint_path(manager, run_id)
    manager.checkpoint(run_id, "voice", ["artifacts/script.txt"])
    os.utime(script_cp, (4102444800, 4102444800))
    manager.interrupt(run_id)
    assert manager.recover(run_id) == "music"


@pytest.mark.parametrize("stage", ["unknown", "../../outside"])
def test_checkpoint_rejects_unknown_stage(tmp_path, stage):
    manager, run_id, _ = running(tmp_path)
    with pytest.raises(ValueError):
        manager.checkpoint(run_id, stage, ["artifacts/script.txt"])


def test_checkpoint_requires_running_lifecycle(tmp_path):
    manager, run_id, _ = running(tmp_path)
    manager.interrupt(run_id)
    with pytest.raises(ValueError):
        manager.checkpoint(run_id, "script", ["artifacts/script.txt"])


def test_terminal_checkpoint_matches_schema_and_does_not_reupload(tmp_path):
    manager, run_id, _ = running(tmp_path)
    manager.checkpoint(run_id, "upload", ["artifacts/script.txt"])
    cp = json.loads(checkpoint_path(manager, run_id).read_text())
    schema = json.loads((Path(__file__).parents[1] / "control_plane/schemas/checkpoint.schema.json").read_text())
    Draft202012Validator(schema).validate(cp)
    assert manager.status(run_id)["resumable"] is False
    manager.interrupt(run_id)
    assert manager.recover(run_id) is None
    manager.succeed(run_id, {"video": "local.mp4"})
    results = json.loads((manager.root / run_id / "results.json").read_text())
    assert results["completed_stages"] == ["upload"]
    assert results["outputs"] == {"video": "local.mp4"}


def test_success_records_completed_stages_once(tmp_path):
    manager, run_id, _ = running(tmp_path)
    manager.checkpoint(run_id, "script", ["artifacts/script.txt"])
    manager.interrupt(run_id)
    manager.recover(run_id)
    manager.checkpoint(run_id, "voice", ["artifacts/script.txt"])
    manager.succeed(run_id)
    results = json.loads((manager.root / run_id / "results.json").read_text())
    assert results["completed_stages"] == ["script", "voice"]


def test_atomic_checkpoint_write_keeps_previous_pointer_on_failure(tmp_path, monkeypatch):
    manager, run_id, _ = running(tmp_path)
    manager.checkpoint(run_id, "script", ["artifacts/script.txt"])
    original_status = manager.status(run_id)
    def fail_replace(source, destination):
        raise OSError("simulated process boundary before replace")
    with monkeypatch.context() as patch:
        patch.setattr(os, "replace", fail_replace)
        with pytest.raises(OSError):
            manager.checkpoint(run_id, "voice", ["artifacts/script.txt"])
    assert manager.status(run_id) == original_status
    assert manager.latest_checkpoint(run_id)["stage"] == "script"
    assert not list((manager.root / run_id / "checkpoints").glob(".*"))


@pytest.mark.parametrize("stage", ["script", "voice"])
def test_completed_checkpoint_cannot_be_overwritten_or_rewound(tmp_path, stage):
    manager, run_id, _ = running(tmp_path)
    manager.checkpoint(run_id, "voice", ["artifacts/script.txt"])
    original = checkpoint_path(manager, run_id).read_text()
    with pytest.raises(ValueError):
        manager.checkpoint(run_id, stage, ["artifacts/script.txt"])
    assert checkpoint_path(manager, run_id).read_text() == original


def test_legacy_checkpoint_requires_reverification(tmp_path):
    manager, run_id, _ = running(tmp_path)
    manager.checkpoint(run_id, "script", ["artifacts/script.txt"])
    path = checkpoint_path(manager, run_id)
    cp = json.loads(path.read_text())
    del cp["artifact_sha256"]
    path.write_text(json.dumps(cp))
    manager.interrupt(run_id)
    with pytest.raises(RuntimeError, match="legacy checkpoints must be reverified"):
        manager.recover(run_id)
