---
name: goal-control-plane
description: Maintain durable goal state across chats, models, agents, context windows, rate limits, and interruptions. Use for substantial projects, multi-step ambitions, workspace work, or whenever loss of conversational context would materially slow completion.
---

# Goal Control Plane

Treat the workspace as the durable source of truth. The active chat/model is a temporary execution worker.

For every substantial request:

1. Determine the governing ambition and goal.
2. Resolve the active project, workstream, milestone, task, and action.
3. Read `.workspace-control/state.json`, `next.md`, `decisions.md`, and only the workstream files needed for the current task.
4. Reconcile the latest query with durable state.
5. Identify dependencies, blockers, risks, unresolved questions, and definition of done.
6. Select the smallest useful execution unit.
7. Execute as much as possible now.
8. Verify results with tests, diffs, logs, or other concrete evidence.
9. Persist the resulting state.
10. Leave a compact continuation capsule in `.workspace-control/handoff.md`.

Use this hierarchy:

```
AMBITION
  -> GOAL
     -> PROJECT
        -> WORKSTREAM
           -> MILESTONE
              -> TASK
                 -> ACTION
```

Required durable fields are defined by `.workspace-control/state.schema.json`.

Prefer implementation over repeated planning, verification over speculation, direct artifact inspection over asking the user to repeat known information, bounded tasks over broad context loading, and durable state over chat-only knowledge.

Do not reopen settled decisions without new evidence. Do not require a replacement model to reconstruct the project from full chat history.

Before ending substantial work, update the state and handoff files.
