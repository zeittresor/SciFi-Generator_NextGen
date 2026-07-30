from __future__ import annotations

from pathlib import Path
from typing import Callable
import struct
import wave

import numpy as np


class AudioMixError(RuntimeError):
    """Raised when a WAV file cannot be decoded or mixed."""


def _decode_pcm(raw: bytes, sample_width: int) -> np.ndarray:
    if sample_width == 1:
        values = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
        return (values - 128.0) / 128.0
    if sample_width == 2:
        return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if sample_width == 3:
        packed = np.frombuffer(raw, dtype=np.uint8)
        if packed.size % 3:
            raise AudioMixError("24-Bit-PCM-Daten besitzen eine ungültige Byte-Länge.")
        packed = packed.reshape(-1, 3)
        values = (
            packed[:, 0].astype(np.int32)
            | (packed[:, 1].astype(np.int32) << 8)
            | (packed[:, 2].astype(np.int32) << 16)
        )
        values = np.where(values & 0x800000, values - 0x1000000, values)
        return values.astype(np.float32) / 8388608.0
    if sample_width == 4:
        return np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    raise AudioMixError(f"Nicht unterstützte PCM-Samplebreite: {sample_width} Byte")


def _read_riff_pcm_fallback(path: Path) -> tuple[bytes, int, int, int]:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise AudioMixError(f"WAV-Datei konnte nicht gelesen werden: {path}: {exc}") from exc
    if len(payload) < 12 or payload[:4] != b"RIFF" or payload[8:12] != b"WAVE":
        raise AudioMixError(f"Ungültiger RIFF/WAVE-Header in {path}")

    fmt: bytes | None = None
    audio_data: bytes | None = None
    offset = 12
    while offset + 8 <= len(payload):
        chunk_id, chunk_size = struct.unpack_from("<4sI", payload, offset)
        offset += 8
        chunk = payload[offset:offset + chunk_size]
        if len(chunk) != chunk_size:
            raise AudioMixError(f"Abgeschnittener WAV-Block in {path}")
        if chunk_id == b"fmt ":
            fmt = chunk
        elif chunk_id == b"data":
            audio_data = chunk
        offset += chunk_size + (chunk_size & 1)

    if fmt is None or audio_data is None or len(fmt) < 16:
        raise AudioMixError(f"WAV-Datei enthält keinen vollständigen fmt-/data-Block: {path}")
    format_tag, channels, sample_rate, _byte_rate, block_align, bits = struct.unpack_from(
        "<HHIIHH", fmt, 0
    )
    if format_tag == 0xFFFE:
        if len(fmt) < 40:
            raise AudioMixError(f"Unvollständiges WAVE_FORMAT_EXTENSIBLE-Format in {path}")
        subformat_tag = struct.unpack_from("<I", fmt, 24)[0]
        format_tag = subformat_tag
    if format_tag != 1:
        raise AudioMixError(f"Nur PCM-WAV wird unterstützt; Formatkennung in {path}: {format_tag}")
    if bits not in (8, 16, 24, 32) or bits % 8:
        raise AudioMixError(f"Nicht unterstützte PCM-Bittiefe in {path}: {bits}")
    sample_width = bits // 8
    if channels < 1 or sample_rate < 1 or block_align != channels * sample_width:
        raise AudioMixError(f"Ungültige WAV-Parameter in {path}")
    return audio_data, channels, sample_width, sample_rate


def read_pcm_wav(path: Path) -> tuple[np.ndarray, int]:
    path = Path(path)
    try:
        with wave.open(str(path), "rb") as source:
            if source.getcomptype() != "NONE":
                raise AudioMixError(
                    f"Komprimierte WAV-Audiodaten werden nicht unterstützt: {source.getcompname()}"
                )
            channels = source.getnchannels()
            sample_width = source.getsampwidth()
            sample_rate = source.getframerate()
            frame_count = source.getnframes()
            raw = source.readframes(frame_count)
    except wave.Error:
        raw, channels, sample_width, sample_rate = _read_riff_pcm_fallback(path)
    except OSError as exc:
        raise AudioMixError(f"WAV-Datei konnte nicht gelesen werden: {path}: {exc}") from exc

    if channels < 1 or sample_rate < 1:
        raise AudioMixError(f"Ungültige WAV-Parameter in {path}")
    samples = _decode_pcm(raw, sample_width)
    if samples.size % channels:
        raise AudioMixError(f"Ungültige PCM-Kanalanordnung in {path}")
    return samples.reshape(-1, channels), sample_rate


