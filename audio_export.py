from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import threading

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from audio_mixer import AudioMixError, mix_narration_with_background


class AudioExportError(RuntimeError):
    pass


class AudioExportCancelled(RuntimeError):
    pass


@dataclass(frozen=True)
class AudioExportRequest:
    text: str
    backend: str
    voice_id: str
    rate: int
    voice_volume: int
    background_path: Path | None
    background_volume: int
    output_path: Path
    tools_dir: Path
    temp_dir: Path
    ffmpeg_path: Path | None = None
    piper_engine_path: Path | None = None
    piper_model_path: Path | None = None
    piper_config_path: Path | None = None
    piper_speaker_id: int | None = None
    piper_noise_scale: float | None = 0.45
    piper_noise_w: float | None = 0.35


def find_ffmpeg(tools_dir: Path) -> Path | None:
    bundled = Path(tools_dir) / "ffmpeg.exe"
    if bundled.is_file():
        return bundled
    located = shutil.which("ffmpeg")
    return Path(located) if located else None


class AudioExportWorker(QObject):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    canceled = pyqtSignal()

    def __init__(self, request: AudioExportRequest):
        super().__init__()
        self.request = request
        self._cancel_event = threading.Event()
        self._process_lock = threading.Lock()
        self._process: subprocess.Popen | None = None

    def cancel(self) -> None:
        self._cancel_event.set()
        with self._process_lock:
            process = self._process
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass

    def _check_canceled(self) -> None:
        if self._cancel_event.is_set():
            raise AudioExportCancelled()

    def _run_process(self, args: list[str], phase: str, *, input_text: str | None = None) -> None:
        self._check_canceled()
        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            process = subprocess.Popen(
                args,
                stdin=subprocess.PIPE if input_text is not None else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=creationflags,
            )
        except OSError as exc:
            raise AudioExportError(f"{phase} konnte nicht gestartet werden: {exc}") from exc
        with self._process_lock:
            self._process = process
        try:
            stdout, stderr = process.communicate(input=input_text)
        finally:
            with self._process_lock:
                self._process = None
        self._check_canceled()
        if process.returncode != 0:
            details = (stderr or stdout or f"Exit code {process.returncode}").strip()
            raise AudioExportError(f"{phase} ist fehlgeschlagen: {details}")

    def _synthesize(self, input_path: Path, narration_path: Path) -> None:
        request = self.request
        if request.backend in {"winrt", "sapi"} and os.name != "nt":
            raise AudioExportError("Der Audioexport mit Windows-TTS ist nur unter Windows verfügbar.")
        if request.backend == "winrt":
            script = request.tools_dir / "synthesize_winrt.ps1"
            speaking_rate = 1.0 + (max(-10, min(10, request.rate)) * 0.05)
            args = [
                "powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive",
                "-ExecutionPolicy", "Bypass", "-File", str(script),
                "-VoiceId", request.voice_id,
                "-InputFile", str(input_path),
                "-OutputFile", str(narration_path),
                "-Rate", f"{speaking_rate:.2f}",
                "-Volume", f"{max(0, min(100, request.voice_volume)) / 100.0:.2f}",
            ]
        elif request.backend == "sapi":
            script = request.tools_dir / "synthesize_sapi.ps1"
            args = [
                "powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive",
                "-ExecutionPolicy", "Bypass", "-File", str(script),
                "-VoiceId", request.voice_id,
                "-InputFile", str(input_path),
                "-OutputFile", str(narration_path),
                "-Rate", str(max(-10, min(10, request.rate))),
                "-Volume", str(max(0, min(100, request.voice_volume))),
            ]
        elif request.backend == "piper":
            engine = Path(request.piper_engine_path or "")
            model = Path(request.piper_model_path or "")
            config = Path(request.piper_config_path or "")
            if not engine.is_file():
                raise AudioExportError(f"Piper-Laufzeit fehlt: {engine}")
            if not model.is_file() or not config.is_file():
                raise AudioExportError("Das ausgewählte Piper-Komplettpaket ist unvollständig.")
            length_scale = max(0.55, min(1.65, 1.0 - (max(-10, min(10, request.rate)) * 0.045)))
            args = [
                str(engine), "--model", str(model), "--config", str(config),
                "--output_file", str(narration_path), "--length_scale", f"{length_scale:.3f}",
            ]
            if request.piper_speaker_id is not None:
                args.extend(["--speaker", str(int(request.piper_speaker_id))])
            if request.piper_noise_scale is not None:
                args.extend(["--noise_scale", f"{float(request.piper_noise_scale):.3f}"])
            if request.piper_noise_w is not None:
                args.extend(["--noise_w", f"{float(request.piper_noise_w):.3f}"])
            self._run_process(args, "Piper-TTS-Synthese", input_text=input_path.read_text(encoding="utf-8") + "\n")
            script = None
        else:
            raise AudioExportError(
                "Die ausgewählte Qt-Stimme kann nicht direkt exportiert werden. "
                "Wählen Sie eine Windows-OneCore/WinRT-, SAPI- oder installierte Piper-Stimme aus."
            )
        if request.backend != "piper":
            if not script.is_file():
                raise AudioExportError(f"Das benötigte TTS-Exportskript fehlt: {script}")
            self._run_process(args, "TTS-Synthese")
        if not narration_path.is_file() or narration_path.stat().st_size < 44:
            raise AudioExportError("Die TTS-Synthese hat keine verwendbare WAV-Datei erzeugt.")

    @pyqtSlot()
    def run(self) -> None:
        request = self.request
        request.temp_dir.mkdir(parents=True, exist_ok=True)
        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        work_dir = Path(tempfile.mkdtemp(prefix="scifi_export_", dir=request.temp_dir))
        temporary_output: Path | None = None
        try:
            self.progress.emit(5, "Erzähltext wird vorbereitet …")
            self._check_canceled()
            input_path = work_dir / "narration.txt"
            narration_path = work_dir / "narration.wav"
            mixed_path = work_dir / "mixed.wav"
            input_path.write_text(request.text, encoding="utf-8")

            self.progress.emit(15, "Ausgewählte Stimme wird synthetisiert …")
            self._synthesize(input_path, narration_path)

            self.progress.emit(55, "Stimme und Brückenatmosphäre werden gemischt …")
            self._check_canceled()
            try:
                mix_narration_with_background(
                    narration_path,
                    mixed_path,
                    background_path=request.background_path,
                    background_volume=max(0, min(100, request.background_volume)) / 100.0,
                    narration_volume=(max(0, min(100, request.voice_volume)) / 100.0 if request.backend == "piper" else 1.0),
                    cancel_check=self._check_canceled,
                    progress_callback=lambda fraction: self.progress.emit(
                        55 + round(max(0.0, min(1.0, fraction)) * 27),
                        "Stimme und Brückenatmosphäre werden gemischt …",
                    ),
                )
            except AudioMixError as exc:
                raise AudioExportError(str(exc)) from exc

            self._check_canceled()
            suffix = request.output_path.suffix.lower()
            if suffix == ".mp3":
                if request.ffmpeg_path is None or not request.ffmpeg_path.is_file():
                    raise AudioExportError(
                        "Für den MP3-Export wird ffmpeg.exe im Ordner tools oder FFmpeg in PATH benötigt."
                    )
                self.progress.emit(82, "MP3 wird mit FFmpeg codiert …")
                temporary_output = request.output_path.with_name(
                    request.output_path.stem + ".partial.mp3"
                )
                # Deliberately use long-established FFmpeg options only. Some Windows
                # systems still have older FFmpeg builds in PATH which reject newer
                # cosmetic/global switches. The legacy codec/bitrate syntax works on
                # both old and current FFmpeg releases and is sufficient here.
                self._run_process([
                    str(request.ffmpeg_path), "-y",
                    "-i", str(mixed_path), "-vn", "-acodec", "libmp3lame", "-ab", "192k",
                    str(temporary_output),
                ], "MP3-Codierung")
            else:
                self.progress.emit(88, "WAV-Datei wird geschrieben …")
                temporary_output = request.output_path.with_name(
                    request.output_path.stem + ".partial.wav"
                )
                shutil.copy2(mixed_path, temporary_output)

            self._check_canceled()
            os.replace(temporary_output, request.output_path)
            temporary_output = None
            self.progress.emit(100, "Audioexport abgeschlossen.")
            self.finished.emit(str(request.output_path))
        except AudioExportCancelled:
            try:
                request.output_path.unlink(missing_ok=True)
            except OSError:
                pass
            self.canceled.emit()
        except Exception as exc:
            try:
                request.output_path.unlink(missing_ok=True)
            except OSError:
                pass
            self.error.emit(str(exc))
        finally:
            if temporary_output is not None:
                try:
                    temporary_output.unlink(missing_ok=True)
                except OSError:
                    pass
            shutil.rmtree(work_dir, ignore_errors=True)
