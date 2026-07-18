from pathlib import Path
import unittest

from prompt_profile_manager import PromptProfileManager
from storyboard_generator import generate_storyboard, render_storyboard_text
from media_package_generator import MediaPackageSettings, render_media_package_text
from story_engine import StoryEngine

ROOT = Path(__file__).resolve().parents[1]


class PromptProfileTests(unittest.TestCase):
    def setUp(self):
        self.manager = PromptProfileManager(ROOT / "prompt_profiles")
        self.manager.load()
        engine = StoryEngine(ROOT / "data" / "vars", ROOT / "sequence_legacy.json")
        self.scenes = generate_storyboard(engine.generate(57), 8)

    def test_expected_external_profiles_load(self):
        self.assertEqual([], self.manager.errors)
        self.assertEqual(
            ["ChatGPT", "Grok", "Gemini", "Stable Diffusion", "Andere"],
            self.manager.names(),
        )

    def test_chatgpt_document_contains_executable_series_instruction(self):
        profile = self.manager.get("ChatGPT")
        text = render_storyboard_text(self.scenes, profile=profile)
        self.assertIn("AUSFÜHRBARER BILDSERIEN-AUFTRAG", text)
        self.assertIn("ARBEITSAUFTRAG FÜR CHATGPT-BILDGENERIERUNG", text)
        self.assertIn("genau 8 einzelne Bilder", text)
        self.assertIn("GLOBALE VISUELLE SERIENBIBEL", text)
        self.assertIn("scene_01.png", text)

    def test_stable_diffusion_document_has_positive_and_negative_prompts(self):
        profile = self.manager.get("Stable Diffusion")
        text = render_storyboard_text(self.scenes, profile=profile)
        self.assertIn("STEUERANWEISUNG FÜR STABLE-DIFFUSION-WORKFLOW", text)
        self.assertIn("POSITIVE PROMPT", text)
        self.assertIn("GLOBAL NEGATIVE PROMPT", text)
        self.assertIn("NEGATIVE PROMPT:", text)
        self.assertIn("Jeder POSITIVE PROMPT ist einzeln zu generieren", text)

    def test_other_profile_uses_custom_target_name(self):
        profile = self.manager.get("Andere")
        text = render_storyboard_text(
            self.scenes,
            profile=profile,
            custom_target_name="Lokales Bildmodell X",
        )
        self.assertIn("Ziel-KI: Lokales Bildmodell X", text)



    def test_chatgpt_total_package_contains_audio_video_and_zip_workflow(self):
        profile = self.manager.get("ChatGPT")
        settings = MediaPackageSettings(
            voice_name="Microsoft Katja",
            voice_backend="Windows SAPI",
            transition_seconds=1.2,
        )
        text = render_media_package_text(
            self.scenes,
            full_story="Vollständige Testgeschichte.",
            source="Lokal",
            profile=profile,
            settings=settings,
        )
        self.assertIn("GESAMTPAKET-PRODUKTIONSAUFTRAG", text)
        self.assertIn("scene_01.wav", text)
        self.assertIn("scene_01.mp4", text)
        self.assertIn("scifi_story.mp4", text)
        self.assertIn("scifi_story_package.zip", text)
        self.assertIn("build_story_video.py", text)
        self.assertIn("Microsoft Katja", text)
        self.assertIn("Crossfade", text)

    def test_stable_diffusion_total_package_requests_external_orchestration(self):
        profile = self.manager.get("Stable Diffusion")
        text = render_media_package_text(
            self.scenes,
            full_story="Test",
            source="Lokal",
            profile=profile,
        )
        self.assertIn("STABLE-DIFFUSION-VIDEO-WORKFLOW", text)
        self.assertIn("FFmpeg", text)
        self.assertIn("Workflow-Runner", text)

if __name__ == "__main__":
    unittest.main()
