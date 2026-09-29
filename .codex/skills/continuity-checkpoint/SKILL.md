---
name: continuity-checkpoint
description: Create a compact model-independent continuation state whenever substantial work progresses, interruption is likely, context pressure rises, or another agent/model may continue the work.
---

# Continuity Checkpoint

Objective: a replacement capable model should resume productive work after one compact workspace inspection cycle.

Maintain:

```
.workspace-control/
  mission.md
  state.json
  state.schema.json
  decisions.md
  blockers.md
  next.md
  handoff.md
  workstreams/
  work-packets/
  history/
```

Checkpoint when:
- meaningful implementation completes
- a decision is made
- a bug is isolated
- tests materially change project state
- before large context expansion
- before another agent/model takes over
- a usage warning appears
- before ending a substantial build session

`handoff.md` must contain:
- governing goal
- current state
- materially completed work
- verified evidence
- exact current task
- blockers
- settled decisions
- critical constraints
- exact relevant paths/commits/PRs
- first next action
- ordered follow-on actions
- work that must not be repeated
- unresolved unknowns

Keep the handoff aggressively compact. Large projects should normally remain within roughly 800-1500 useful words.

When a checkpoint is created, update `state.json` and `next.md` in the same logical operation.
