import tempfile
import unittest
from pathlib import Path

from printer.core.production import ProductionError, render_manifest
from printer.integrations.mock_backend import MockProductionBackend


class PrinterProductionTests(unittest.TestCase):
    def _manifest(self, run_id="run-001"):
        return {
            "schema_version": "1.0",
            "experiment_id": "exp-001",
            "run_id": run_id,
            "script": {"path": "story/script.txt"},
            "shots": [
                {
                    "shot_id": "shot-001",
                    "purpose": "hook",
                    "visual_prompt": "Business owner reviewing an automation workflow",
                    "duration_seconds": 5,
                },
                {
                    "shot_id": "shot-002",
                    "purpose": "evidence",
                    "visual_prompt": "Clean dashboard showing measured time savings",
                    "duration_seconds": 6,
                },
            ],
        }

    def test_mock_backend_renders_without_provider_credits(self):
        with tempfile.TemporaryDirectory() as td:
            result = render_manifest(
                self._manifest(),
                "run-001",
                MockProductionBackend(),
                Path(td) / "video",
            )
            self.assertEqual(result["status"], "rendered")
            self.assertEqual(result["backend"], "mock-local")
            self.assertTrue(Path(result["artifact"]).exists())
            self.assertEqual(result["metadata"]["shot_count"], 2)
            self.assertEqual(result["metadata"]["duration_seconds"], 11.0)

    def test_manifest_run_id_is_enforced(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ProductionError):
                render_manifest(
                    self._manifest("other-run"),
                    "run-001",
                    MockProductionBackend(),
                    td,
                )

    def test_provider_failure_isolated_from_manifest_contract(self):
        class FailingBackend:
            name = "provider-failure"

            def render(self, manifest, output_dir):
                raise RuntimeError("provider unavailable")

        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(RuntimeError):
                render_manifest(
                    self._manifest(),
                    "run-001",
                    FailingBackend(),
                    td,
                )


if __name__ == "__main__":
    unittest.main()
