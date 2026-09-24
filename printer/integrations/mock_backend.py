"""Deterministic local backend used to prove the Printer without provider credits."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .backend import ProductionArtifact


class MockProductionBackend:
    name = "mock-local"

    def render(self, manifest: Mapping[str, Any], output_dir: str | Path) -> ProductionArtifact:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        required = ("experiment_id", "run_id", "script", "shots")
        missing = [key for key in required if key not in manifest]
        if missing:
            raise ValueError(f"production manifest missing required fields: {', '.join(missing)}")

        shot_count = len(manifest["shots"])
        duration = sum(float(shot.get("duration_seconds", 0)) for shot in manifest["shots"])
        artifact = out / "mock-render.json"
        artifact.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "backend": self.name,
                    "media_type": "application/x-mock-video",
                    "experiment_id": manifest["experiment_id"],
                    "run_id": manifest["run_id"],
                    "rendered": True,
                    "shot_count": shot_count,
                    "duration_seconds": duration,
                    "shots": manifest["shots"],
                },
                indent=2,
                sort_keys=True,
            ) + "\n",
            encoding="utf-8",
        )
        return ProductionArtifact(
            backend=self.name,
            artifact_path=str(artifact),
            media_type="application/x-mock-video",
            metadata={"shot_count": shot_count, "duration_seconds": duration},
        )
