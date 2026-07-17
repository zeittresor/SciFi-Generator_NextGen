from pathlib import Path
import unittest

from story_engine import APP_VERSION, StoryEngine

ROOT = Path(__file__).resolve().parents[1]


class StoryEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = StoryEngine(ROOT / "data" / "vars", ROOT / "sequence_legacy.json")

    def test_all_sources_exist(self):
        self.assertEqual([], self.engine.validate_sources())

    def test_seed_is_deterministic(self):
        first = self.engine.generate(123456)
        second = self.engine.generate(123456)
        self.assertEqual(first.raw_story, second.raw_story)
        self.assertEqual(first.display_story, second.display_story)

    def test_generation_has_full_trace(self):
        result = self.engine.generate(57)
        self.assertGreater(len(result.selections), 80)
        self.assertIn("App-Version: " + APP_VERSION, result.build_log())
        self.assertTrue(result.display_story)

    def test_legacy_umlauts_can_be_disabled(self):
        result = self.engine.generate(57, legacy_umlauts=False)
        self.assertEqual(result.raw_story, result.display_story)


if __name__ == "__main__":
    unittest.main()
