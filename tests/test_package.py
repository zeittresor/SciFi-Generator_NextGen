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



    def test_storyboard_prompt_feature_is_packaged(self):
        self.assertTrue((ROOT / "storyboard_generator.py").is_file())
        self.assertTrue((ROOT / "ollama_client.py").is_file())
        app_source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("Bild-Prompts erzeugen", app_source)
        self.assertIn("def generate_storyboard_prompts", app_source)
        self.assertIn("Ollama (lokales Modell)", app_source)
        self.assertIn("self.prompts_edit", app_source)

    def test_target_ai_prompt_profiles_are_packaged(self):
        app_source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("Zielsystem / LLM:", app_source)
        self.assertIn("PromptProfileManager", app_source)
        self.assertIn("storyboard_target_ai", app_source)
        self.assertTrue((ROOT / "prompt_profile_manager.py").is_file())
        for filename in (
            "01_chatgpt.json",
            "02_grok.json",
            "03_gemini.json",
            "04_stable_diffusion.json",
            "05_other.json",
        ):
            self.assertTrue((ROOT / "prompt_profiles" / filename).is_file())


    def test_total_media_package_prompt_is_packaged(self):
        self.assertTrue((ROOT / "media_package_generator.py").is_file())
        app_source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("Gesamtpaket (Bilder + Audio + Video)", app_source)
        self.assertIn("Gesamtpaket-Prompt erzeugen", app_source)
        self.assertIn("render_media_package_text", app_source)
        self.assertIn("storyboard_transition_seconds", app_source)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("## Gesamtpaket-Prompt: Bilder, Audio und Video", readme)
        self.assertIn("build_story_video.py", readme)
        self.assertIn("package_voice_character", app_source)
        self.assertIn("package_voice_gender", app_source)
        self.assertIn("package_voice_quality", app_source)
        self.assertIn("Menschlich / natürlich", app_source)
        self.assertIn("Robotisch / synthetisch", app_source)
        self.assertIn("Stimmcharakter", readme)
        self.assertIn("Videoauflösung:", app_source)
        self.assertIn("1024 × 1024 (1:1, Standard)", app_source)
        self.assertIn("3840 × 2160 (4K UHD, 16:9)", app_source)
        self.assertIn("package_video_resolution_preset", app_source)
        self.assertIn("Benutzerdefiniert", app_source)
        self.assertIn("1024 × 1024", readme)
        self.assertIn("4K UHD", readme)

if __name__ == "__main__":
    unittest.main()
