from __future__ import annotations

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class V6026MlsAliasDefaultTests(unittest.TestCase):
    def test_aliases_are_disabled_by_default_in_gui_and_settings_loader(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn('self.mls_aliases_check.setChecked(False)', source)
        self.assertIn('settings.get("mls_speaker_aliases", False)', source)
        self.assertIn('Fiktive Merknamen für MLS-Sprecher anzeigen (optional)', source)

    def test_explicit_alias_setting_is_still_persisted(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn('"mls_speaker_aliases": self.mls_aliases_check.isChecked()', source)
        self.assertIn('_mls_alias_setting_changed', source)

    def test_alias_metadata_warns_against_gender_inference(self):
        payload = json.loads((ROOT / "data" / "mls_speaker_aliases.json").read_text(encoding="utf-8"))
        self.assertEqual(2, payload["format_version"])
        self.assertEqual(236, len(payload["aliases"]))
        self.assertIn("Geschlechtsangabe", payload["note_de"])
        self.assertIn("standardmäßig ausgeschaltet", payload["note_de"])

    def test_version_is_6026(self):
        self.assertEqual("60.26", (ROOT / "version.txt").read_text(encoding="utf-8").strip())


if __name__ == "__main__":
    unittest.main()
