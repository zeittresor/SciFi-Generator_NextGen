from pathlib import Path
import struct
import tempfile
import unittest
import wave

import numpy as np

from audio_mixer import mix_narration_with_background, read_pcm_wav


class AudioMixerTests(unittest.TestCase):
    @staticmethod
    def _write_tone(path: Path, *, rate: int, seconds: float, channels: int, amplitude: float) -> None:
        frames = max(1, round(rate * seconds))
        time = np.arange(frames, dtype=np.float32) / rate
        mono = np.sin(2.0 * np.pi * 220.0 * time) * amplitude
        data = mono[:, None]
        if channels == 2:
            data = np.repeat(data, 2, axis=1)
        pcm = np.rint(np.clip(data, -1.0, 1.0) * 32767.0).astype("<i2")
        with wave.open(str(path), "wb") as target:
            target.setnchannels(channels)
            target.setsampwidth(2)
            target.setframerate(rate)
            target.writeframes(pcm.tobytes())

    def test_background_is_resampled_looped_and_mixed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            narration = root / "narration.wav"
            background = root / "background.wav"
            output = root / "mixed.wav"
            self._write_tone(narration, rate=24000, seconds=0.25, channels=1, amplitude=0.4)
            self._write_tone(background, rate=44100, seconds=0.05, channels=2, amplitude=0.1)
            mix_narration_with_background(
                narration,
                output,
                background_path=background,
                background_volume=0.5,
            )
            samples, rate = read_pcm_wav(output)
            self.assertEqual(24000, rate)
            self.assertEqual(2, samples.shape[1])
            self.assertGreaterEqual(samples.shape[0], 5900)
            self.assertLessEqual(float(np.max(np.abs(samples))), 1.0)

    def test_narration_only_export_is_valid_pcm(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            narration = root / "narration.wav"
            output = root / "output.wav"
            self._write_tone(narration, rate=16000, seconds=0.1, channels=1, amplitude=0.3)
            mix_narration_with_background(narration, output)
            samples, rate = read_pcm_wav(output)
            self.assertEqual(16000, rate)
            self.assertEqual(1, samples.shape[1])
            self.assertTrue(output.is_file())

    def test_wave_format_extensible_pcm_is_supported(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "extensible.wav"
            samples = np.array([0, 1000, -1000, 2000], dtype="<i2").tobytes()
            subformat = struct.pack(
                "<IHH8s",
                1,
                0,
                0x0010,
                bytes.fromhex("800000aa00389b71"),
            )
            fmt = struct.pack(
                "<HHIIHHH",
                0xFFFE,
                1,
                16000,
                32000,
                2,
                16,
                22,
            ) + struct.pack("<HI", 16, 4) + subformat
            body = b"fmt " + struct.pack("<I", len(fmt)) + fmt
            body += b"data" + struct.pack("<I", len(samples)) + samples
            path.write_bytes(b"RIFF" + struct.pack("<I", len(body) + 4) + b"WAVE" + body)
            decoded, rate = read_pcm_wav(path)
            self.assertEqual(16000, rate)
            self.assertEqual((4, 1), decoded.shape)
            self.assertAlmostEqual(1000 / 32768.0, float(decoded[1, 0]), places=5)


if __name__ == "__main__":
    unittest.main()
