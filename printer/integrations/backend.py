"""Provider-neutral production backend contract for the Printer."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol


@dataclass(frozen=True)
class ProductionArtifact:
    backend: str
    artifact_path: str
    media_type: str
    metadata: dict[str, Any]


class ProductionBackend(Protocol):
    name: str

    def render(self, manifest: Mapping[str, Any], output_dir: str | Path) -> ProductionArtifact:
        """Render a production manifest into a provider-specific artifact."""
        ...
