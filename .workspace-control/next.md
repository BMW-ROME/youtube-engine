# Next

## Immediate

1. Run `pytest -q tests/test_workspace_continuity.py`.
2. Run the existing Control Plane recovery tests.
3. Simulate a fresh worker by reading only:
   - `.workspace-control/state.json`
   - `.workspace-control/handoff.md`
   - `.workspace-control/work-packets/WP-001.yaml`
   - the exact source/test files referenced by WP-001
4. Confirm the worker can identify the next action without prior chat context.

## After verification

- Add a small CLI command for checkpoint refresh if manual state editing proves error-prone.
- Decide whether CI should validate state schema and work-packet references on every continuity-related PR.
- Reuse the bundle in the next repository/project only after the proving-ground resume test passes.
