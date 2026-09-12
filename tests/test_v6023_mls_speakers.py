from __future__ import annotations

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class V6023MlsSpeakerTests(unittest.TestCase):
    def test_mls_catalog_exposes_speaker_selector(self):
        payload = json.loads((ROOT / "tts_package_catalog.json").read_text(encoding="utf-8"))
        package = next(item for item in payload["packages"] if item["id"] == "piper-de-mls-medium")
        self.assertTrue(package["speaker_selector"])
        self.assertEqual("Sprecher", package["speaker_selector_label"])
        self.assertEqual("2422", package["default_speaker"])

    def test_large_multispeaker_models_use_scrollable_list(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("self.piper_speaker_list = QListWidget()", source)
        self.assertIn("len(entry.get(\"speaker_options\") or []) > 32", source)
        self.assertIn("MLS-ID", source)
        self.assertIn("Qt.ItemDataRole.UserRole", source)

    def test_small_style_models_keep_compact_combo(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("self.piper_style_combo = QComboBox()", source)
        self.assertIn("PIPER_STYLE_LABELS", source)


if __name__ == "__main__":
    unittest.main()
