from pathlib import Path
import re
import unittest

from story_engine import APP_VERSION

ROOT = Path(__file__).resolve().parents[1]


class PackageTests(unittest.TestCase):
    def test_version_matches_central_version_file(self):
        expected = (ROOT / "version.txt").read_text(encoding="utf-8").strip()
        self.assertEqual(expected, APP_VERSION)
        self.assertRegex(APP_VERSION, r"^\d+\.\d+(?:\.\d+)?$")

    def test_windows_voice_scripts_exist(self):
        self.assertTrue((ROOT / "tools" / "list_winrt_voices.ps1").is_file())
        self.assertTrue((ROOT / "tools" / "synthesize_winrt.ps1").is_file())
        self.assertTrue((ROOT / "tools" / "synthesize_sapi.ps1").is_file())

    def test_installer_uses_external_verifier_without_delayed_expansion(self):
        installer = (ROOT / "install_windows.bat").read_text(encoding="utf-8")
        self.assertIn("DisableDelayedExpansion", installer)
        self.assertNotIn("EnableDelayedExpansion", installer)
        self.assertIn("tools\\verify_installation.py", installer)
        self.assertNotIn("story_engine.APP_VERSION !=", installer)

    def test_batch_tools_read_central_version_file(self):
        for filename in ("install_windows.bat", "build_wheelhouse.bat"):
            content = (ROOT / filename).read_text(encoding="utf-8")
            self.assertIn('set /p "VERSION="<"version.txt"', content)
            self.assertIsNone(re.search(r'set "VERSION=\d', content))

    def test_control_panel_uses_scroll_area_with_as_needed_policies(self):
        app_source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("QScrollArea", app_source)
        self.assertIn("setWidgetResizable(True)", app_source)
        self.assertGreaterEqual(
            app_source.count("Qt.ScrollBarPolicy.ScrollBarAsNeeded"),
            2,
        )
        self.assertIn("QLayout.SizeConstraint.SetMinimumSize", app_source)

    def test_responsive_ui_scaling_is_present(self):
        app_source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("def resizeEvent", app_source)
        self.assertIn("def _calculate_ui_scale", app_source)
        self.assertIn("def _update_ui_scale", app_source)
        self.assertIn("QTimer", app_source)
        self.assertIn("QFont", app_source)
        self.assertIn("MAX_UI_SCALE", app_source)
        self.assertIn("QSizePolicy.Policy.MinimumExpanding", app_source)

    def test_readme_is_german_first_with_short_english_summary(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("**Aktuelle Version: " + APP_VERSION + "**", readme)
        self.assertIn("## English summary", readme)
        self.assertLess(readme.index("## Funktionen"), readme.index("## English summary"))
        english = readme.split("## English summary", 1)[1]
        self.assertLess(len(english.split()), 180)

    def test_jump_lifecycle_and_audio_export_are_present(self):
        app_source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("self.story_completed", app_source)
        self.assertIn("jump_missing_story.ini", app_source)
        self.assertIn("jump_story_already_used.ini", app_source)
        self.assertIn("def save_story_audio", app_source)
        self.assertIn("QProgressDialog", app_source)
        self.assertIn("AudioExportWorker", app_source)
        self.assertTrue((ROOT / "audio_mixer.py").is_file())
        self.assertTrue((ROOT / "audio_export.py").is_file())
        self.assertTrue((ROOT / "data" / "vars" / "jump_missing_story.ini").is_file())
        self.assertTrue((ROOT / "data" / "vars" / "jump_story_already_used.ini").is_file())

    def test_audio_dependency_and_documentation(self):
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("numpy", requirements.lower())
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("## Audioexport", readme)
        self.assertIn("FFmpeg", readme)
        self.assertIn("nur einmal vollständig", readme)


if __name__ == "__main__":
    unittest.main()
