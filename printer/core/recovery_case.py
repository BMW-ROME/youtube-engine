"""Evidence-backed local engineering case; never authorizes publication.

Uses real filesystem executions to compare restart-from-zero with checkpoint
recovery. Counts are observations of this workload, not time or revenue claims.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from control_plane.core.run_manager import RunManager
from printer.core.orchestrator import ARTIFACT_DIRS, PRINTER_STAGES, PrinterError, PrinterOrchestrator
from printer.core.production import render_manifest
from printer.integrations.mock_backend import MockProductionBackend


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def experiment(run_id):
    return {
        "schema_version": "1.0", "experiment_id": "local-checkpoint-recovery-v1",
        "run_id": run_id,
        "problem": "Restarting an interrupted workflow from zero repeats completed work.",
        "hypothesis": "Recovering at a completed checkpoint avoids replaying completed stages.",
        "procedure": ["Run five of ten instrumented stages, then interrupt.",
                      "Baseline: start a new run and execute all ten stages.",
                      "Intervention: recover the interrupted run and finish it.",
                      "Compare durable stage-call logs and final lifecycle states."],
        "success_metrics": [{"name": "replayed_stages", "target": 0}],
    }


def measure_recovery(root):
    """Run both arms with real managers and log each handler invocation."""
    root = Path(root)
    measurements = {}
    for arm in ("restart", "recover"):
        arm_root = root / arm
        manager = RunManager(arm_root)
        log = arm_root / "calls.jsonl"

        def record(payload):
            with log.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"run_id": payload["run_id"], "stage": payload["stage"]}) + "\n")
            return {"operation": "recorded local stage invocation"}

        handlers = dict.fromkeys(PRINTER_STAGES, record)
        initial = manager.create("recovery-measurement", {})
        PrinterOrchestrator(manager, arm_root, handlers).execute(initial, experiment(initial), stop_after="evidence")
        manager.interrupt(initial)
        # Reconstruct objects: no in-memory state can supply the resume position.
        manager = RunManager(arm_root)
        final = manager.create("restart-measurement", {}) if arm == "restart" else initial
        if arm == "recover":
            manager.recover(final)
        PrinterOrchestrator(manager, arm_root, handlers).execute(final, experiment(final))
        calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        measurements[arm] = {
            "calls": len(calls), "replayed_stages": len(calls) - len({row["stage"] for row in calls}),
            "stages": [row["stage"] for row in calls],
            "final_lifecycle": manager.status(final)["lifecycle"],
            "log": log.relative_to(root).as_posix(), "sha256": digest(log),
        }
    return measurements


def validate_editorial(evidence, story):
    observations = evidence.get("observations", [])
    identifiers = {row["id"] for row in observations}
    if not identifiers or len(identifiers) != len(observations):
        raise PrinterError("no evidence or duplicate observation IDs")
    if not evidence.get("claims"):
        raise PrinterError("no evidence-backed claim")
    for claim in evidence["claims"]:
        support = claim.get("supporting_observations", [])
        if not support or not set(support) <= identifiers:
            raise PrinterError("unsupported claim")
    if not story.get("viewer_takeaway", "").strip():
        raise PrinterError("no useful viewer takeaway")
    for layer in ("observation", "inference", "audience_prediction", "business_conclusion"):
        if not story.get("layers", {}).get(layer):
            raise PrinterError(f"missing editorial layer: {layer}")


class RecoveryCase:
    """All ten substantive handlers for this one bounded engineering experiment."""

    def __init__(self, root, run_id):
        self.root = Path(root)
        self.run_id = run_id
        self.directory = self.root / run_id
        self.exp = experiment(run_id)

    def stage_path(self, stage):
        return self.directory / "artifacts" / ARTIFACT_DIRS.get(stage, stage) / f"{stage}.json"

    def reference(self, path):
        path = Path(path).resolve()
        return {"path": path.relative_to(self.directory.resolve()).as_posix(), "sha256": digest(path)}

    def verify_reference(self, reference):
        path = (self.directory / reference["path"]).resolve()
        if not path.is_relative_to(self.directory.resolve()) or not path.is_file():
            raise PrinterError("missing or out-of-run artifact")
        if digest(path) != reference["sha256"]:
            raise PrinterError(f"artifact integrity mismatch: {reference['path']}")

    def read(self, stage):
        record = json.loads(self.stage_path(stage).read_text(encoding="utf-8"))
        if record["run_id"] != self.run_id or record["experiment_id"] != self.exp["experiment_id"] or record["stage"] != stage:
            raise PrinterError("artifact lineage mismatch")
        for ref in record["sources"]:
            self.verify_reference(ref)
        return record["data"]

    def handlers(self):
        return {stage: self.handle for stage in PRINTER_STAGES}

    def handle(self, payload):
        stage = payload["stage"]
        if payload["run_id"] != self.run_id or payload["experiment_id"] != self.exp["experiment_id"]:
            raise PrinterError("case identity mismatch")
        previous = PRINTER_STAGES[:PRINTER_STAGES.index(stage)]
        # Validate the complete chain, including raw sidecars, after a restart.
        for prior in previous:
            self.read(prior)
        data, sidecars = getattr(self, stage)()
        return {
            "schema_version": "1.0", "run_id": self.run_id,
            "experiment_id": self.exp["experiment_id"], "stage": stage,
            "sources": [self.reference(self.stage_path(prior)) for prior in previous]
                       + [self.reference(path) for path in sidecars],
            "data": data,
        }

    def intake(self):
        return {"problem": self.exp["problem"], "scope": "local engineering only"}, []

    def research(self):
        source_root = Path(__file__).resolve().parents[2]
        paths = [source_root / "printer/core/orchestrator.py", source_root / "control_plane/core/run_manager.py"]
        snapshots = []
        for path in paths:
            target = self.directory / "artifacts/research/source" / path.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_bytes())
            snapshots.append(target)
        return {"question": self.exp["hypothesis"], "method": "inspect and exercise local recovery code",
                "limitations": "one controlled workload; no external research or business validation"}, snapshots

    def experiment(self):
        return self.exp, []

    def execution(self):
        measurements_root = self.directory / "artifacts/experiment/measurements"
        measured = measure_recovery(measurements_root)
        path = measurements_root / "measurements.json"
        write_json(path, measured)
        return measured, [path, *sorted(measurements_root.rglob("calls.jsonl"))]

    def evidence(self):
        measured = self.read("execution")
        observations = []
        for arm in ("restart", "recover"):
            value = measured[arm]
            observations.append({"id": arm, "statement": f"{arm}: {value['calls']} stage calls, {value['replayed_stages']} replayed stages.",
                                 "source": f"artifacts/experiment/measurements/{value['log']}"})
        delta = measured["restart"]["calls"] - measured["recover"]["calls"]
        return {"observations": observations,
                "claims": [{"statement": f"Checkpoint recovery used {delta} fewer stage calls in this local experiment.",
                            "basis": "observation", "confidence": "high", "supporting_observations": ["restart", "recover"]}],
                "scope": "measured local engineering behavior only; no time, audience, or revenue measurement"}, []

    def story(self):
        evidence = self.read("evidence")
        layers = {
            "observation": evidence["claims"][0]["statement"],
            "inference": "Checkpoint recovery can avoid duplicate completed work at this tested stage boundary.",
            "audience_prediction": "Untested: a walkthrough may help workflow builders understand recovery.",
            "business_conclusion": "No measured revenue, cost, production time, or ROI conclusion is available.",
        }
        story = {"layers": layers, "viewer_takeaway": "Persist and verify a checkpoint, then resume at the next uncompleted stage.",
                 "limitations": "One local workload; interruption between stages only, not arbitrary mid-stage failure.",
                 "voice": "User-led explanation planned; no substitute voice or recording generated.",
                 "walk_with_me_panel": ["Show the problem", "Walk through both logs", "Separate measured result from inference", "Explain limits and next test"],
                 "multimodal_evidence": {"available": ["source snapshots", "stage-call logs"],
                                         "not_collected": ["audio", "video", "screenshots"]}}
        validate_editorial(evidence, story)
        path = self.directory / "artifacts/story/script.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("Local engineering experiment.\n" + "\n".join(f"{key}: {value}" for key, value in layers.items())
                        + "\nTakeaway: " + story["viewer_takeaway"] + "\nLimitations: " + story["limitations"] + "\n", encoding="utf-8")
        story["script"] = path.relative_to(self.directory).as_posix()
        return story, [path]

    def production(self):
        story = self.read("story")
        manifest = {"schema_version": "1.0", "run_id": self.run_id, "experiment_id": self.exp["experiment_id"],
                    "script": {"path": story["script"]},
                    "shots": [{"shot_id": "logs", "purpose": "evidence", "visual_prompt": "Show measured restart and recovery logs; label local engineering scope.",
                               "duration_seconds": 11, "references": ["artifacts/experiment/measurements/restart/calls.jsonl", "artifacts/experiment/measurements/recover/calls.jsonl"]}],
                    "voice": {"mode": "user-recording-pending"}, "metadata": {"validation_only": True}}
        path = self.directory / "artifacts/video/manifest.json"
        write_json(path, manifest)
        render = render_manifest(manifest, self.run_id, MockProductionBackend(), path.parent)
        artifact = Path(render.pop("artifact"))
        render["media_artifact"] = artifact.relative_to(self.directory).as_posix()
        return {"manifest": path.relative_to(self.directory).as_posix(), "render": render}, [path, artifact]

    def qa(self):
        validate_editorial(self.read("evidence"), self.read("story"))
        return {"evidence_gate": "passed", "viewer_takeaway_gate": "passed", "publication_allowed": False,
                "blockers": ["mock render is not playable media", "user voice recording not supplied", "editorial release review pending"]}, []

    def publish_package(self):
        qa = self.read("qa")
        return {"status": "review_only", "publication_allowed": False, "uploaded": False,
                "blockers": qa["blockers"], "story": "artifacts/story/story.json",
                "production": "artifacts/video/production.json"}, []

    def learning(self):
        return {"engineering_result": self.read("evidence")["claims"][0]["statement"],
                "revenue": None, "cost": None, "production_hours": None, "profit_per_production_hour": None,
                "business_conclusion": "Unmeasured; do not infer profit from avoided stage calls.",
                "next_experiment": "Test interruption during a stage and external side-effect deduplication.",
                "revenue_feedback": "Pending live release and measured costs, production hours, and revenue."}, []


def run_case(root):
    root = Path(root)
    manager = RunManager(root)
    run_id = manager.create("printer-local-recovery-e2e", {"experiment_id": "local-checkpoint-recovery-v1"})
    case = RecoveryCase(root, run_id)
    PrinterOrchestrator(manager, root, case.handlers()).execute(run_id, case.exp, stop_after="evidence")
    manager.interrupt(run_id)
    manager = RunManager(root)
    manager.recover(run_id)
    case = RecoveryCase(root, run_id)
    PrinterOrchestrator(manager, root, case.handlers()).execute(run_id, case.exp)
    for stage in PRINTER_STAGES:
        case.read(stage)
    events = [json.loads(line) for line in (case.directory / "events.jsonl").read_text().splitlines()]
    completed = [event["stage"] for event in events if event["event"] == "checkpoint_created"]
    if completed != list(PRINTER_STAGES) or manager.status(run_id)["lifecycle"] != "SUCCEEDED":
        raise PrinterError("E2E lifecycle or stage sequence failed")
    measurements = case.read("execution")
    for arm, expected in (("restart", list(PRINTER_STAGES[:5]) + list(PRINTER_STAGES)),
                          ("recover", list(PRINTER_STAGES))):
        observed = measurements[arm]
        if observed["stages"] != expected or observed["final_lifecycle"] != "SUCCEEDED":
            raise PrinterError(f"{arm} experiment did not meet the stage-sequence gate")
    summary = {"run_id": run_id, "gate": "local-engineering-e2e", "status": "passed",
               "completed_stages": completed, "attempt": manager.status(run_id)["attempt"],
               "measurements": measurements, "publication_allowed": False,
               "scope": "real local recovery measurements with mock production; no live publishing or revenue proof"}
    write_json(case.directory / "e2e-summary.json", summary)
    return summary


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="output/printer-e2e")
    args = parser.parse_args()
    print(json.dumps(run_case(args.output), indent=2))
