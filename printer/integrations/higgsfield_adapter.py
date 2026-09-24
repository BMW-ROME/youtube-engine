"""Higgsfield production handoff contract.

The adapter deliberately stops at a backend request object. Credentials and
provider execution remain outside the repository's durable experiment state.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class HiggsfieldShotRequest:
    experiment_id: str
    run_id: str
    shot_id: str
    prompt: str
    aspect_ratio: str = "16:9"
    duration_seconds: int = 5
    resolution: str = "720p"

    def as_generation_params(self) -> dict[str, Any]:
        return {
            "model": "seedance_2_5",
            "mode": "t2v",
            "prompt": self.prompt,
            "aspect_ratio": self.aspect_ratio,
            "duration": self.duration_seconds,
            "resolution": self.resolution,
            "generate_audio": False,
        }

def build_requests(manifest: dict[str, Any]) -> list[HiggsfieldShotRequest]:
    return [
        HiggsfieldShotRequest(
            experiment_id=manifest["experiment_id"],
            run_id=manifest["run_id"],
            shot_id=shot["shot_id"],
            prompt=shot["visual_prompt"],
            aspect_ratio=shot.get("aspect_ratio", "16:9"),
            duration_seconds=int(shot.get("duration_seconds", 5)),
            resolution=shot.get("resolution", "720p"),
        )
        for shot in manifest["shots"]
    ]
