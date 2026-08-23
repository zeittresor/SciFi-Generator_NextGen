from __future__ import annotations

from pathlib import Path
import json
import unittest

from story_engine import StoryEngine
from storyboard_generator import generate_storyboard, build_visual_bible

ROOT = Path(__file__).resolve().parents[1]
VARS = ROOT / "data" / "vars"
MANIFEST = ROOT / "data" / "branch_fragments_v60.15.json"


class StoryBranchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = StoryEngine(VARS, ROOT / "sequence_legacy.json")
        cls.payload = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_new_branch_fragment_manifest(self):
        self.assertEqual("60.15", self.payload["version"])
        self.assertEqual(72, self.payload["file_count"])
        self.assertEqual(7, self.payload["lines_per_file"])
        self.assertEqual(504, self.payload["total_lines"])
        for filename, expected in self.payload["files"].items():
            with self.subTest(filename=filename):
                lines = [line.strip() for line in (VARS / filename).read_text(encoding="utf-8").splitlines() if line.strip()]
                self.assertEqual(expected, lines)
                self.assertEqual(7, len(lines))
                self.assertEqual(7, len({line.casefold() for line in lines}))

    def test_all_major_and_nested_routes_are_reachable(self):
        expected = {
            ("alien_encounter",),
            ("planet_nature", "natural_forces"),
            ("planet_nature", "destructive_flora"),
            ("planet_nature", "destructive_fauna"),
            ("space_only", "debris_field"),
            ("space_only", "unknown_station"),
            ("space_only", "restricted_zone"),
            ("space_only", "space_phenomenon"),
            ("abandoned_site", "surface_ruins"),
            ("abandoned_site", "orbital_ruins"),
        }
        found = set()
        for seed in range(500):
            result = self.engine.generate(seed)
            found.add(tuple(item.choice_id for item in result.branches))
        self.assertTrue(expected.issubset(found))

    def test_every_route_has_ten_storyboard_boundaries(self):
        representative_seeds = [0, 1, 18, 10, 13, 63, 41, 15, 2, 12]
        for seed in representative_seeds:
            with self.subTest(seed=seed):
                result = self.engine.generate(seed)
                scenes = generate_storyboard(result, 10)
                self.assertEqual(10, len(scenes))
                self.assertTrue(all(scene.narration_text for scene in scenes))
                self.assertIn("Sektorsprung", scenes[-1].title)

    def test_branch_selection_is_deterministic(self):
        for seed in (0, 1, 2, 10, 57, 9999):
            first = self.engine.generate(seed)
            second = self.engine.generate(seed)
            self.assertEqual(first.branch_path, second.branch_path)
            self.assertEqual(first.raw_story, second.raw_story)


    def test_visual_bible_does_not_invent_alien_for_natural_force_route(self):
        result = self.engine.generate(1)
        scenes = generate_storyboard(result, 8)
        bible = dict(build_visual_bible(scenes, "1:1"))
        self.assertNotIn("Fremdlebensform", bible)
        self.assertNotIn("Lokale Flora", bible)
        self.assertNotIn("Lokale Fauna", bible)
        self.assertIn("Planet / Oberfläche", bible)

    def test_space_only_route_does_not_use_planet_landing_or_alien_files(self):
        result = self.engine.generate(13)  # debris_field
        sources = {item.source for item in result.selections}
        self.assertFalse(any("life_alien_" in source for source in sources))
        self.assertFalse(any("planet_surface_landing_" in source for source in sources))
        self.assertFalse(any("ship_liftoff_desc.ini" in source for source in sources))

    def test_nature_routes_do_not_use_intelligent_alien_anatomy_files(self):
        for seed in (1, 18, 10):
            result = self.engine.generate(seed)
            sources = {item.source for item in result.selections}
            self.assertFalse(any("life_alien_" in source for source in sources))
            self.assertTrue(any("ship_liftoff_desc.ini" in source for source in sources))


if __name__ == "__main__":
    unittest.main()
