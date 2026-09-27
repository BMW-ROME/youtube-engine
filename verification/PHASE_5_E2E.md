# Phase 5 E2E — local recovery experiment

Date: 2026-09-27. Python 3.13.7 on Windows. Base: `ad4fb32` on `printer-v0.1`.
The project owner selected the local recovery experiment for this gate.

**The connected local-engineering E2E gate passed.** All ten stages ran with
case-specific handlers, the outer run recovered at the evidence checkpoint, and
the final lifecycle was SUCCEEDED on attempt 2. No stage was skipped or replayed
in that outer run. This is a bounded engineering validation, not authorization
to publish or proof of live provider operation, commercial outcomes, or arbitrary
mid-stage crash safety.

## Measured result

Run: `2026-09-27T052005Z-442db45e`.

| Arm | Actual stage calls | Repeated stages | Final lifecycle |
| --- | ---: | ---: | --- |
| Restart from zero after five completed stages | 15 | 5 | SUCCEEDED for the replacement run |
| Recover the interrupted run | 10 | 0 | SUCCEEDED |

Each invocation wrote a durable JSONL record. Counts were computed from those
records, not prefilled. Both arms used actual RunManager and PrinterOrchestrator
instances. The intervention reconstructed manager/orchestrator objects from disk.
The deliberate interruption occurred between completed stages; this case does not
kill a process mid-stage. The broader suite separately includes a subprocess
interruption test. The baseline abandoned run remains INTERRUPTED as expected.

Five fewer stage calls is the measured conclusion. It does not establish time
savings, profit, or audience response. Revenue, cost, production hours, and profit
per production hour are explicitly null, with a follow-up measurement requirement.

## Connected artifacts and constitution compliance

`printer/core/recovery_case.py` supplies all ten handlers for this case:

- Intake records the real engineering problem; research snapshots the tested orchestration and recovery source files.
- Experiment records the hypothesis and method; execution runs both arms and preserves raw invocation logs.
- Evidence links observations to logs and claims to observation IDs. SHA-256 references connect stage records and sidecars; each later handler checks the earlier chain.
- Story writes a draft script with separate observation, inference, audience prediction, and business conclusion layers, a viewer takeaway, and scope limitations.
- The Walk With Me Panel is preserved as a planned walkthrough. Multimodal evidence records available code/logs and explicitly lists uncollected audio, video, and screenshots. The user's voice remains planned, not synthesized or replaced.
- Production invokes the existing provider-neutral renderer with MockProductionBackend and saves a manifest and actual mock JSON artifact. The manifest reserves the user's voice recording and references the measured logs.
- QA checks evidence support and the viewer takeaway. Packaging is review-only: `publication_allowed=false`, `uploaded=false`. Mock media, missing user voice, and pending release review are recorded blockers.
- Learning records the narrow engineering conclusion, unknown business metrics, and the next experiment: mid-stage interruption and external side-effect deduplication.

These are case-specific stage envelopes, not a replacement for the generic
evidence/story schemas or a new general-purpose production workflow. Existing
default handlers and lifecycle behavior remain unchanged. Integrity hashes detect
missing/changed artifacts in this flow; they are not digital signatures or a
defense against someone rewriting every record and hash together.

## Exact verification commands and actual output

Run from the repository root in PowerShell:

```powershell
python -m printer.core.recovery_case --output output/printer-e2e > verification/phase5-e2e-result.json
python -m unittest discover -s tests -p 'test_printer_*.py' -v *> verification/phase5-e2e-targeted.txt
$env:OPENAI_API_KEY='test-only-not-a-real-key'
python -m unittest discover -s tests -v *> verification/phase5-e2e-full-suite.txt
git diff --check
```

| Check | Passed | Failed/errors | Result |
| --- | ---: | ---: | --- |
| First targeted execution | 18 | 0 | OK, 9.946s |
| Final captured targeted execution | 18 | 0 | OK, 9.906s, exit 0 |
| Full suite | 26 | 0 | OK, 10.667s, exit 0 |
| E2E command | all 10 stages | 0 | passed, exit 0 |

The full-suite dummy key only satisfies configuration loading for the mocked
YouTube adapter. This case needs no credentials and makes no provider requests.
Negative tests cover absent/changed raw evidence, cross-run stage records,
missing render artifacts, unsupported claims, absent evidence/takeaway/layers,
and artifact paths outside the run. Both uninterrupted and recovered cases pass.

## Evidence and changed files

- `printer/core/recovery_case.py`: runnable connected case and publication-blocked review package.
- `tests/test_printer_e2e.py`: seven E2E/negative tests, including subcases.
- `verification/phase5-e2e-result.json`: actual command output and measured result.
- `verification/phase5-e2e-targeted.txt`, `verification/phase5-e2e-full-suite.txt`: raw test output.
- `verification/phase5-e2e-artifacts.zip`: all 102 files from the captured run, including nested measurements, source snapshots, script, manifests, checkpoints, events, statuses, and results. ZIP integrity checked successfully.
- `verification/PHASE_5_E2E.md`: this report.

The standalone `e2e-summary.json` is the full-run gate summary. The legacy
RunManager `results.json` retains its existing format, including the orchestrator's
per-invocation completed-stage list; it is not used as the sole full-run proof.

## Next gate

Phase 6 live-production validation: prepare and review the user-led narration,
use a real production backend to create playable media, inspect it against the
evidence and viewer-takeaway gates, and measure production cost/time. Actual
publishing and revenue feedback remain downstream and unverified. Do not remove
the mock case's publication block to simulate that gate passing.
