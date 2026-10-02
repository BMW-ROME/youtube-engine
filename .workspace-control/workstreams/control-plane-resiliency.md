# Workstream: Control Plane Resiliency

## Objective
Prove that runtime recovery and workspace/project recovery can coexist cleanly and that a fresh worker can continue implementation without full prior chat context.

## Runtime layer
Owned by `control_plane/`.
Tracks job lifecycle, checkpoints, artifacts, interruption, and recovery.

## Workspace layer
Owned by `.workspace-control/`.
Tracks project goal, progress, decisions, blockers, active work packets, verification evidence, and model-independent handoff state.

## Current proving-ground question
Can a fresh worker resume meaningful resiliency work using only the compact continuation capsule and the exact files named by the active work packet?

## Success evidence
- continuity schema validates
- required files exist
- active work packet references real paths
- existing Control Plane recovery tests remain green
- fresh-worker simulation correctly identifies the next bounded action
