from __future__ import annotations

from pathlib import Path
import unittest

from story_engine import APP_VERSION

ROOT = Path(__file__).resolve().parents[1]


class V6022DirectTabLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app_source = (ROOT / "app.py").read_text(encoding="utf-8")
        cls.theme_source = (ROOT / "theme_manager.py").read_text(encoding="utf-8")
        cls.verify_source = (ROOT / "tools" / "verify_installation.py").read_text(encoding="utf-8")

    def test_release_version(self):
        self.assertEqual("60.26", APP_VERSION)

    def test_nested_collapsible_widget_is_removed(self):
        self.assertNotIn("class CollapsibleSection", self.app_source)
        self.assertNotIn("collapsibleHeader", self.app_source)
        self.assertNotIn("collapsibleSummary", self.app_source)
        self.assertNotIn("collapsibleContent", self.app_source)
        self.assertNotIn("collapsibleHeader", self.theme_source)

    def test_tab_sections_are_normal_always_visible_group_boxes(self):
        for token in (
            'QGroupBox("Video, Stimme und Übergänge")',
            'QGroupBox("Lieferumfang des Ergebnis-ZIP")',
            'QGroupBox("Prompt-Verfeinerung mit Ollama")',
            'QGroupBox("Lokale Sprachausgabe")',
            'QGroupBox("Brückenatmosphäre")',
            'QGroupBox("Storygenerierung")',
        ):
            self.assertIn(token, self.app_source)

    def test_installer_constructs_main_window_on_windows(self):
        self.assertIn("window = gui_module.MainWindow()", self.verify_source)
        self.assertIn("GUI MainWindow construction smoke test: OK", self.verify_source)


if __name__ == "__main__":
    unittest.main()
