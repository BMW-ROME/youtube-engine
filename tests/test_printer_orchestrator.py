import json
import tempfile
import unittest
from pathlib import Path

from control_plane.core.run_manager import RunManager
from printer.core.orchestrator import PrinterError, PrinterOrchestrator, PRINTER_STAGES


class PrinterOrchestratorTests(unittest.TestCase):
    def test_full_run_creates_lineage_for_every_stage(self):
        with tempfile.TemporaryDirectory() as td:
            manager = RunManager(td)
            run_id = manager.create("printer", {
                "experiment_id": "exp-001",
            })
            root = Path(td)
            exp = {
                "experiment_id": "exp-001",
                "run_id": run_id,
                "problem": "Test business problem",
                "hypothesis": "The intervention reduces time",
                "procedure": ["baseline", "intervention"],
                "success_metrics": [{"name": "minutes_saved", "target": 30}],
            }
            result = PrinterOrchestrator(manager, root).execute(run_id, exp)
            self.assertEqual(result["completed_stages"], list(PRINTER_STAGES))
            status = manager.status(run_id)
            self.assertEqual(status["stage"], "learning")
            self.assertEqual(status["lifecycle"], "SUCCEEDED")
            self.assertEqual(status["execution"], "COMPLETE")
            self.assertFalse(status["resumable"])
            results = json.loads((root / run_id / "results.json").read_text())
            self.assertTrue(results["success"])
            self.assertEqual(results["outputs"], result)
            events = [json.loads(line) for line in (root / run_id / "events.jsonl").read_text().splitlines()]
            self.assertEqual(events[-1]["event"], "run_succeeded")
            with self.assertRaises(PrinterError):
                PrinterOrchestrator(manager, root).execute(run_id, exp)
            for stage in PRINTER_STAGES:
                artifact = result[stage]["artifact"]
                self.assertTrue((root / run_id / "artifacts" / artifact.split("/", 1)[-1]).exists())

    def test_validation_rejects_mismatched_run(self):
        with tempfile.TemporaryDirectory() as td:
            manager = RunManager(td)
            run_id = manager.create("printer", {"experiment_id": "exp-001"})
            exp = {
                "experiment_id": "exp-001", "run_id": "other-run",
                "problem": "x", "hypothesis": "y", "procedure": [], "success_metrics": []
            }
            with self.assertRaises(PrinterError):
                PrinterOrchestrator(manager, td).execute(run_id, exp)

    def test_stop_after_creates_checkpoint(self):
        with tempfile.TemporaryDirectory() as td:
            manager = RunManager(td)
            run_id = manager.create("printer", {"experiment_id": "exp-001"})
            exp = {
                "experiment_id": "exp-001", "run_id": run_id,
                "problem": "x", "hypothesis": "y", "procedure": [], "success_metrics": []
            }
            result = PrinterOrchestrator(manager, td).execute(run_id, exp, stop_after="evidence")
            self.assertEqual(result["completed_stages"][-1], "evidence")
            self.assertEqual(manager.status(run_id)["last_checkpoint"].split("/")[-1], "evidence-1.json")
            self.assertEqual(manager.status(run_id)["lifecycle"], "RUNNING")
            self.assertTrue(manager.status(run_id)["resumable"])
            self.assertFalse(Path(td, run_id, "results.json").exists())

    def test_stop_after_final_stage_still_succeeds(self):
        with tempfile.TemporaryDirectory() as td:
            manager = RunManager(td)
            run_id = manager.create("printer", {})
            exp = {"experiment_id": "exp-001", "problem": "x", "hypothesis": "y",
                   "procedure": [], "success_metrics": []}
            PrinterOrchestrator(manager, td).execute(run_id, exp, stop_after="learning")
            self.assertEqual(manager.status(run_id)["lifecycle"], "SUCCEEDED")
            self.assertFalse(manager.status(run_id)["resumable"])

    def test_handler_failure_does_not_mark_run_successful(self):
        with tempfile.TemporaryDirectory() as td:
            manager = RunManager(td)
            run_id = manager.create("printer", {})
            exp = {"experiment_id": "exp-001", "problem": "x", "hypothesis": "y",
                   "procedure": [], "success_metrics": []}

            def fail(payload):
                raise RuntimeError("provider unavailable")

            with self.assertRaisesRegex(RuntimeError, "provider unavailable"):
                PrinterOrchestrator(manager, td, {"production": fail}).execute(run_id, exp)
            self.assertEqual(manager.status(run_id)["stage"], "story")
            self.assertEqual(manager.status(run_id)["lifecycle"], "RUNNING")
            self.assertFalse(Path(td, run_id, "results.json").exists())


if __name__ == "__main__":
    unittest.main()
