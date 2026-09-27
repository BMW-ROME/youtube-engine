import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
            # Filesystem timestamp ties must not select an older checkpoint.
            for checkpoint_path in Path(td, run_id, "checkpoints").glob("*.json"):
                os.utime(checkpoint_path, (1000000000, 1000000000))

            manager.interrupt(run_id)
            self.assertEqual(manager.status(run_id)["lifecycle"], "INTERRUPTED")

            resume_stage = manager.recover(run_id)
            self.assertEqual(resume_stage, "story")
            self.assertEqual(manager.status(run_id)["attempt"], 2)

            second = printer.execute(run_id, self._experiment(run_id))
            self.assertEqual(second["resumed_from"], "story")
            self.assertEqual(second["completed_stages"], list(PRINTER_STAGES[5:]))
            self.assertEqual(manager.status(run_id)["stage"], "learning")
            self.assertEqual(manager.status(run_id)["lifecycle"], "SUCCEEDED")
            self.assertEqual(manager.status(run_id)["execution"], "COMPLETE")
            self.assertFalse(manager.status(run_id)["resumable"])
            self.assertTrue(Path(td, run_id, "artifacts", "story", "story.json").exists())

    def test_recovery_after_final_checkpoint_only_finalizes(self):
        with tempfile.TemporaryDirectory() as td:
            manager = RunManager(td)
            run_id = manager.create("printer", {})
            printer = PrinterOrchestrator(manager, td)
            with patch.object(manager, "succeed", side_effect=RuntimeError("interrupted before success")):
                with self.assertRaisesRegex(RuntimeError, "interrupted before success"):
                    printer.execute(run_id, self._experiment(run_id))
            manager.interrupt(run_id)
            self.assertIsNone(manager.recover(run_id))
            with patch.object(printer, "_run_stage", side_effect=AssertionError("stage replayed")):
                result = printer.execute(run_id, self._experiment(run_id))
            self.assertEqual(result["completed_stages"], [])
            self.assertIsNone(result["resumed_from"])
            self.assertEqual(manager.status(run_id)["lifecycle"], "SUCCEEDED")
            self.assertFalse(manager.status(run_id)["resumable"])

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
