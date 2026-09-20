import json
import tempfile
import unittest
from pathlib import Path

from control_plane.core.state_machine import next_stage


class RecoveryContractTests(unittest.TestCase):
    def test_resume_from_verified_checkpoint(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            checkpoint = root / "checkpoints" / "03_images_complete.json"
            checkpoint.parent.mkdir()
            checkpoint.write_text(json.dumps({
                "schema_version": "1.0",
                "checkpoint_id": "cp-03",
                "run_id": "2026-09-20T041500Z-a13f92c1",
                "stage": "images",
                "attempt": 1,
                "created_at": "2026-09-20T04:22:11Z",
                "verified": True,
                "resume_from": "thumbnail",
                "artifacts": ["artifacts/images.json"],
            }), encoding="utf-8")
            data = json.loads(checkpoint.read_text(encoding="utf-8"))
            self.assertTrue(data["verified"])
            self.assertEqual(next_stage(data["stage"]), data["resume_from"])


if __name__ == "__main__":
    unittest.main()
