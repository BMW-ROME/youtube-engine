"""AI Business Lab printer orchestration layer.

Phase 5C: deterministic stage orchestration around the existing Control Plane.
Media execution remains owned by youtube-engine.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Mapping

PRINTER_STAGES = (
    "intake", "research", "experiment", "execution", "evidence",
    "story", "production", "qa", "publish_package", "learning",
)

ARTIFACT_DIRS = {
    "research": "research",
    "experiment": "experiment",
    "execution": "experiment",
    "evidence": "evidence",
    "story": "story",
    "production": "video",
    "qa": "publish",
    "publish_package": "publish",
    "learning": "analytics",
}

class PrinterError(RuntimeError):
    pass

class PrinterOrchestrator:
    """Run printer stages while preserving run/experiment lineage.

    handlers are injected so production backends, including Higgsfield and
    youtube-engine, remain replaceable and testable.
    """
    def __init__(
        self,
        run_manager: Any,
        root: str | Path,
        handlers: Mapping[str, Callable[[dict[str, Any]], Mapping[str, Any]]] | None = None,
    ) -> None:
        self.run_manager = run_manager
        self.root = Path(root)
        self.handlers = dict(handlers or {})

    def execute(self, run_id: str, experiment: Mapping[str, Any], *, stop_after: str | None = None) -> dict[str, Any]:
        self._validate_experiment(experiment, run_id)
        self._ensure_started(run_id)
        result: dict[str, Any] = {"run_id": run_id, "experiment_id": experiment["experiment_id"], "completed_stages": []}
        for stage in PRINTER_STAGES:
            payload = dict(experiment)
            payload.update({"run_id": run_id, "stage": stage})
            output = self._run_stage(run_id, stage, payload)
            result["completed_stages"].append(stage)
            result[stage] = output
            if stop_after == stage:
                return result
        return result

    def _run_stage(self, run_id: str, stage: str, payload: dict[str, Any]) -> dict[str, Any]:
        handler = self.handlers.get(stage, self._default_handler)
        output = dict(handler(payload) or {})
        artifact = self._write_stage_artifact(run_id, stage, output)
        output["artifact"] = artifact
        self.run_manager.checkpoint(run_id, stage, [artifact])
        return output

    def _write_stage_artifact(self, run_id: str, stage: str, payload: Mapping[str, Any]) -> str:
        directory = ARTIFACT_DIRS.get(stage, stage)
        path = self.root / run_id / "artifacts" / directory
        path.mkdir(parents=True, exist_ok=True)
        target = path / f"{stage}.json"
        target.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return str(target.relative_to(self.root / run_id))

    @staticmethod
    def _default_handler(payload: dict[str, Any]) -> dict[str, Any]:
        return {"status": "prepared", "stage": payload["stage"]}

    def _ensure_started(self, run_id: str) -> None:
        status = self.run_manager.status(run_id)
        if status["lifecycle"] == "CREATED":
            self.run_manager.start(run_id)
        elif status["lifecycle"] != "RUNNING":
            raise PrinterError(f"run is not executable from lifecycle={status['lifecycle']}")

    @staticmethod
    def _validate_experiment(experiment: Mapping[str, Any], run_id: str) -> None:
        required = ("experiment_id", "problem", "hypothesis", "procedure", "success_metrics")
        missing = [key for key in required if key not in experiment]
        if missing:
            raise PrinterError(f"experiment missing required fields: {', '.join(missing)}")
        if experiment.get("run_id", run_id) != run_id:
            raise PrinterError("experiment run_id does not match printer run_id")
