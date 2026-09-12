from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from runtime_diagnostics import RuntimeDiagnostics
from story_engine import APP_VERSION

ROOT = Path(__file__).resolve().parents[1]


class V6021RuntimeStabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app_source = (ROOT / "app.py").read_text(encoding="utf-8")
        cls.tts_source = (ROOT / "tts_services.py").read_text(encoding="utf-8")

    def test_release_version(self):
        self.assertEqual("60.26", APP_VERSION)

    def test_background_uses_dedicated_full_loop_sound_effect(self):
        self.assertIn("QSoundEffect", self.app_source)
        self.assertIn("self.background_effect.setLoopCount(qsoundeffect_infinite_loop_count())", self.app_source)
        self.assertIn("QSoundEffect.Loop.Infinite", self.app_source)
        self.assertNotIn("self.background_player = QMediaPlayer", self.app_source)

    def test_runtime_error_log_option_is_present_and_persisted(self):
        self.assertIn("Erweitertes Laufzeit-Fehlerprotokoll schreiben", self.app_source)
        self.assertIn('settings.get("runtime_error_log", False)', self.app_source)
        self.assertIn('"runtime_error_log": self.runtime_error_log.isChecked()', self.app_source)
        self.assertIn("RuntimeDiagnostics", self.app_source)

    def test_piper_cancel_detaches_before_kill(self):
        start = self.tts_source.index("class PiperTtsService")
        block = self.tts_source[start:]
        cancel = block[block.index("    def cancel(self) -> None:"):block.index("    def release_output", block.index("    def cancel(self) -> None:"))]
        self.assertLess(cancel.index("self._process = None"), cancel.index("process.kill()"))
        self.assertIn("process.finished.disconnect", cancel)
        self.assertIn("process.errorOccurred.disconnect", cancel)

    def test_runtime_diagnostics_records_breadcrumb_and_exception(self):
        with tempfile.TemporaryDirectory() as temporary:
            logger = RuntimeDiagnostics(Path(temporary), "TestApp", "1.0")
            logger.breadcrumb("before_enable", value=42)
            path = logger.enable()
            self.assertIsNotNone(path)
            logger.breadcrumb("voice_changed", backend="piper", voice="Ramona")
            try:
                raise RuntimeError("synthetic failure")
            except RuntimeError as exc:
                logger.log_exception("unit_test", exc)
            logger.close()
            text = Path(path).read_text(encoding="utf-8")
            self.assertIn("before_enable", text)
            self.assertIn("voice_changed", text)
            self.assertIn("synthetic failure", text)
            self.assertIn("Recent breadcrumbs", text)


if __name__ == "__main__":
    unittest.main()
