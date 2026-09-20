import json
import unittest
from pathlib import Path

from control_plane.core.state_machine import (
    LIFECYCLE_TRANSITIONS,
    STAGES,
    can_transition,
    next_stage,
    require_transition,
)


class ControlPlaneStateMachineTests(unittest.TestCase):
    def test_allowed_lifecycle_transitions(self):
        self.assertTrue(can_transition("CREATED", "RUNNING"))
        self.assertTrue(can_transition("RUNNING", "INTERRUPTED"))
        self.assertTrue(can_transition("INTERRUPTED", "RECOVERY_REQUIRED"))
        self.assertTrue(can_transition("RECOVERY_REQUIRED", "RUNNING"))
        self.assertTrue(can_transition("RUNNING", "SUCCEEDED"))

    def test_terminal_states_have_no_outgoing_edges(self):
        for state in ("SUCCEEDED", "FAILED", "CANCELLED"):
            self.assertEqual(LIFECYCLE_TRANSITIONS[state], set())

    def test_illegal_transition_is_rejected(self):
        with self.assertRaises(ValueError):
            require_transition("SUCCEEDED", "RUNNING")
        with self.assertRaises(ValueError):
            require_transition("CREATED", "SUCCEEDED")

    def test_stage_order_matches_youtube_engine_contract(self):
        self.assertEqual(STAGES, (
            "script", "voice", "music", "images", "thumbnail",
            "effects", "assembly", "seo", "shorts", "upload",
        ))
        self.assertEqual(next_stage(None), "script")
        self.assertEqual(next_stage("assembly"), "seo")
        self.assertIsNone(next_stage("upload"))

    def test_schema_files_are_valid_json(self):
        root = Path(__file__).parents[1] / "control_plane" / "schemas"
        expected = {
            "manifest.schema.json", "status.schema.json", "event.schema.json",
            "checkpoint.schema.json", "artifact.schema.json", "results.schema.json",
        }
        self.assertEqual({p.name for p in root.glob("*.json")}, expected)
        for path in root.glob("*.json"):
            with path.open(encoding="utf-8") as fh:
                doc = json.load(fh)
            self.assertEqual(doc["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertEqual(doc["type"], "object")


if __name__ == "__main__":
    unittest.main()
