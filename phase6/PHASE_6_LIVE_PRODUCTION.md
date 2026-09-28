# Phase 6 — Live Production Validation

Status: IN PROGRESS

## Objective

Move from mock production to a real, reviewable media artifact while preserving the Project Constitution.

This phase must validate:

1. real evidence -> narration/story -> playable media
2. the user's voice remains the narration layer
3. provider output does not invent or overstate the experiment result
4. QA checks evidence support and viewer takeaway before publication
5. production time and direct production cost are measured
6. publication remains blocked until all Phase 6 gates pass

## First live-production case

Source experiment: Phase 5 local recovery experiment.

Measured facts:

- restart-from-zero arm: 15 actual stage calls
- recovered arm: 10 actual stage calls
- completed stages replayed by recovery arm: 0
- measured difference: 5 fewer stage calls
- recovered run lifecycle: SUCCEEDED
- recovered run completed on attempt 2

The experiment does **not** establish time savings, profit, audience response, or arbitrary mid-stage crash safety.

## Viewer question

When an AI workflow gets interrupted, can durable checkpoints prevent already-completed stages from being repeated?

## Phase 6 narration rule

The user's recorded voice is the intended final narration. Synthetic narration must not silently replace it.

## Real-provider attempt

Provider: Higgsfield / Seedance 2.5  
Requested output: 5-second, 16:9, 720p, silent B-roll showing interruption -> preserved checkpoint -> resume without restarting completed stages.  
Estimated cost before submission: 35 Higgsfield credits.  
Submission result: BLOCKED by provider with `Requires plus plan or higher.`

This is a provider/account-plan gate. It is not evidence that the Printer failed.

## Current gate state

- evidence basis: PASS
- narration script: PREPARED
- real provider submission: BLOCKED
- playable real-provider media: NOT YET PRODUCED
- user voice recording: REQUIRED
- evidence QA on final media: PENDING
- production time/cost measurement: PARTIAL
- publication_allowed: false
- uploaded: false

## Exit criteria

Phase 6 closes only when:

1. the user records/approves the narration;
2. a real production backend returns playable media;
3. the media is checked against the evidence and viewer-takeaway gates;
4. direct production cost and production time are recorded;
5. the package remains publication-blocked until review explicitly passes.

## Next action

Obtain a user voice take for `phase6/narration.md` and clear or replace the Higgsfield provider-plan gate for the first playable render.
