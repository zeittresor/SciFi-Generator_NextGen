from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class V6025VoiceManagerTableTests(unittest.TestCase):
    def test_voice_manager_columns_are_interactive_movable_and_sortable(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("QHeaderView.ResizeMode.Interactive", source)
        self.assertIn("setSectionsMovable(True)", source)
        self.assertIn("setSectionsClickable(True)", source)
        self.assertIn("setSortIndicatorShown(True)", source)
        self.assertIn("setSortingEnabled(True)", source)

    def test_voice_manager_table_layout_is_persistent(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn('"tts_manager_column_widths"', source)
        self.assertIn('"tts_manager_column_order"', source)
        self.assertIn('"tts_manager_sort_column"', source)
        self.assertIn('"tts_manager_sort_order"', source)
        self.assertIn("sectionMoved.connect(self._schedule_settings_save)", source)
        self.assertIn("sectionResized.connect(self._schedule_settings_save)", source)
        self.assertIn("sortIndicatorChanged.connect(self._schedule_settings_save)", source)

    def test_population_temporarily_disables_sorting(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("sorting_enabled = self.tts_package_table.isSortingEnabled()", source)
        self.assertIn("self.tts_package_table.setSortingEnabled(False)", source)
        self.assertIn("self.tts_package_table.setSortingEnabled(sorting_enabled)", source)


if __name__ == "__main__":
    unittest.main()
