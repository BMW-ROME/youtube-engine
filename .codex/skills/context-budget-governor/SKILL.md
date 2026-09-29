---
name: context-budget-governor
description: Minimize unnecessary token and model usage while preserving sufficient technical context to complete goals. Use during long chats, large repositories, complex research, agent workflows, or any usage-limit/context-pressure risk.
---

# Context Budget Governor

Primary rule: spend tokens on execution, not reconstruction.

Classify context:

- T0 invariant: mission, hard constraints, architecture principles, established conventions.
- T1 active state: current milestone, active implementation, blockers, interfaces.
- T2 execution evidence: source files, diffs, tests, logs.
- T3 history: superseded approaches, old debugging, completed brainstorming.

Default load: T0 summary + T1 + only necessary T2. Do not load T3 unless evidence requires it.

Pressure levels:

## GREEN
Normal execution.

## YELLOW
Context is growing materially.
- compact repeated information
- summarize completed work
- retrieve selectively
- split large work into atomic packets
- update continuation state

## ORANGE
Usage warning, rapidly expanding context, large task, or likely boundary.
- finish the current safe atomic operation
- stop opening unrelated context
- checkpoint
- record the exact next action
- update the continuation capsule
- isolate independent work into separate packets

## RED
The active model/session can no longer reliably continue or a provider limit is reached.
- do not attempt to evade provider limits
- preserve completed work
- persist unresolved work
- make `.workspace-control/handoff.md` sufficient for a fresh worker
- resume from durable workspace state on another available execution surface/model

Compression must preserve facts, constraints, interfaces, decisions, paths, IDs, commits, errors, commands, validation evidence, and next actions. Compress repetition, narration, and abandoned brainstorming.

Use progressive disclosure:
1. `.workspace-control/state.json`
2. active workstream
3. exact files/diffs/tests
4. historical evidence only if necessary

For build work, target effort roughly toward execution first, then verification, state persistence, and explanation.
