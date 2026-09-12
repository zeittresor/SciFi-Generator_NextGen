from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import shutil
import tarfile
import tempfile
import unittest
import zipfile

from tts_package_manager import TtsPackageError, TtsPackageManager

ROOT = Path(__file__).resolve().parents[1]


def md5_bytes(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


class NoNetworkManager(TtsPackageManager):
    @staticmethod
    def _download(*args, **kwargs):
        raise AssertionError("network download must not be used in this test")


class V6018TtsPackageTests(unittest.TestCase):
    def test_catalog_contains_curated_german_piper_packages(self):
        payload = json.loads((ROOT / "tts_package_catalog.json").read_text(encoding="utf-8"))
        self.assertEqual(1, payload["schema_version"])
        packages = payload["packages"]
        ids = {item["id"] for item in packages}
        self.assertEqual(len(ids), len(packages))
        self.assertGreaterEqual(len(packages), 10)
        self.assertTrue(all(item["locale"] == "de_DE" for item in packages))
        for required in (
            "piper-de-eva-k-x-low",
            "piper-de-karlsson-low",
            "piper-de-kerstin-low",
            "piper-de-mls-medium",
            "piper-de-pavoque-low",
            "piper-de-ramona-low",
            "piper-de-thorsten-low",
            "piper-de-thorsten-medium",
            "piper-de-thorsten-high",
            "piper-de-thorsten-emotional-medium",
        ):
            self.assertIn(required, ids)
        for item in packages:
            self.assertRegex(item["model_md5"], r"^[0-9a-f]{32}$")
            self.assertRegex(item["config_md5"], r"^[0-9a-f]{32}$")
            self.assertGreater(item["model_bytes"], 1_000_000)
            self.assertTrue(item["model_url"].startswith("https://huggingface.co/"))

    def test_complete_package_install_reuses_local_runtime_and_model_without_network(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            app = base / "SciFi-Generator"
            app.mkdir()
            reusable = base / "already_downloaded" / "piper"
            reusable.mkdir(parents=True)
            executable = reusable / ("piper.exe" if TtsPackageManager.platform_key().startswith("windows-") else "piper")
            executable.write_bytes(b"fake-piper-runtime")
            (reusable / "espeak-ng-data").mkdir()
            (reusable / "espeak-ng-data" / "de_dict").write_bytes(b"dictionary")

            model_bytes = b"fake-model-data" * 23
            config_payload = {
                "language": {"code": "de_DE"},
                "speaker_id_map": {"neutral": 0, "whisper": 1},
            }
            config_bytes = json.dumps(config_payload).encode("utf-8")
            model_name = "de_DE-test-medium.onnx"
            config_name = model_name + ".json"
            (base / model_name).write_bytes(model_bytes)
            (base / config_name).write_bytes(config_bytes)

            platform_key = TtsPackageManager.platform_key()
            catalog = {
                "schema_version": 1,
                "engines": {
                    "fake-piper": {
                        "name": "Fake Piper",
                        "project": "Piper",
                        "project_url": "https://example.invalid/piper",
                        "license": "MIT",
                        "platforms": {
                            platform_key: {
                                "url": "https://example.invalid/piper.zip",
                                "archive": "piper.zip",
                                "executable": executable.name,
                            }
                        },
                    }
                },
                "packages": [
                    {
                        "id": "test-de",
                        "display_name": "Test Deutsch",
                        "engine": "fake-piper",
                        "language": "Deutsch (de_DE)",
                        "locale": "de_DE",
                        "quality": "medium",
                        "gender_hint": "neutral",
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
                    }
                ],
            }
            catalog_path = app / "tts_package_catalog.json"
            catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
            manager = NoNetworkManager(app, catalog_path)
            messages: list[str] = []
            state = manager.install("test-de", callback=lambda _p, m: messages.append(m))
            self.assertTrue(manager.is_installed("test-de"))
            self.assertTrue(any("wiederverwend" in msg.lower() or "gefunden" in msg.lower() for msg in messages))
            self.assertFalse(Path(state["engine_path"]).is_absolute(), state["engine_path"])
            self.assertFalse(Path(state["model_path"]).is_absolute(), state["model_path"])

            voices = manager.installed_voices()
            self.assertEqual(2, len(voices))
            self.assertEqual({"neutral", "whisper"}, {voice["speaker_name"] for voice in voices})
            self.assertTrue(all(Path(voice["engine_path"]).is_file() for voice in voices))

            # Moving the whole portable application must not invalidate package.json paths.
            moved = base / "Moved-SciFi-Generator"
            shutil.copytree(app, moved)
            moved_manager = NoNetworkManager(moved, moved / "tts_package_catalog.json")
            self.assertTrue(moved_manager.is_installed("test-de"))
            self.assertEqual(2, len(moved_manager.installed_voices()))

    def test_archive_extraction_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination = root / "out"
            destination.mkdir()
            archive = root / "evil.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("../escape.txt", "no")
            with self.assertRaises(TtsPackageError):
                TtsPackageManager._safe_extract_zip(archive, destination)
            self.assertFalse((root / "escape.txt").exists())

            tar_path = root / "evil.tar.gz"
            with tarfile.open(tar_path, "w:gz") as tf:
                info = tarfile.TarInfo("../escape2.txt")
                payload = b"no"
                info.size = len(payload)
                tf.addfile(info, io.BytesIO(payload))
            with self.assertRaises(TtsPackageError):
                TtsPackageManager._safe_extract_tar(tar_path, destination)
            self.assertFalse((root / "escape2.txt").exists())

    def test_gui_has_language_manager_and_escaped_ampersands(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn('addTab(manager_scroll, "Sprachmanager")', source)
        self.assertIn('addTab(audio_scroll, "Sprache && Audio")', source)
        self.assertIn('addTab(details_page, "Story && Trace")', source)
        self.assertIn('QPushButton("Story && Trace anzeigen")', source)
        self.assertIn('BACKEND_LABELS', source)
        self.assertIn('"piper": "Piper (lokales Komplettpaket)"', source)
        self.assertIn("PiperTtsService", source)

    def test_piper_audio_export_is_cross_platform_in_source(self):
        source = (ROOT / "audio_export.py").read_text(encoding="utf-8")
        self.assertIn('request.backend in {"winrt", "sapi"} and os.name != "nt"', source)
        self.assertIn('elif request.backend == "piper":', source)
        self.assertIn('input_text=input_path.read_text', source)
        self.assertIn('narration_volume=', source)


if __name__ == "__main__":
    unittest.main()
