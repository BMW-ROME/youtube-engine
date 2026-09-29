# Continuation Capsule

## Goal
Make BMW-ROME/youtube-engine production-grade while ensuring project progress can survive model usage limits, context ceilings, interruptions, and worker/model switching.

## Current state
The continuity layer is being added on branch `workspace-continuity-v0.1`, which is based on PR #10's `control-plane-v0.1` branch.

PR #10 contains the first Control Plane v0.1 vertical slice: lifecycle state machine, durable RunManager, YouTube adapter, JSON schemas, and interruption/recovery tests.

## Completed
- Continuity architecture defined.
- Four Codex skills added under `.codex/skills/`.
- Durable `.workspace-control/` bootstrap added.
- State schema and first work packet added.

## Verified evidence
- PR #10 is open and draft.
- Base: `main`.
- Head: `control-plane-v0.1`.
- Head SHA at bootstrap: `5ccefba0929dcabb635291738debff3fd2f245d5`.
- PR is currently reported mergeable.

## Current task
Validate that a fresh worker can resume the Control Plane resiliency work using only compact continuity state plus explicitly referenced files.

## Constraints
- Do not bypass provider/model usage limits.
- Do not reload unrelated repository/chat history.
- Keep runtime Control Plane state separate from project continuity state.
- Preserve settled decisions unless new evidence requires revision.

## Relevant paths
- `.workspace-control/state.json`
- `.workspace-control/work-packets/WP-001.yaml`
- `control_plane/core/run_manager.py`
- `control_plane/core/state_machine.py`
- `tests/test_interruption_recovery.py`
- `tests/test_recovery_contract.py`
- `tests/test_workspace_continuity.py`

## First next action
Run `pytest -q tests/test_workspace_continuity.py`.

## Then
1. Run existing Control Plane recovery tests.
2. Perform fresh-worker resume simulation.
3. Record evidence in state/handoff.
4. Decide whether to add CI validation.

## Do not redo
- Do not redesign the entire Control Plane.
- Do not reconstruct the project from full conversation history.
- Do not create a second competing runtime recovery state machine.

## Unknowns
- Whether the local Codex installation auto-discovers repository-local `.codex/skills` without copy/link configuration.
- Whether continuity validation belongs in existing CI or a dedicated workflow.
