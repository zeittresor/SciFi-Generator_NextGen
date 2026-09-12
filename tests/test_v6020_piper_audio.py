from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from tts_package_manager import TtsPackageManager

ROOT = Path(__file__).resolve().parents[1]


def md5_bytes(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


class NoNetworkManager(TtsPackageManager):
    @staticmethod
    def _download(*args, **kwargs):
        raise AssertionError("network download must not be used in this test")


class V6020PiperAudioTests(unittest.TestCase):
    def test_thorsten_emotional_catalog_uses_dedicated_style_selector(self):
        payload = json.loads((ROOT / "tts_package_catalog.json").read_text(encoding="utf-8"))
        package = next(item for item in payload["packages"] if item["id"] == "piper-de-thorsten-emotional-medium")
        self.assertTrue(package["speaker_selector"])
        self.assertEqual("Emotion / Stil", package["speaker_selector_label"])
        self.assertEqual("neutral", package["default_speaker"])

    def test_style_selector_package_is_one_voice_with_options(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            app = base / "SciFi-Generator"
            app.mkdir()
            reusable = base / "runtime" / "piper"
            reusable.mkdir(parents=True)
            executable = reusable / ("piper.exe" if TtsPackageManager.platform_key().startswith("windows-") else "piper")
            executable.write_bytes(b"fake-piper")
            (reusable / "espeak-ng-data").mkdir()
            (reusable / "espeak-ng-data" / "de_dict").write_bytes(b"dictionary")

            model_bytes = b"fake-emotional-model" * 23
            config = {
                "language": {"code": "de_DE"},
                "speaker_id_map": {
                    "amused": 0,
                    "angry": 1,
                    "disgusted": 2,
                    "drunk": 3,
                    "neutral": 4,
                    "sleepy": 5,
                    "surprised": 6,
                    "whisper": 7,
                },
            }
            config_bytes = json.dumps(config).encode("utf-8")
            model_name = "de_DE-fake-emotional.onnx"
            config_name = model_name + ".json"
            (base / model_name).write_bytes(model_bytes)
            (base / config_name).write_bytes(config_bytes)

            catalog = {
                "schema_version": 1,
                "engines": {
                    "fake-piper": {
                        "name": "Fake Piper",
                        "project": "Piper",
                        "project_url": "https://example.invalid/piper",
                        "license": "MIT",
                        "platforms": {
                            TtsPackageManager.platform_key(): {
                                "url": "https://example.invalid/piper.zip",
                                "archive": "piper.zip",
                                "executable": executable.name,
                            }
                        },
                    }
                },
                "packages": [{
                    "id": "fake-emotional",
                    "display_name": "Fake Emotional",
                    "engine": "fake-piper",
                    "language": "Deutsch (de_DE)",
                    "locale": "de_DE",
                    "quality": "medium / 8 Stile",
                    "gender_hint": "männlich",
                    "model": model_name,
                    "config": config_name,
                    "model_url": "https://example.invalid/model",
                    "config_url": "https://example.invalid/config",
                    "model_md5": md5_bytes(model_bytes),
                    "config_md5": md5_bytes(config_bytes),
                    "model_bytes": len(model_bytes),
                    "source": "test",
                    "source_url": "https://example.invalid/source",
                    "voice_license": "test",
                    "speaker_selector": True,
                    "speaker_selector_label": "Emotion / Stil",
                    "default_speaker": "neutral",
                }],
            }
            catalog_path = app / "tts_package_catalog.json"
            catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
            manager = NoNetworkManager(app, catalog_path)
            manager.install("fake-emotional")
            voices = manager.installed_voices()
            self.assertEqual(1, len(voices))
            voice = voices[0]
            self.assertTrue(voice["speaker_selector"])
            self.assertEqual(4, voice["speaker_id"])
            self.assertEqual("neutral", voice["speaker_name"])
            self.assertEqual(8, len(voice["speaker_options"]))
            self.assertEqual({0,1,2,3,4,5,6,7}, {item["id"] for item in voice["speaker_options"]})

    def test_gui_has_dynamic_piper_style_and_prosody_controls(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn('self.piper_style_combo = QComboBox()', source)
        self.assertIn('self.piper_prosody_combo = QComboBox()', source)
        self.assertIn('"Stabil / gleichmäßig (empfohlen)"', source)
        self.assertIn('PIPER_STYLE_LABELS', source)
        self.assertIn('self._voice_with_piper_options(entry)', source)

    def test_piper_synthesis_supports_stability_parameters(self):
        service_source = (ROOT / "tts_services.py").read_text(encoding="utf-8")
        export_source = (ROOT / "audio_export.py").read_text(encoding="utf-8")
        self.assertIn('"--noise_scale"', service_source)
        self.assertIn('"--noise_w"', service_source)
        self.assertIn('piper_noise_scale', export_source)
        self.assertIn('piper_noise_w', export_source)

    def test_mp3_export_avoids_hide_banner_and_uses_legacy_compatible_options(self):
        source = (ROOT / "audio_export.py").read_text(encoding="utf-8")
        # Direct story MP3 export must not require modern cosmetic FFmpeg options.
        mp3_block = source[source.index('if suffix == ".mp3":'):source.index('else:', source.index('if suffix == ".mp3":'))]
        self.assertNotIn('hide_banner', mp3_block)
        self.assertIn('"-acodec", "libmp3lame"', source)
        self.assertIn('"-ab", "192k"', source)


if __name__ == "__main__":
    unittest.main()
