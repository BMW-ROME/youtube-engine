# Next

## Active packet

`.workspace-control/work-packets/WP-002.yaml`

## Immediate

1. Extend `scripts/bootstrap_workspace_control.py` to validate active work-packet input paths and relevant state references.
2. Add negative tests proving stale/missing references fail validation.
3. Add deterministic checkpoint refresh/update behavior so state and handoff are less dependent on manual edits.
4. Run the continuity CI gate.

## Integration follow-up

The proving ground corrected `tests/test_interruption_recovery.py`, originally introduced by PR #10. Preserve that correction when resolving the stacked PR sequence.
