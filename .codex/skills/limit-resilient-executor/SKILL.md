---
name: limit-resilient-executor
description: Orchestrate long-running project work so progress survives model caps, token ceilings, chat boundaries, and model switching without bypassing provider limits. Use for ambitious multi-step execution where continuity matters.
---

# Limit Resilient Executor

Run this loop:

```
USER QUERY
  -> resolve governing ambition/goal
  -> read compact workspace state
  -> determine the query delta
  -> estimate context/execution cost
  -> select or create an atomic work packet
  -> execute
  -> verify
  -> checkpoint
  -> continue if productive budget remains
  -> hand off cleanly otherwise
```

A work packet should specify:
- id
- goal
- workstream
- inputs
- dependencies
- definition_of_done
- constraints
- verification
- status
- next_on_success

Do not depend on knowing an exact remaining message/token allowance. Infer checkpoint pressure from context growth, file volume, task complexity, explicit usage warnings, model transitions, and session age.

Never attempt to bypass product/provider usage limits. The resilience mechanism is durable state plus bounded work, not cap evasion.

When another worker takes over, it should need only:
1. `.workspace-control/state.json`
2. `.workspace-control/handoff.md`
3. the active work packet
4. the exact source/test files named by that packet

Do not reload unrelated repository history or chat history.
