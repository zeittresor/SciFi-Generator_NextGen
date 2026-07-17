from pathlib import Path
import unittest

from theme_manager import ThemeManager

ROOT = Path(__file__).resolve().parents[1]


class ThemeTests(unittest.TestCase):
    def test_all_external_themes_pass_contrast_validation(self):
        manager = ThemeManager(ROOT / "themes")
        manager.load()
        self.assertEqual([], manager.errors)
        self.assertEqual(
            {"Light", "Dark", "Sepia", "Ocean", "Matrix", "Hellfire", "Purple", "Aurora", "Legacy Beige"},
            set(manager.names()),
        )

    def test_each_theme_produces_a_stylesheet(self):
        manager = ThemeManager(ROOT / "themes")
        manager.load()
        for theme in manager.themes.values():
            stylesheet = theme.stylesheet()
            enlarged = theme.stylesheet(1.5)
            self.assertIn("QPushButton", stylesheet)
            self.assertIn("selection-background-color", stylesheet)
            self.assertIn("min-height: 28px", stylesheet)
            self.assertIn("min-height: 42px", enlarged)
            self.assertIn("QScrollBar:vertical", enlarged)


if __name__ == "__main__":
    unittest.main()
