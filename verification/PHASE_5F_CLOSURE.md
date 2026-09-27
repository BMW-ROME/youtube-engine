# Phase 5F runtime closure

Verified 2026-09-27 on Windows with Python 3.13.7, starting from remote
`printer-v0.1` at `4576504cc11bb368b8e4468e2055702867654da7`.
That commit adds the three production tests; the branch contained no later commits at inspection.

**Phase 5F is closed for the deterministic, provider-neutral runtime gate.**
This does not close the full Phase 5 E2E gate or prove live provider/publishing operation.

## Actual executions

Commands were run from the repository root in PowerShell:

```powershell
python --version
python -m unittest discover -s tests -p 'test_printer_*.py' -v
python -m unittest discover -s tests -v
$env:OPENAI_API_KEY='test-only-not-a-real-key'
python -m unittest discover -s tests -v
```

| Execution | Passed | Failures | Errors | Outcome |
| --- | ---: | ---: | ---: | --- |
| Original targeted suite | 5 | 3 | 0 | Windows path serialization/assertion failures |
| Targeted suite after lifecycle/recovery fixes | 11 | 0 | 0 | OK |
| First broader discovery | 17 | 0 | 2 | Broken subprocess harness; adapter import requires OPENAI_API_KEY |
| Broader discovery after harness fix, dummy configuration key | 19 | 0 | 0 | OK |
| Final captured targeted suite | 11 | 0 | 0 | OK, 1.492s, exit 0 |
| Final captured broader suite | 19 | 0 | 0 | OK, 1.797s, exit 0 |

The broader adapter test mocks `run_pipeline`; the dummy key is not a credential
and no real provider request is exercised. The targeted suite needs no key.
The first broader run's 19 entries include one failed module import rather than
an executed adapter test. Original runs also emitted an unclosed event-file warning.

Final output was captured with:

```powershell
python -m unittest discover -s tests -p 'test_printer_*.py' -v *> verification/phase5f-targeted.txt
$env:OPENAI_API_KEY='test-only-not-a-real-key'
python -m unittest discover -s tests -v *> verification/phase5f-full-suite.txt
```

See the adjacent raw output files. The production test executes the local mock,
checks its artifact exists, and verifies 2 shots and 11.0 seconds. It also checks
cross-run manifest rejection and provider failure propagation.

## Changes

- `PROJECT_CONSTITUTION.md`: project identity, evidence separation, voice, architectural protections, publishing gates, economics, and amendment rules.
- `AGENTS.md`: mandatory constitution entry point for future agents.
- `printer/core/orchestrator.py`: call `RunManager.succeed()` after all stages, including a final-stage stop; resume after the durable completed checkpoint rather than skipping the stage named in recovery status; serialize artifact paths portably.
- `control_plane/core/run_manager.py`: serialize checkpoint paths portably; use the persisted checkpoint pointer rather than ambiguous file timestamps; close the event reader.
- `tests/test_printer_orchestrator.py`: terminal lifecycle, persisted results/event, terminal re-execution refusal, partial-stop behavior, final-stage stop, and failure-before-success coverage.
- `tests/test_printer_recovery.py`: no skipped story, terminal recovery, equal timestamp checkpoint selection, and interruption after final checkpoint without replay.
- `tests/test_interruption_recovery.py`: run the child from the repository with `-c`, ensuring imports work and the helper file is not mistaken for a run; bound subprocess runtime.
- `verification/PHASE_5F_CLOSURE.md`, `verification/phase5f-targeted.txt`, `verification/phase5f-full-suite.txt`: this report and runtime evidence.

The baseline test incorrectly accepted a completed run remaining resumable.
The lifecycle contract instead defines SUCCEEDED as terminal; successful execution
now sets `execution=COMPLETE`, `resumable=false`, and writes results.
Partial execution and provider failure do not report success.

## Next Phase 5 gate

Full Printer E2E: connect substantive stage handlers across intake -> research ->
experiment -> execution -> evidence -> story -> production -> QA -> publish package
-> learning, using one traceable experiment and real evidence. Verify artifact lineage,
claim/evidence separation, useful viewer takeaway, production handoff, deliberate
interruption/recovery without skips or replay, terminal success, and learning/revenue
feedback. Confirm the constitution's publication gates before any release.

Current default orchestrator handlers only emit `prepared` markers; their successful
execution is infrastructure evidence, not a completed case study. The mock backend
writes JSON, not a playable video. Phase 6 live production remains a subsequent gate.
