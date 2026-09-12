from __future__ import annotations

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class V6024ProfilesAndAliasesTests(unittest.TestCase):
    def test_mls_alias_file_is_stable_and_complete(self):
        payload = json.loads((ROOT / "data" / "mls_speaker_aliases.json").read_text(encoding="utf-8"))
        aliases = payload["aliases"]
        self.assertEqual(236, len(aliases))
        self.assertEqual(236, len(set(aliases.values())))
        self.assertEqual("Mirko", aliases["2"])
        self.assertIn("keinen echten Namen", payload["note_de"])

    def test_gui_can_toggle_fictional_mls_names(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("Fiktive Merknamen für MLS-Sprecher anzeigen", source)
        self.assertIn("mls_speaker_aliases", source)
        self.assertIn("_format_large_piper_speaker_name", source)
        self.assertIn("MLS-ID", source)

    def test_configuration_profiles_export_and_import_complete_settings(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("Konfiguration speichern …", source)
        self.assertIn("Konfiguration laden …", source)
        self.assertIn("CONFIG_PROFILE_FORMAT", source)
        self.assertIn('"settings": self._collect_settings()', source)
        self.assertIn("def _apply_settings_dict", source)
        self.assertIn('"seed": self.seed_spin.value()', source)
        self.assertIn('_setting_int(settings, "seed", 0)', source)

    def test_settings_are_debounced_and_atomically_autosaved(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("_settings_autosave_timer", source)
        self.assertIn("_connect_settings_autosave", source)
        self.assertIn("_write_json_atomic", source)
        self.assertIn("temp_path.replace(path)", source)

    def test_async_windows_voice_restore_preserves_requested_voice(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("_pending_saved_voice_key", source)
        self.assertIn("self._pending_saved_voice_key or current_key", source)
        self.assertIn("_voice_user_activated", source)


if __name__ == "__main__":
    unittest.main()
