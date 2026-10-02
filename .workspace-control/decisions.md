# Decisions

## D-001 — Repository is the continuity authority
Chats and individual model sessions are temporary workers. Durable project state lives in versioned workspace files.

## D-002 — Layer onto Control Plane v0.1
Workspace continuity is built on branch `workspace-continuity-v0.1`, based on `control-plane-v0.1`, so it can reuse and test the existing recovery foundation from PR #10.

## D-003 — Separate runtime state from project state
`control_plane/` owns runtime job lifecycle and media-pipeline recovery.
`.workspace-control/` owns project/workspace continuity across agents, chats, models, and usage boundaries.

They may reference each other but must not silently conflate schemas or lifecycle semantics.

## D-004 — Model-agnostic checkpointing
Continuity must not depend on a specific model, exact hidden token count, or a single chat thread.

## D-005 — No provider-limit evasion
The system reduces reconstruction and wasted context; it does not attempt to manufacture quota, bypass caps, or automate prohibited account behavior.
