from __future__ import annotations

from pathlib import Path
import unittest

from story_engine import APP_VERSION

ROOT = Path(__file__).resolve().parents[1]


class V6022QSoundEffectCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app_source = (ROOT / "app.py").read_text(encoding="utf-8")
        cls.verify_source = (ROOT / "tools" / "verify_installation.py").read_text(encoding="utf-8")

    def test_release_version(self):
        self.assertEqual("60.26", APP_VERSION)

    def test_scoped_pyqt6_loop_enum_is_supported(self):
        self.assertIn('getattr(QSoundEffect, "Loop", None)', self.app_source)
        self.assertIn('getattr(loop_enum, "Infinite", None)', self.app_source)
        self.assertIn('return -2', self.app_source)
        self.assertNotIn('setLoopCount(QSoundEffect.Infinite)', self.app_source)
        self.assertIn('setLoopCount(qsoundeffect_infinite_loop_count())', self.app_source)

    def test_installer_verifier_calls_loop_compatibility_helper_on_windows(self):
        self.assertIn('qsoundeffect_infinite_loop_count', self.verify_source)
        self.assertIn('GUI QSoundEffect loop compatibility', self.verify_source)


if __name__ == "__main__":
    unittest.main()
