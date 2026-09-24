import tempfile
import unittest
from pathlib import Path

from control_plane.core.run_manager import RunManager
from printer.core.orchestrator import PrinterOrchestrator, PRINTER_STAGES


class PrinterRecoveryTests(unittest.TestCase):
    def _experiment(self, run_id):
        return {
            "experiment_id": "exp-recovery-001",
            "run_id": run_id,
            "problem": "Test business problem",
            "hypothesis": "The intervention reduces time",
            "procedure": ["baseline", "intervention"],
            "success_metrics": [{"name": "minutes_saved", "target": 30}],
        }

    def test_deliberate_interruption_recovers_from_last_verified_checkpoint(self):
        with tempfile.TemporaryDirectory() as td:
            manager = RunManager(td)
            run_id = manager.create("printer", {"experiment_id": "exp-recovery-001"})
            printer = PrinterOrchestrator(manager, td)

            first = printer.execute(run_id, self._experiment(run_id), stop_after="evidence")
            self.assertEqual(first["completed_stages"][-1], "evidence")
            self.assertEqual(manager.status(run_id)["last_checkpoint"], "checkpoints/evidence-1.json")

            manager.interrupt(run_id)
            self.assertEqual(manager.status(run_id)["lifecycle"], "INTERRUPTED")

            resume_stage = manager.recover(run_id)
            self.assertEqual(resume_stage, "story")
            self.assertEqual(manager.status(run_id)["attempt"], 2)

            second = printer.execute(run_id, self._experiment(run_id))
            self.assertEqual(second["resumed_from"], "story")
            self.assertEqual(second["completed_stages"], list(PRINTER_STAGES[5:]))
            self.assertEqual(manager.status(run_id)["stage"], "learning")

    def test_recovery_refuses_missing_checkpoint_artifact(self):
        with tempfile.TemporaryDirectory() as td:
            manager = RunManager(td)
            run_id = manager.create("printer", {"experiment_id": "exp-recovery-001"})
            printer = PrinterOrchestrator(manager, td)
            printer.execute(run_id, self._experiment(run_id), stop_after="evidence")
            manager.interrupt(run_id)

            checkpoint = manager.latest_checkpoint(run_id)
            Path(td, run_id, checkpoint["artifacts"][0]).unlink()

            with self.assertRaises(RuntimeError):
                manager.recover(run_id)


if __name__ == "__main__":
    unittest.main()
