from __future__ import annotations

from pathlib import Path
import json
import unittest

ROOT = Path(__file__).resolve().parents[1]
VARS = ROOT / "data" / "vars"
MANIFEST = ROOT / "data" / "fragment_expansion_v60.14.json"


def read_nonblank(path: Path) -> list[str]:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = raw.decode(encoding)
            return [line.strip() for line in text.splitlines() if line.strip()]
        except UnicodeDecodeError:
            continue
    raise AssertionError(f"Could not decode {path}")


class FragmentExpansionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_manifest_declares_expected_scope(self):
        self.assertEqual("60.14", self.payload["version"])
        self.assertEqual(87, self.payload["file_count"])
        self.assertEqual(7, self.payload["added_lines_per_file"])
        self.assertEqual(609, self.payload["total_added_lines"])
        self.assertEqual(87, len(self.payload["files"]))

    def test_each_ini_contains_all_seven_documented_additions(self):
        for filename, additions in self.payload["files"].items():
            with self.subTest(filename=filename):
                self.assertEqual(7, len(additions))
                self.assertEqual(7, len({line.casefold() for line in additions}))
                path = VARS / filename
                self.assertTrue(path.is_file())
                lines = {line.casefold() for line in read_nonblank(path)}
                for addition in additions:
                    self.assertIn(addition.strip().casefold(), lines)

    def test_manifest_covers_every_ini_file(self):
        actual = {path.name for path in VARS.glob("*.ini")}
        declared = set(self.payload["files"])
        self.assertTrue(declared.issubset(actual))


if __name__ == "__main__":
    unittest.main()
