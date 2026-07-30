from pathlib import Path
import json
import tempfile
import unittest
import zipfile

from handoff_package import create_handoff_zip, validate_handoff_archive, validate_total_package_prompt
from media_package_generator import MediaPackageSettings, build_media_manifest, render_media_package_text
from prompt_profile_manager import PromptProfileManager
from storyboard_generator import generate_storyboard
from story_engine import StoryEngine

ROOT = Path(__file__).resolve().parents[1]


class HandoffPackageTests(unittest.TestCase):
    def setUp(self):
        engine = StoryEngine(ROOT / "data" / "vars", ROOT / "sequence_legacy.json")
        result = engine.generate(57)
        self.scenes = generate_storyboard(result, 8)
        manager = PromptProfileManager(ROOT / "prompt_profiles")
        manager.load()
        self.profile = manager.get("ChatGPT")
        self.settings = MediaPackageSettings(background_enabled=True)
        self.prompt = render_media_package_text(
            self.scenes,
            full_story=result.display_story,
            profile=self.profile,
            settings=self.settings,
        )
        self.manifest = build_media_manifest(
            self.scenes,
            target_name="ChatGPT",
            profile=self.profile,
            settings=self.settings,
        )
        self.story = result.display_story

    def test_total_prompt_has_completion_gate_and_background_rules(self):
        self.assertEqual([], validate_total_package_prompt(self.prompt, background_required=True))
        self.assertIn("Eine reine Bild-ZIP ist ausdrücklich unvollständig", self.prompt)
        self.assertIn("assets/background.wav", self.prompt)
        self.assertIn("nicht-stumme Audiospur", self.prompt)

    def test_handoff_zip_embeds_background_and_start_file(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "handoff.zip"
            background = ROOT / "data" / "sounds" / "background.wav"
            create_handoff_zip(
                out,
                prompt_text=self.prompt,
                manifest=self.manifest,
                full_story=self.story,
                app_version="60.12",
                background_path=background,
            )
            with zipfile.ZipFile(out) as archive:
                names = set(archive.namelist())
                self.assertIn("00_START_HERE.txt", names)
                self.assertIn("00_EXECUTE_THIS_TASK.txt", names)
                self.assertIn("README_HANDOFF.txt", names)
                self.assertIn("style_reference.png", names)
                self.assertIn("prompts/scifi_media_package_prompt.txt", names)
                self.assertIn("manifest.json", names)
                self.assertIn("assets/background.wav", names)
                self.assertIn("verification/DELIVERY_CHECKLIST.txt", names)
                self.assertIn("build_story_video.py", names)
                self.assertIn("build_video.bat", names)
                self.assertIn("TASK.json", names)
                self.assertIn("tools/list_sapi_voices.ps1", names)
                self.assertIn("offline_fallback/build_story_video.py", names)
                self.assertIn("offline_fallback/audio_mixer.py", names)
                start = archive.read("00_START_HERE.txt").decode("utf-8-sig")
                self.assertIn("KEINE BITTE UM ARCHIVANALYSE", start)
                self.assertIn("Stoppe danach nicht", start)
                self.assertIn("style_reference.png", start)
                self.assertIn("gewünschten Lieferumfang", start)
            self.assertEqual([], validate_handoff_archive(out, background_required=True, expected_scene_count=8))

    def test_handoff_manifest_preserves_selected_result_zip_contents(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "handoff_video_only.zip"
            settings = MediaPackageSettings(
                include_images_in_result_zip=False,
                include_audio_in_result_zip=False,
                include_clips_in_result_zip=False,
                include_project_files_in_result_zip=False,
            )
            prompt = render_media_package_text(
                self.scenes,
                full_story=self.story,
                profile=self.profile,
                settings=settings,
            )
            manifest = build_media_manifest(
                self.scenes,
                target_name="ChatGPT",
                profile=self.profile,
                settings=settings,
            )
            create_handoff_zip(
                out,
                prompt_text=prompt,
                manifest=manifest,
                full_story=self.story,
                app_version="60.13",
                background_path=ROOT / "data" / "sounds" / "background.wav",
            )
            with zipfile.ZipFile(out) as archive:
                payload = json.loads(archive.read("manifest.json").decode("utf-8-sig"))
                result = payload["result_package"]
                self.assertTrue(result["video_always_included"])
                self.assertFalse(result["include_images"])
                self.assertFalse(result["include_audio"])
                checklist = archive.read("verification/DELIVERY_CHECKLIST.txt").decode("utf-8-sig")
                self.assertIn("Szenenbilder sind nicht enthalten, wie ausgewählt", checklist)
                self.assertIn("Szenenaudios und final_mix.wav sind nicht enthalten, wie ausgewählt", checklist)



if __name__ == "__main__":
    unittest.main()
