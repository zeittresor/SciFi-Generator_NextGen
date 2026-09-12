from __future__ import annotations

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

from story_engine import APP_VERSION, StoryEngine

ROOT = Path(__file__).resolve().parents[1]
VARS = ROOT / "data" / "vars"
BRANCH_MANIFEST = ROOT / "data" / "branch_fragments_v60.16.json"
EXPANSION_MANIFEST = ROOT / "data" / "fragment_expansion_v60.16.json"
REPAIR_MANIFEST = ROOT / "data" / "fragment_repairs_v60.16.json"
CONSOLE = ROOT / "scifi_console.py"


def read_nonblank(path: Path) -> list[str]:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return [line.strip() for line in raw.decode(encoding).splitlines() if line.strip()]
        except UnicodeDecodeError:
            continue
    raise AssertionError(f"Could not decode {path}")


class V6016ConsoleAndQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = StoryEngine(VARS, ROOT / "sequence_legacy.json")
        cls.branch_manifest = json.loads(BRANCH_MANIFEST.read_text(encoding="utf-8"))
        cls.expansion_manifest = json.loads(EXPANSION_MANIFEST.read_text(encoding="utf-8"))
        cls.repairs = json.loads(REPAIR_MANIFEST.read_text(encoding="utf-8"))

    def _repair_set(self, manifest_name: str, filename: str) -> set[str]:
        section = self.repairs["manifests"][manifest_name]["removed_or_rewritten_lines"]
        return {line.strip().casefold() for line in section.get(filename, [])}

    def test_version_and_console_assets(self):
        self.assertEqual("60.26", APP_VERSION)
        self.assertEqual("60.26", (ROOT / "version.txt").read_text(encoding="utf-8").strip())
        for relative in (
            "scifi_console.py",
            "run_console.sh",
            "start_console.bat",
            "requirements_console.txt",
            "tools/audit_stories.py",
        ):
            self.assertTrue((ROOT / relative).is_file(), relative)

    def test_v6016_branch_manifest(self):
        p = self.branch_manifest
        self.assertEqual("60.16", p["version"])
        self.assertEqual(59, p["file_count"])
        self.assertEqual(7, p["lines_per_file"])
        self.assertEqual(413, p["total_lines"])
        self.assertEqual(59, len(p["files"]))
        for filename, documented in p["files"].items():
            with self.subTest(filename=filename):
                self.assertEqual(7, len(documented))
                current = {line.casefold() for line in read_nonblank(VARS / filename)}
                repaired = self._repair_set(BRANCH_MANIFEST.name, filename)
                for line in documented:
                    key = line.strip().casefold()
                    self.assertTrue(key in current or key in repaired)

    def test_v6016_every_sentence_file_received_seven_expansions(self):
        p = self.expansion_manifest
        self.assertEqual("60.16", p["version"])
        self.assertEqual(218, p["file_count"])
        self.assertEqual(7, p["added_lines_per_file"])
        self.assertEqual(1526, p["total_added_lines"])
        self.assertEqual(218, len(p["files"]))
        self.assertEqual(218, len(list(VARS.glob("*.ini"))))
        for filename, additions in p["files"].items():
            with self.subTest(filename=filename):
                self.assertEqual(7, len(additions))
                self.assertEqual(7, len({line.casefold() for line in additions}))
                current = {line.casefold() for line in read_nonblank(VARS / filename)}
                repaired = self._repair_set(EXPANSION_MANIFEST.name, filename)
                for line in additions:
                    key = line.strip().casefold()
                    self.assertTrue(
                        key in current or key in repaired,
                        f"Undocumented v60.16 rewrite in {filename}: {line!r}",
                    )

    def test_temperature_fragments_share_a_compatible_grammar_frame(self):
        desc = read_nonblank(VARS / "planet_surface_temperature_desc.ini")
        adder = read_nonblank(VARS / "planet_surface_temperature_adder.ini")
        self.assertTrue(desc)
        self.assertTrue(adder)
        self.assertTrue(all("minus" in line.casefold() for line in desc))
        self.assertTrue(all(line.casefold().startswith("bis ") for line in adder))
        # Every cross-product must form the same grammatical lower/upper-bound frame.
        for left in desc:
            for right in adder:
                phrase = f"{left} sechs {right} zehn Grad Celsius"
                self.assertIn("minus sechs bis", phrase.casefold())
                self.assertIn("plus zehn", phrase.casefold())

    def test_terminal_contract_is_explicit_and_structural(self):
        self.assertEqual([], self.engine.validate_terminal_invariant())
        self.assertEqual(200, len(self.engine.enumerate_branch_routes()))
        expected = (
            "mission_free_space.ini",
            "mission_end_status.ini",
            "ship_liftoff_jumpready.ini",
            "mission_jump_prompt.ini",
        )
        for seed in range(300):
            result = self.engine.generate(seed=seed, legacy_umlauts=False)
            tail = tuple(Path(item.source).name for item in result.selections[-4:])
            self.assertEqual(expected, tail)
            self.assertIn("frei", result.selections[-4].raw_text.casefold())

    def test_quality_sanity_on_1000_deterministic_stories(self):
        bad_punctuation = re.compile(r"\.\.|\.,|,\.|,,| {3,}")
        duplicate_word = re.compile(r"\b([A-Za-zÄÖÜäöüß]{4,})\s+\1\b", re.IGNORECASE)
        observed_routes = set()
        for seed in range(1000):
            result = self.engine.generate(seed=seed, legacy_umlauts=False)
            observed_routes.add(tuple((b.branch_id, b.choice_id) for b in result.branches))
            self.assertIsNone(bad_punctuation.search(result.raw_story), f"seed={seed}")
            for marker in self.engine.REPETITIVE_CLAUSE_MARKERS:
                self.assertLessEqual(result.raw_story.count(marker), 1, f"seed={seed}, marker={marker}")
            for selection in result.selections:
                text = selection.rendered_text or selection.raw_text
                self.assertIsNone(
                    duplicate_word.search(text),
                    f"seed={seed}, {selection.source}:{selection.line_number}: {text!r}",
                )
        self.assertGreaterEqual(len(observed_routes), 160)

    def run_console(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CONSOLE), *args],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_console_default_outputs_story_only(self):
        proc = self.run_console("--seed", "57", "--raw")
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertTrue(proc.stdout.strip())
        self.assertNotIn("TRACE:", proc.stdout)
        self.assertNotIn("SCIFI-GENERATOR", proc.stdout)

    def test_console_trace_exposes_source_file_and_line_in_story_order(self):
        proc = self.run_console("--seed", "57", "--trace", "--raw")
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertIn("--- TRACE: STORY ROUTE ---", proc.stdout)
        self.assertIn("--- TRACE: FRAGMENTS IN OUTPUT ORDER ---", proc.stdout)
        self.assertRegex(proc.stdout, r"001 \| data/vars/sternzeit_name\.ini:\d+ \|")
        self.assertIn("mission_free_space.ini", proc.stdout)

    def test_console_json_trace_is_machine_readable(self):
        proc = self.run_console("--seed", "57", "--json", "--trace", "--raw")
        self.assertEqual(0, proc.returncode, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(57, payload["seed"])
        self.assertEqual("60.26", payload["version"])
        self.assertTrue(payload["story"])
        self.assertTrue(payload["branch_path"])
        self.assertTrue(payload["selections"])
        self.assertEqual("data/vars/sternzeit_name.ini", payload["selections"][0]["source"])

    def test_console_validate(self):
        proc = self.run_console("--validate")
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertIn("all branch paths return to the common jump-ready ending", proc.stdout)


if __name__ == "__main__":
    unittest.main()
