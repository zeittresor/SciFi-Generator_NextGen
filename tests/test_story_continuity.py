from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from story_engine import StoryEngine
from story_continuity import StoryContinuity

ROOT = Path(__file__).resolve().parents[1]
VARS = ROOT / "data" / "vars"
SEQUENCE = ROOT / "sequence_legacy.json"


class StoryContinuityTests(unittest.TestCase):
    def test_explicit_seed_keeps_diagnostic_mode_stateless(self):
        with TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "story_state.json"
            engine = StoryEngine(VARS, SEQUENCE, continuity_path=state_path)
            first = engine.generate(57)
            second = engine.generate(57)
            self.assertEqual(first.raw_story, second.raw_story)
            self.assertEqual(first.branch_path, second.branch_path)
            self.assertEqual(0, first.continuity_jump)
            self.assertFalse(state_path.exists())

    def test_due_hook_is_injected_as_side_plot(self):
        with TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "story_state.json"
            continuity = StoryContinuity(state_path)
            state = continuity.default_state()
            state.update({
                "jump_index": 1,
                "next_hook_id": 2,
                "open_hooks": [{
                    "id": "H0001",
                    "kind": "signal",
                    "origin": "distress_signal",
                    "created_jump": 1,
                    "due_jump": 2,
                    "expires_jump": 12,
                    "stage": 1,
                    "strength": 1.5,
                    "last_outcome": "opened",
                }],
            })
            continuity.save(state)

            engine = StoryEngine(VARS, SEQUENCE, continuity_path=state_path)
            result = engine.generate(1, use_continuity=True)
            sources = {item.source for item in result.selections}
            branch_ids = [item.branch_id for item in result.branches]

            self.assertEqual(2, result.continuity_jump)
            self.assertEqual("H0001", result.continuity_hook)
            self.assertIn("data/vars/continuity_signal_return.ini", sources)
            self.assertIn("continuity_response", branch_ids)
            self.assertIn("continuity_outcome", branch_ids)
            self.assertTrue(result.raw_story)

            persisted = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(2, persisted["jump_index"])
            self.assertTrue(persisted["history"])

    def test_previous_route_and_damage_bias_future_weights(self):
        with TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "story_state.json"
            continuity = StoryContinuity(state_path)
            state = continuity.default_state()
            state["recent_routes"] = ["space_only"]
            state["ship_state"]["propulsion"] = 70
            continuity.save(state)
            session = continuity.begin_jump(123)
            biases = continuity.route_weight_biases(session)
            self.assertLess(biases["space_only"], 1.0)
            self.assertGreater(biases["ship_malfunction"], 1.0)

    def test_continuity_fragments_are_validated(self):
        with TemporaryDirectory() as tmp:
            engine = StoryEngine(VARS, SEQUENCE, continuity_path=Path(tmp) / "story_state.json")
            self.assertEqual([], engine.validate_sources())


if __name__ == "__main__":
    unittest.main()
