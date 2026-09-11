from __future__ import annotations

from pathlib import Path
import unittest

from story_engine import APP_VERSION

ROOT = Path(__file__).resolve().parents[1]


class V6017PyQtGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app_source = (ROOT / "app.py").read_text(encoding="utf-8")
        cls.theme_source = (ROOT / "theme_manager.py").read_text(encoding="utf-8")
        cls.requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")

    def test_release_version(self):
        self.assertEqual("60.17", APP_VERSION)

    def test_runtime_gui_modules_use_pyqt6_only(self):
        self.assertIn("PyQt6>=6.7,<7", self.requirements)
        for filename in ("app.py", "audio_export.py", "tts_services.py"):
            source = (ROOT / filename).read_text(encoding="utf-8")
            self.assertIn("PyQt6", source, filename)
            self.assertNotIn("from PySide6", source, filename)

    def test_task_oriented_category_tabs_are_present(self):
        expected = (
            'addTab(mission_scroll, "Mission")',
            'addTab(media_scroll, "Medienpaket")',
            'addTab(audio_scroll, "Sprache & Audio")',
            'addTab(details_page, "Story & Trace")',
            'addTab(settings_scroll, "Einstellungen")',
        )
        positions = [self.app_source.index(token) for token in expected]
        self.assertEqual(sorted(positions), positions)

    def test_story_trace_has_nested_views(self):
        self.assertIn('self.tabs.addTab(self.story_edit, "Story")', self.app_source)
        self.assertIn('self.tabs.addTab(self.log_edit, "Auswahlprotokoll / Trace")', self.app_source)
        self.assertIn('self.tabs.addTab(self.prompts_edit, "Prompts / Produktion")', self.app_source)

    def test_optional_media_details_are_closed_by_default(self):
        for title in (
            "Video, Stimme und Übergänge (optional)",
            "Lieferumfang des Ergebnis-ZIP (optional)",
            "Prompt-Verfeinerung mit Ollama (optional)",
        ):
            self.assertIn(title, self.app_source)
        self.assertGreaterEqual(self.app_source.count("expanded=False"), 3)

    def test_new_visual_hierarchy_is_theme_driven(self):
        for selector in (
            "QFrame#appHeader",
            "QFrame#heroCard",
            "QLabel#versionBadge",
            "QLabel#stepBadge",
            "QFrame#statusStrip",
        ):
            self.assertIn(selector, self.theme_source)
        self.assertIn('settings.get("theme", "Aurora")', self.app_source)

    def test_category_scrollers_avoid_horizontal_scroll(self):
        self.assertIn("ScrollBarAlwaysOff", self.app_source)
        self.assertIn("ScrollBarAsNeeded", self.app_source)


if __name__ == "__main__":
    unittest.main()
