from pathlib import Path
import unittest

from media_package_generator import MediaPackageSettings, build_media_manifest, render_media_package_text
from prompt_profile_manager import PromptProfileManager
from storyboard_generator import generate_storyboard
from story_engine import StoryEngine

ROOT = Path(__file__).resolve().parents[1]


class MediaPackageTests(unittest.TestCase):
    def setUp(self):
        engine = StoryEngine(ROOT / "data" / "vars", ROOT / "sequence_legacy.json")
        self.scenes = generate_storyboard(engine.generate(57), 8)
        manager = PromptProfileManager(ROOT / "prompt_profiles")
        manager.load()
        self.profile = manager.get("ChatGPT")
        self.assertIsNotNone(self.profile)
        self.settings = MediaPackageSettings(
            voice_name="Microsoft Katja",
            voice_backend="Windows OneCore/WinRT",
            voice_character="Menschlich / natürlich",
            voice_gender="Weiblich",
            voice_quality="Beste verfügbare Qualität",
        )

    def test_prompt_contains_voice_preferences_and_fallback_rule(self):
        text = render_media_package_text(
            self.scenes,
            full_story="Teststory",
            profile=self.profile,
            settings=self.settings,
        )
        self.assertIn("Stimmcharakter: Menschlich / natürlich", text)
        self.assertIn("Stimmliche Wirkung: Weiblich", text)
        self.assertIn("TTS-Qualitätsziel: Beste verfügbare Qualität", text)
        self.assertIn("eSpeak", text)
        self.assertIn("production.log", text)

    def test_manifest_contains_voice_preferences(self):
        manifest = build_media_manifest(
            self.scenes,
            target_name="ChatGPT",
            profile=self.profile,
            settings=self.settings,
        )
        voice = manifest["voice"]
        self.assertEqual("Menschlich / natürlich", voice["character"])
        self.assertEqual("Weiblich", voice["gender_expression"])
        self.assertEqual("Beste verfügbare Qualität", voice["quality_target"])
        self.assertIn("fallback_policy", voice)


    def test_default_video_resolution_is_square_1024(self):
        defaults = MediaPackageSettings()
        self.assertEqual("1024x1024", defaults.resolution)
        self.assertEqual("1:1", defaults.aspect_ratio)
        self.assertEqual(1024, defaults.width)
        self.assertEqual(1024, defaults.height)
        self.assertEqual(8, defaults.fps)

    def test_manifest_contains_exact_video_dimensions(self):
        settings = MediaPackageSettings(
            aspect_ratio="16:9",
            resolution="3840x2160",
            width=3840,
            height=2160,
        )
        manifest = build_media_manifest(
            self.scenes,
            target_name="ChatGPT",
            profile=self.profile,
            settings=settings,
        )
        self.assertEqual("3840x2160", manifest["resolution"])
        self.assertEqual(3840, manifest["width"])
        self.assertEqual(2160, manifest["height"])
        self.assertEqual("16:9", manifest["aspect_ratio"])

    def test_prompt_preserves_aspect_ratio_without_stretching(self):
        settings = MediaPackageSettings(
            aspect_ratio="5:3",
            resolution="1280x768",
            width=1280,
            height=768,
        )
        text = render_media_package_text(
            self.scenes,
            full_story="Teststory",
            profile=self.profile,
            settings=settings,
        )
        self.assertIn("1280x768", text)
        self.assertIn("Seitenverhältnis 5:3", text)
        self.assertIn("Strecke Bilder niemals disproportional", text)

    def test_prompt_contains_style_reference_and_cgi_quality_rules(self):
        text = render_media_package_text(
            self.scenes,
            full_story="Teststory",
            profile=self.profile,
            settings=self.settings,
        )
        self.assertIn("Stilreferenz: style_reference.png", text)
        self.assertIn("VERBINDLICHER VISUELLER QUALITÄTS- UND STILANKER", text)
        self.assertIn("final gerenderte cinematische CGI-/3D", text)
        self.assertIn("flacher 2D-Look", text)

    def test_result_zip_selection_is_in_manifest_and_prompt(self):
        settings = MediaPackageSettings(
            include_images_in_result_zip=False,
            include_audio_in_result_zip=True,
            include_clips_in_result_zip=False,
            include_project_files_in_result_zip=False,
        )
        manifest = build_media_manifest(
            self.scenes,
            target_name="ChatGPT",
            profile=self.profile,
            settings=settings,
        )
        result = manifest["result_package"]
        self.assertFalse(result["include_images"])
        self.assertTrue(result["include_audio"])
        text = render_media_package_text(
            self.scenes,
            full_story="Teststory",
            profile=self.profile,
            settings=settings,
        )
        self.assertIn("Szenenbilder im Ergebnis-ZIP: NEIN", text)
        self.assertIn("Szenenaudios und final_mix.wav im Ergebnis-ZIP: JA", text)
        self.assertNotIn("images/scene_01.png …", text.split("ERWARTETE PAKETSTRUKTUR", 1)[1].split("ZIELSYSTEM-HINWEISE", 1)[0])



if __name__ == "__main__":
    unittest.main()
