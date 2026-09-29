# Goal Continuity Stack v0.1

This repository contains four complementary Codex/Agent Skills:

- `goal-control-plane`
- `context-budget-governor`
- `continuity-checkpoint`
- `limit-resilient-executor`

Each skill is a standard directory containing one `SKILL.md` manifest with YAML front matter and instructions. This follows the Agent Skills shape used by Codex-compatible skill systems.

## Repository-local use

Keep the directories under `.codex/skills/` when repository-local skill discovery is supported by your Codex setup.

If your Codex installation expects user-level skills instead, copy or link the four skill directories into the configured Codex skills directory. Do not combine the four `SKILL.md` files into one directory; each skill bundle must keep exactly one manifest.

## Workspace bootstrap

The proving-ground project state lives under `.workspace-control/`.

Validate it with:

```bash
python scripts/bootstrap_workspace_control.py
pytest -q tests/test_workspace_continuity.py
```

Then run the existing Control Plane recovery tests named in `.workspace-control/next.md`.
