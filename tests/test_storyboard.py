from pathlib import Path
import unittest

from storyboard_generator import generate_storyboard, render_storyboard_text
from story_engine import StoryEngine

ROOT = Path(__file__).resolve().parents[1]


class StoryboardTests(unittest.TestCase):
    def setUp(self):
        engine = StoryEngine(ROOT / "data" / "vars", ROOT / "sequence_legacy.json")
        self.result = engine.generate(57)

    def test_local_storyboard_scene_count(self):
        scenes = generate_storyboard(self.result, 8)
        self.assertEqual(8, len(scenes))
        self.assertTrue(all(scene.prompt for scene in scenes))
        self.assertTrue(all(scene.summary for scene in scenes))

    def test_scene_count_is_clamped(self):
        self.assertEqual(6, len(generate_storyboard(self.result, 1)))
        self.assertEqual(10, len(generate_storyboard(self.result, 99)))

    def test_rendered_storyboard_contains_sections(self):
        scenes = generate_storyboard(self.result, 7)
        text = render_storyboard_text(scenes, source="Lokal")
        self.assertIn("BILD-PROMPTS / STORYBOARD", text)
        self.assertIn("Quelle: Lokal", text)
        self.assertIn("Prompt:", text)


if __name__ == "__main__":
    unittest.main()
