"""Control Plane v0.1 lifecycle and stage transition contract."""

from __future__ import annotations

LIFECYCLE_TERMINAL = {"SUCCEEDED", "FAILED", "CANCELLED"}
LIFECYCLE_TRANSITIONS = {
    "CREATED": {"RUNNING", "CANCELLED"},
    "RUNNING": {"PAUSED", "INTERRUPTED", "SUCCEEDED", "FAILED", "CANCELLED"},
    "PAUSED": {"RUNNING"},
    "INTERRUPTED": {"RECOVERY_REQUIRED"},
    "RECOVERY_REQUIRED": {"RUNNING", "FAILED", "CANCELLED"},
    "SUCCEEDED": set(),
    "FAILED": set(),
    "CANCELLED": set(),
}

STAGES = (
    "script", "voice", "music", "images", "thumbnail",
    "effects", "assembly", "seo", "shorts", "upload",
)

def can_transition(current: str, target: str) -> bool:
    return target in LIFECYCLE_TRANSITIONS.get(current, set())

def require_transition(current: str, target: str) -> None:
    if not can_transition(current, target):
        raise ValueError(f"illegal lifecycle transition: {current} -> {target}")

def next_stage(stage: str | None) -> str | None:
    if stage is None:
        return STAGES[0]
    try:
        return STAGES[STAGES.index(stage) + 1]
    except (ValueError, IndexError):
        return None
