# Mission

Make `BMW-ROME/youtube-engine` production-grade while preserving forward progress across model limits, context ceilings, chat boundaries, interruptions, and agent/model switching.

The repository is the durable source of truth. Conversations and individual model sessions are temporary execution surfaces.

## Governing principles

1. Do not bypass provider usage limits.
2. Make continuation cheap enough that another capable worker can resume without reconstructing full history.
3. Prefer bounded, verifiable work packets.
4. Persist decisions, blockers, tests, exact paths, commits, and next actions.
5. Keep continuity state compact.
6. Treat Control Plane v0.1 as the first proving ground for recovery-aware workspace execution.
