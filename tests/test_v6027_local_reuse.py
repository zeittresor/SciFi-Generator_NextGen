from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from install_dependencies import default_tree_search_root, discover_local_wheels  # noqa: E402
from index_local_tts_assets import stage_catalog_assets  # noqa: E402


class LocalReuseTests(unittest.TestCase):
    def test_installer_invokes_dependency_and_tts_reuse_helpers(self) -> None:
        source = (ROOT / "install_windows.bat").read_text(encoding="utf-8")
        self.assertIn('"tools\\install_dependencies.py"', source)
        self.assertIn('"tools\\index_local_tts_assets.py"', source)
        self.assertNotIn("pip install --upgrade pip", source)

    def test_default_search_root_uses_bounded_project_family(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "xxx" / "yyy" / "zzz"
            project.mkdir(parents=True)
            with patch.dict("os.environ", {"SCIFI_WHEEL_SEARCH_ROOT": ""}, clear=False):
                self.assertEqual(default_tree_search_root(project), (root / "xxx").resolve())

    def test_wheel_discovery_finds_typical_sibling_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            family = root / "xxx"
            project = family / "yyy" / "zzz"
            project.mkdir(parents=True)
            wheel_dir = family / "old_project" / "wheelhouse"
            wheel_dir.mkdir(parents=True)
            wheel = wheel_dir / "example_pkg-1.0-py3-none-any.whl"
            wheel.write_bytes(b"not-a-real-wheel-needed-for-discovery-test")

            with patch.dict("os.environ", {"SCIFI_WHEEL_SEARCH_ROOT": str(family)}, clear=False):
                search_root, wheels = discover_local_wheels(project)

            self.assertEqual(search_root, family.resolve())
            self.assertIn(wheel.resolve(), wheels)

    def test_tts_scan_stages_only_verified_catalog_model_and_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            family = root / "xxx"
            app = family / "new" / "scifi"
            app.mkdir(parents=True)

            old_models = family / "old_project" / "voice_models"
            old_models.mkdir(parents=True)
            model_bytes = b"verified fake onnx payload for unit test"
            config_bytes = b'{"speaker_id_map": {}}'
            model_name = "de_DE-test-medium.onnx"
            config_name = model_name + ".json"
            model_path = old_models / model_name
            config_path = old_models / config_name
            model_path.write_bytes(model_bytes)
            config_path.write_bytes(config_bytes)

            catalog = {
                "schema_version": 1,
                "engines": {},
                "packages": [
                    {
                        "id": "test-voice",
                        "display_name": "Test Voice",
                        "engine": "unused",
                        "language": "Deutsch",
                        "locale": "de_DE",
                        "quality": "medium",
                        "gender_hint": "",
                        "model": model_name,
                        "config": config_name,
                        "model_url": "https://example.invalid/model",
                        "config_url": "https://example.invalid/config",
                        "model_md5": hashlib.md5(model_bytes).hexdigest(),
                        "config_md5": hashlib.md5(config_bytes).hexdigest(),
                        "model_bytes": len(model_bytes),
                        "source": "test",
                        "source_url": "https://example.invalid",
                        "voice_license": "test",
                    }
                ],
            }
            (app / "tts_package_catalog.json").write_text(
                json.dumps(catalog), encoding="utf-8"
            )

            manifest = stage_catalog_assets(app, search_root=family, extra_roots=[])
            cache = app / "tts_packages" / "_cache"

            self.assertEqual((cache / model_name).read_bytes(), model_bytes)
            self.assertEqual((cache / config_name).read_bytes(), config_bytes)
            self.assertEqual(manifest["files"][model_name]["kind"], "model")
            self.assertEqual(manifest["files"][config_name]["kind"], "config")
            self.assertIn(manifest["files"][model_name]["method"], {"hardlink", "copy", "existing"})

    def test_tts_scan_rejects_wrong_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            family = root / "xxx"
            app = family / "new" / "scifi"
            app.mkdir(parents=True)
            model_dir = family / "old" / "models"
            model_dir.mkdir(parents=True)
            model_name = "de_DE-test-low.onnx"
            (model_dir / model_name).write_bytes(b"wrong payload")

            catalog = {
                "schema_version": 1,
                "engines": {},
                "packages": [
                    {
                        "id": "bad-test",
                        "display_name": "Bad Test",
                        "engine": "unused",
                        "language": "Deutsch",
                        "locale": "de_DE",
                        "quality": "low",
                        "gender_hint": "",
                        "model": model_name,
                        "config": "missing.json",
                        "model_url": "https://example.invalid/model",
                        "config_url": "https://example.invalid/config",
                        "model_md5": hashlib.md5(b"expected payload").hexdigest(),
                        "config_md5": "",
                        "model_bytes": len(b"expected payload"),
                        "source": "test",
                        "source_url": "https://example.invalid",
                        "voice_license": "test",
                    }
                ],
            }
            (app / "tts_package_catalog.json").write_text(json.dumps(catalog), encoding="utf-8")

            manifest = stage_catalog_assets(app, search_root=family, extra_roots=[])
            self.assertNotIn(model_name, manifest["files"])
            self.assertFalse((app / "tts_packages" / "_cache" / model_name).exists())


if __name__ == "__main__":
    unittest.main()
