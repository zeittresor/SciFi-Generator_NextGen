from __future__ import annotations

from pathlib import Path
import json
import unittest

from story_engine import StoryEngine
from storyboard_generator import generate_storyboard, build_visual_bible

ROOT = Path(__file__).resolve().parents[1]
VARS = ROOT / "data" / "vars"
MANIFEST = ROOT / "data" / "branch_fragments_v60.15.json"
REPAIRS = ROOT / "data" / "fragment_repairs_v60.16.json"


def read_nonblank(path: Path) -> list[str]:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return [line.strip() for line in data.decode(encoding).splitlines() if line.strip()]
        except UnicodeDecodeError:
            continue
    raise AssertionError(f"Could not decode {path}")


class StoryBranchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = StoryEngine(VARS, ROOT / "sequence_legacy.json")
        cls.payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
        repair_payload = json.loads(REPAIRS.read_text(encoding="utf-8"))
        repaired = repair_payload["manifests"][MANIFEST.name]["removed_or_rewritten_lines"]
        cls.repaired = {
            filename: {line.strip().casefold() for line in lines}
            for filename, lines in repaired.items()
        }

    def test_historical_branch_fragment_manifest(self):
        self.assertEqual("60.15", self.payload["version"])
        self.assertEqual(72, self.payload["file_count"])
        self.assertEqual(7, self.payload["lines_per_file"])
        self.assertEqual(504, self.payload["total_lines"])
        for filename, expected in self.payload["files"].items():
            with self.subTest(filename=filename):
                lines = read_nonblank(VARS / filename)
                current = {line.casefold() for line in lines}
                repaired = self.repaired.get(filename, set())
                self.assertGreaterEqual(len(lines), 7)
                self.assertEqual(len(lines), len({line.casefold() for line in lines}))
                for historical in expected:
                    key = historical.strip().casefold()
                    self.assertTrue(
                        key in current or key in repaired,
                        f"Undocumented v60.15 rewrite in {filename}: {historical!r}",
                    )

    def test_current_major_and_nested_routes_are_reachable(self):
        expected_main = {
            "alien_encounter",
            "planet_nature",
            "space_only",
            "abandoned_site",
            "distress_signal",
            "ship_malfunction",
        }
        found_main = set()
        found_nested = set()
        for seed in range(1000):
            result = self.engine.generate(seed)
            found_main.add(result.branches[0].choice_id)
            found_nested.update(item.choice_id for item in result.branches[1:])
        self.assertEqual(expected_main, found_main)
        for required in (
            "natural_forces", "destructive_flora", "destructive_fauna",
            "debris_field", "unknown_station", "restricted_zone", "space_phenomenon",
            "surface_ruins", "orbital_ruins", "damaged_vessel", "escape_pod",
            "automated_beacon", "navigation_fault", "propulsion_fault", "power_fault",
        ):
            self.assertIn(required, found_nested)

    def test_every_generated_route_has_storyboard_boundaries(self):
        # Representative seeds include all six main mission families.
        for seed in (0, 1, 2, 3, 4, 29, 31, 54, 63, 100):
            with self.subTest(seed=seed):
                result = self.engine.generate(seed)
                scenes = generate_storyboard(result, 10)
                self.assertGreaterEqual(len(scenes), 6)
                self.assertLessEqual(len(scenes), 10)
                self.assertTrue(all(scene.narration_text for scene in scenes))
                self.assertIn("Sektorsprung", scenes[-1].title)

    def test_branch_selection_is_deterministic(self):
        for seed in (0, 1, 2, 10, 57, 9999):
            first = self.engine.generate(seed)
            second = self.engine.generate(seed)
            self.assertEqual(first.branch_path, second.branch_path)
            self.assertEqual(first.raw_story, second.raw_story)

    def test_every_structural_route_returns_to_free_space_and_jump_ready(self):
        self.assertEqual(200, len(self.engine.enumerate_branch_routes()))
        self.assertEqual([], self.engine.validate_terminal_invariant())

    def test_visual_bible_does_not_invent_alien_for_natural_force_route(self):
        result = self.engine.generate(0)
        scenes = generate_storyboard(result, 8)
        bible = dict(build_visual_bible(scenes, "1:1"))
        self.assertNotIn("Fremdlebensform", bible)
        self.assertNotIn("Lokale Flora", bible)
        self.assertNotIn("Lokale Fauna", bible)
        self.assertIn("Planet / Oberfläche", bible)

    def test_space_only_route_does_not_use_planet_landing_or_alien_files(self):
        result = self.engine.generate(1)  # space_only / debris_field
        sources = {item.source for item in result.selections}
        self.assertFalse(any("life_alien_" in source for source in sources))
        self.assertFalse(any("planet_surface_landing_" in source for source in sources))
        self.assertFalse(any("ship_liftoff_desc.ini" in source for source in sources))

    def test_nature_routes_do_not_use_intelligent_alien_anatomy_files(self):
        found = {}
        for seed in range(1000):
            result = self.engine.generate(seed)
            ids = [item.choice_id for item in result.branches]
            if ids and ids[0] == "planet_nature" and len(ids) > 1:
                found.setdefault(ids[1], result)
            if {"natural_forces", "destructive_flora", "destructive_fauna"}.issubset(found):
                break
        self.assertEqual({"natural_forces", "destructive_flora", "destructive_fauna"}, set(found))
        for result in found.values():
            sources = {item.source for item in result.selections}
            self.assertFalse(any("life_alien_" in source for source in sources))
            self.assertTrue(any("ship_liftoff_desc.ini" in source for source in sources))


if __name__ == "__main__":
    unittest.main()
