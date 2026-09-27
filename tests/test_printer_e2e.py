import copy
import json
import tempfile
import unittest
from pathlib import Path

from control_plane.core.run_manager import RunManager
from printer.core.orchestrator import PRINTER_STAGES, PrinterError, PrinterOrchestrator
from printer.core.recovery_case import RecoveryCase, run_case, validate_editorial, write_json


class PrinterE2ETests(unittest.TestCase):
    def prepare(self, root, stop="evidence"):
        manager = RunManager(root)
        run_id = manager.create("printer-local-recovery-e2e", {})
        case = RecoveryCase(root, run_id)
        PrinterOrchestrator(manager, root, case.handlers()).execute(run_id, case.exp, stop_after=stop)
        return manager, case

    def test_connected_case_recovers_with_real_measurements_and_blocks_publication(self):
        with tempfile.TemporaryDirectory() as td:
            summary = run_case(td)
            self.assertEqual(summary["completed_stages"], list(PRINTER_STAGES))
            self.assertEqual(summary["attempt"], 2)
            self.assertEqual(summary["measurements"]["restart"]["calls"], 15)
            self.assertEqual(summary["measurements"]["recover"]["calls"], 10)
            self.assertEqual(summary["measurements"]["recover"]["replayed_stages"], 0)
            self.assertEqual(summary["measurements"]["recover"]["stages"], list(PRINTER_STAGES))
            self.assertFalse(summary["publication_allowed"])
            case = RecoveryCase(td, summary["run_id"])
            for stage in PRINTER_STAGES:
                self.assertTrue(case.read(stage))
            production = case.read("production")
            media = case.directory / production["render"]["media_artifact"]
            self.assertTrue(media.is_file())
            self.assertEqual(json.loads(media.read_text())["run_id"], summary["run_id"])
            package = case.read("publish_package")
            self.assertFalse(package["publication_allowed"])
            self.assertFalse(package["uploaded"])
            self.assertIsNone(case.read("learning")["profit_per_production_hour"])
            status = RunManager(td).status(summary["run_id"])
            self.assertEqual(status["lifecycle"], "SUCCEEDED")
            self.assertFalse(status["resumable"])

    def test_uninterrupted_case_has_same_observations(self):
        with tempfile.TemporaryDirectory() as td:
            manager, case = self.prepare(td, stop=None)
            self.assertEqual(manager.status(case.run_id)["attempt"], 1)
            self.assertEqual(manager.status(case.run_id)["lifecycle"], "SUCCEEDED")
            self.assertEqual(case.read("execution")["recover"]["calls"], 10)
            self.assertFalse(case.read("qa")["publication_allowed"])

    def test_missing_or_tampered_raw_evidence_blocks_resume(self):
        for alteration in ("delete", "change"):
            with self.subTest(alteration=alteration), tempfile.TemporaryDirectory() as td:
                manager, case = self.prepare(td)
                raw = case.directory / "artifacts/experiment/measurements/recover/calls.jsonl"
                if alteration == "delete":
                    raw.unlink()
                else:
                    raw.write_text("fabricated replacement", encoding="utf-8")
                manager.interrupt(case.run_id)
                manager.recover(case.run_id)
                with self.assertRaises(PrinterError):
                    PrinterOrchestrator(manager, td, case.handlers()).execute(case.run_id, case.exp)
                self.assertFalse(case.stage_path("story").exists())
                self.assertNotEqual(manager.status(case.run_id)["lifecycle"], "SUCCEEDED")

    def test_cross_run_stage_artifact_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            manager, case = self.prepare(td)
            path = case.stage_path("evidence")
            record = json.loads(path.read_text())
            record["run_id"] = "different-run"
            write_json(path, record)
            with self.assertRaisesRegex(PrinterError, "lineage mismatch"):
                PrinterOrchestrator(manager, td, case.handlers()).execute(case.run_id, case.exp)

    def test_missing_mock_media_blocks_qa_after_recovery(self):
        with tempfile.TemporaryDirectory() as td:
            manager, case = self.prepare(td, "production")
            (case.directory / "artifacts/video/mock-render.json").unlink()
            manager.interrupt(case.run_id)
            manager.recover(case.run_id)
            with self.assertRaises(PrinterError):
                PrinterOrchestrator(manager, td, case.handlers()).execute(case.run_id, case.exp)
            self.assertFalse(case.stage_path("publish_package").exists())

    def test_editorial_gate_rejects_missing_evidence_support_takeaway_and_layers(self):
        evidence = {"observations": [{"id": "o1"}],
                    "claims": [{"statement": "observed result", "supporting_observations": ["o1"]}]}
        story = {"viewer_takeaway": "Check the checkpoint.",
                 "layers": dict.fromkeys(("observation", "inference", "audience_prediction", "business_conclusion"), "explicitly labeled")}
        for defect in ("no_evidence", "no_claim", "unsupported", "no_takeaway", "missing_layer"):
            with self.subTest(defect=defect):
                candidate, narrative = copy.deepcopy(evidence), copy.deepcopy(story)
                if defect == "no_evidence":
                    candidate["observations"] = []
                elif defect == "no_claim":
                    candidate["claims"] = []
                elif defect == "unsupported":
                    candidate["claims"][0]["supporting_observations"] = ["invented"]
                elif defect == "no_takeaway":
                    narrative["viewer_takeaway"] = " "
                else:
                    del narrative["layers"]["business_conclusion"]
                with self.assertRaises(PrinterError):
                    validate_editorial(candidate, narrative)

    def test_artifact_reference_cannot_escape_run(self):
        with tempfile.TemporaryDirectory() as td:
            manager = RunManager(td)
            run_id = manager.create("printer", {})
            case = RecoveryCase(td, run_id)
            with self.assertRaises(PrinterError):
                case.verify_reference({"path": "../outside.txt", "sha256": "untrusted"})


if __name__ == "__main__":
    unittest.main()
