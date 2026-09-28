# Phase 6 narration — recovery experiment pilot

Target: ~75–90 seconds  
Voice: project owner / user  
Purpose: evidence-backed pilot narration for live-production validation

## Narration

What happens when an AI workflow gets interrupted halfway through?

The easy answer is: restart it. But if that workflow has already finished expensive or time-consuming steps, restarting means doing work twice.

So I tested a recovery system built around durable checkpoints.

In the restart-from-zero version, the workflow made fifteen stage calls. Five completed stages had to run again.

In the recovery version, the system rebuilt itself from saved state, resumed after the last verified checkpoint, and finished with ten stage calls total.

That means five completed stages were not repeated.

Now, that does **not** mean I proved it saved a specific number of minutes or dollars. I didn't measure that yet. And this test interrupted the workflow between completed stages, not randomly in the middle of every possible operation.

But it proves something narrower and useful: if a workflow records durable progress correctly, an interruption does not automatically have to send the whole job back to zero.

For an AI system doing real business work, that difference could matter.

The next test is harder: interrupt the workflow during a stage, especially around an external action, and see whether recovery stays clean without doing the same real-world action twice.

That's where this gets interesting.

## Evidence boundaries

Supported:
- 15 calls for restart-from-zero
- 10 calls for recovered run
- 5 repeated stages avoided
- 0 completed stages replayed in recovery arm
- final lifecycle SUCCEEDED
- attempt 2 after recovery

Not yet supported:
- minutes saved
- dollars saved
- profit impact
- audience response
- universal/mid-stage crash safety
