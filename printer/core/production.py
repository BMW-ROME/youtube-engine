"""Provider-neutral production execution and manifest validation."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from printer.integrations.backend import ProductionBackend


class ProductionError(RuntimeError):
    pass


REQUIRED_MANIFEST_FIELDS = ("schema_version", "experiment_id", "run_id", "script", "shots")


def validate_manifest(manifest: Mapping[str, Any], run_id: str) -> None:
    missing = [key for key in REQUIRED_MANIFEST_FIELDS if key not in manifest]
    if missing:
        raise ProductionError(f"production manifest missing required fields: {', '.join(missing)}")
    if manifest["schema_version"] != "1.0":
        raise ProductionError("unsupported production schema_version")
    if manifest["run_id"] != run_id:
        raise ProductionError("production manifest run_id does not match printer run_id")
    if not isinstance(manifest["shots"], list) or not manifest["shots"]:
        raise ProductionError("production manifest requires at least one shot")
    for index, shot in enumerate(manifest["shots"], start=1):
        for field in ("shot_id", "purpose", "visual_prompt"):
            if field not in shot:
                raise ProductionError(f"shot {index} missing required field: {field}")


def render_manifest(
    manifest: Mapping[str, Any],
    run_id: str,
    backend: ProductionBackend,
    output_dir: str | Path,
) -> dict[str, Any]:
    validate_manifest(manifest, run_id)
    result = backend.render(manifest, output_dir)
    artifact = Path(result.artifact_path)
    if not artifact.exists():
        raise ProductionError(f"backend reported missing artifact: {artifact}")
    return {
        "status": "rendered",
        "backend": result.backend,
        "artifact": str(artifact),
        "media_type": result.media_type,
        "metadata": result.metadata,
    }


def load_manifest(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
