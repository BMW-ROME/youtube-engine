"""Minimal adapter around the existing youtube-engine production interface.

The adapter intentionally delegates production work to core.pipeline.run_pipeline.
Control Plane state/recovery remains outside the production engine.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Mapping

from core.pipeline import PipelineResult, run_pipeline


def run_youtube_production(
    *,
    topic: str,
    channel_codename: str = "finance",
    config: Mapping[str, Any] | None = None,
    clients: Mapping[str, Any] | None = None,
    video_id: int | None = None,
) -> dict[str, Any]:
    result: PipelineResult = run_pipeline(
        topic=topic,
        channel_codename=channel_codename,
        config=dict(config) if config is not None else None,
        clients=dict(clients) if clients is not None else None,
        video_id=video_id,
    )
    payload = asdict(result)
    payload["success"] = result.success
    return payload