def _convert_channels(samples: np.ndarray, channels: int) -> np.ndarray:
    current = samples.shape[1]
    if current == channels:
        return samples
    if channels == 1:
        return samples.mean(axis=1, keepdims=True, dtype=np.float32)
    if current == 1:
        return np.repeat(samples, channels, axis=1)
    if current > channels:
        return samples[:, :channels]
    repeats = int(np.ceil(channels / current))
    return np.tile(samples, (1, repeats))[:, :channels]


def _resample_linear(samples: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    if source_rate == target_rate or samples.shape[0] < 2:
        return samples
    target_frames = max(1, round(samples.shape[0] * target_rate / source_rate))
    positions = np.arange(target_frames, dtype=np.float64) * (source_rate / target_rate)
    positions = np.minimum(positions, samples.shape[0] - 1)
    source_positions = np.arange(samples.shape[0], dtype=np.float64)
    result = np.empty((target_frames, samples.shape[1]), dtype=np.float32)
    for channel in range(samples.shape[1]):
        result[:, channel] = np.interp(
            positions,
            source_positions,
            samples[:, channel],
        ).astype(np.float32)
    return result


def write_pcm16_wav(
    path: Path,
    samples: np.ndarray,
    sample_rate: int,
    *,
    cancel_check: Callable[[], None] | None = None,
    progress_callback: Callable[[float], None] | None = None,
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    clipped = np.clip(samples, -1.0, 1.0)
    try:
        with wave.open(str(path), "wb") as target:
            target.setnchannels(samples.shape[1])
            target.setsampwidth(2)
            target.setframerate(sample_rate)
            block_frames = 262_144
            total_frames = max(1, clipped.shape[0])
            for start in range(0, clipped.shape[0], block_frames):
                if cancel_check is not None:
                    cancel_check()
                block = clipped[start:start + block_frames]
                pcm = np.rint(block * 32767.0).astype("<i2", copy=False)
                target.writeframes(pcm.tobytes())
                if progress_callback is not None:
                    progress_callback(min(1.0, (start + block.shape[0]) / total_frames))
    except (OSError, wave.Error) as exc:
        raise AudioMixError(f"WAV-Datei konnte nicht geschrieben werden: {path}: {exc}") from exc


def mix_narration_with_background(
    narration_path: Path,
    output_path: Path,
    *,
    background_path: Path | None = None,
    background_volume: float = 0.0,
    cancel_check: Callable[[], None] | None = None,
    progress_callback: Callable[[float], None] | None = None,
) -> None:
    narration, sample_rate = read_pcm_wav(narration_path)
    if narration.size == 0:
        raise AudioMixError("Die synthetisierte Sprachausgabe ist leer.")

    if background_path is None or background_volume <= 0.0:
        write_pcm16_wav(
            output_path,
            narration,
            sample_rate,
            cancel_check=cancel_check,
            progress_callback=progress_callback,
        )
        return

    background, background_rate = read_pcm_wav(background_path)
    if background.size == 0:
        raise AudioMixError("Die ausgewählte Hintergrund-WAV-Datei ist leer.")

    output_channels = max(narration.shape[1], background.shape[1])
    narration = _convert_channels(narration, output_channels)
    background = _convert_channels(background, output_channels)
    background = _resample_linear(background, background_rate, sample_rate)
    if background.shape[0] == 0:
        raise AudioMixError("Die Hintergrund-WAV-Datei enthält keine verwendbaren Audioblöcke.")

    mixed = narration.astype(np.float32, copy=True)
    gain = max(0.0, min(1.0, float(background_volume)))
    block_frames = 262_144
    background_frames = background.shape[0]
    total_frames = max(1, mixed.shape[0])
    for start in range(0, mixed.shape[0], block_frames):
        if cancel_check is not None:
            cancel_check()
        end = min(mixed.shape[0], start + block_frames)
        indices = np.arange(start, end, dtype=np.int64) % background_frames
        mixed[start:end] += background[indices] * gain
        if progress_callback is not None:
            progress_callback(0.55 * (end / total_frames))

    def write_progress(fraction: float) -> None:
        if progress_callback is not None:
            progress_callback(0.55 + (0.45 * fraction))

    write_pcm16_wav(
        output_path,
        mixed,
        sample_rate,
        cancel_check=cancel_check,
        progress_callback=write_progress,
    )
