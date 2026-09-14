from __future__ import annotations

import math
import unittest
from pathlib import Path

from v6028_tts_flow import (
    PIPER_MODE_CONTINUOUS,
    PIPER_MODE_SECTIONS,
    ffmpeg_pitch_filter,
    pitch_factor,
    prepare_piper_text,
)

ROOT = Path(__file__).resolve().parents[1]


class V6028PiperFlowTests(unittest.TestCase):
    def test_section_mode_preserves_line_boundaries(self) -> None:
        text = "Sprungantrieb aktiviert.\n\nZielsystem erkannt.\nLandung eingeleitet."
        self.assertEqual(prepare_piper_text(text, PIPER_MODE_SECTIONS), text)

    def test_continuous_mode_joins_story_blocks(self) -> None:
        text = "Sprungantrieb aktiviert.\r\n\r\n  Zielsystem   erkannt.  \nLandung eingeleitet."
        self.assertEqual(
            prepare_piper_text(text, PIPER_MODE_CONTINUOUS),
            "Sprungantrieb aktiviert. Zielsystem erkannt. Landung eingeleitet.",
        )

    def test_pitch_factor_uses_semitones(self) -> None:
        self.assertAlmostEqual(pitch_factor(0), 1.0, places=8)
        self.assertAlmostEqual(pitch_factor(6), math.sqrt(2.0), places=8)
        # Public control range is clamped to +/-6 semitones.
        self.assertAlmostEqual(pitch_factor(12), math.sqrt(2.0), places=8)

    def test_pitch_filter_compensates_duration(self) -> None:
        result = ffmpeg_pitch_filter(22050, 3)
        self.assertIn("asetrate=22050*", result)
        self.assertIn("aresample=22050", result)
        self.assertIn("atempo=", result)

    def test_v6028_files_compile(self) -> None:
        for relative in (
            "v6028_tts_flow.py",
            "launcher.py",
            "tools/verify_installation.py",
        ):
            path = ROOT / relative
            compile(path.read_text(encoding="utf-8"), str(path), "exec")

    def test_version_and_launcher_activation(self) -> None:
        self.assertEqual((ROOT / "version.txt").read_text(encoding="utf-8").strip(), "60.28")
        launcher = (ROOT / "launcher.py").read_text(encoding="utf-8")
        self.assertIn("install_v6028_tts_flow(app)", launcher)


if __name__ == "__main__":
    unittest.main()
