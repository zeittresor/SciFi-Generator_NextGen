from __future__ import annotations

from pathlib import Path
import json
import os
import tempfile

from PyQt6.QtCore import QObject, QProcess, QThread, QTimer, pyqtSignal, pyqtSlot


class WinRtTtsService(QObject):
    voices_ready = pyqtSignal(object)
    synthesis_ready = pyqtSignal(str)
    error = pyqtSignal(str)
    state_changed = pyqtSignal(str)

    def __init__(self, tools_dir: Path, temp_dir: Path, parent: QObject | None = None):
        super().__init__(parent)
        self.tools_dir = Path(tools_dir)
        self.temp_dir = Path(temp_dir)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self._list_process: QProcess | None = None
        self._synth_process: QProcess | None = None
        self._input_path: Path | None = None
        self._output_path: Path | None = None

    @staticmethod
    def available() -> bool:
        return os.name == "nt"

    def _stop_voice_list_process(self) -> None:
        """Stop a pending PowerShell voice enumeration without leaving QProcess alive."""
        process = self._list_process
        self._list_process = None
        if process is None:
            return
        try:
            process.finished.disconnect(self._voice_list_finished)
        except (TypeError, RuntimeError):
            pass
        try:
            if process.state() != QProcess.ProcessState.NotRunning:
                process.kill()
                process.waitForFinished(1000)
        finally:
            process.deleteLater()

    def refresh_voices(self) -> None:
        if not self.available():
            self.voices_ready.emit([])
            return
        script = self.tools_dir / "list_winrt_voices.ps1"
        if not script.is_file():
            self.error.emit(f"WinRT-Stimmen-Skript fehlt: {script}")
            self.voices_ready.emit([])
            return
        self._stop_voice_list_process()
        process = QProcess(self)
        self._list_process = process
        process.setProgram("powershell.exe")
        process.setArguments(["-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script)])
        process.finished.connect(self._voice_list_finished)
        process.start()

    @pyqtSlot(int, QProcess.ExitStatus)
    def _voice_list_finished(self, exit_code: int, _status: QProcess.ExitStatus) -> None:
        process = self._list_process
        self._list_process = None
        if process is None:
            return
        stdout = bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace").strip()
        stderr = bytes(process.readAllStandardError()).decode("utf-8", errors="replace").strip()
        process.deleteLater()
        if exit_code != 0:
            self.error.emit("WinRT-Stimmen konnten nicht gelesen werden: " + (stderr or f"Exit-Code {exit_code}"))
            self.voices_ready.emit([])
            return
        try:
            payload = json.loads(stdout or "[]")
            if isinstance(payload, dict):
                payload = [payload]
            voices = []
            for item in payload:
                voices.append({
                    "backend": "winrt",
                    "id": str(item.get("id", "")),
                    "name": str(item.get("name", "Windows voice")),
                    "locale": str(item.get("language", "")),
                    "description": str(item.get("description", "")),
                    "gender": str(item.get("gender", "")),
                })
            self.voices_ready.emit(voices)
        except (json.JSONDecodeError, TypeError, AttributeError) as exc:
            self.error.emit(f"WinRT-Stimmenausgabe konnte nicht ausgewertet werden: {exc}")
            self.voices_ready.emit([])

    def synthesize(self, text: str, voice_id: str, rate: int, volume: int) -> None:
        if not self.available():
            self.error.emit("Windows WinRT-TTS ist auf diesem System nicht verfügbar.")
            return
        self.cancel()
        script = self.tools_dir / "synthesize_winrt.ps1"
        if not script.is_file():
            self.error.emit(f"WinRT-Synthese-Skript fehlt: {script}")
            return
        fd, input_name = tempfile.mkstemp(prefix="scifi_tts_", suffix=".txt", dir=self.temp_dir)
        os.close(fd)
        self._input_path = Path(input_name)
        self._input_path.write_text(text, encoding="utf-8")
        fd, output_name = tempfile.mkstemp(prefix="scifi_tts_", suffix=".wav", dir=self.temp_dir)
        os.close(fd)
        self._output_path = Path(output_name)
        self._output_path.unlink(missing_ok=True)

        speaking_rate = 1.0 + (max(-10, min(10, rate)) * 0.05)
        process = QProcess(self)
        self._synth_process = process
        process.setProgram("powershell.exe")
        process.setArguments([
            "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-File", str(script),
            "-VoiceId", voice_id,
            "-InputFile", str(self._input_path),
            "-OutputFile", str(self._output_path),
            "-Rate", f"{speaking_rate:.2f}",
            "-Volume", f"{max(0, min(100, volume)) / 100.0:.2f}",
        ])
        process.finished.connect(self._synthesis_finished)
        self.state_changed.emit("preparing")
        process.start()

    @pyqtSlot(int, QProcess.ExitStatus)
    def _synthesis_finished(self, exit_code: int, _status: QProcess.ExitStatus) -> None:
        process = self._synth_process
        self._synth_process = None
        if process is None:
            return
        stderr = bytes(process.readAllStandardError()).decode("utf-8", errors="replace").strip()
        process.deleteLater()
        self._cleanup_input()
        if exit_code != 0 or self._output_path is None or not self._output_path.is_file():
            self._cleanup_output()
            self.error.emit("WinRT-Sprachausgabe konnte nicht erzeugt werden: " + (stderr or f"Exit-Code {exit_code}"))
            self.state_changed.emit("error")
            return
        self.synthesis_ready.emit(str(self._output_path))

    def cancel(self) -> None:
        # Voice enumeration is asynchronous too. Closing the application or a GUI
        # smoke test while it is still running used to leave powershell.exe attached
        # to a QProcess that Qt then destroyed, producing a shutdown warning.
        self._stop_voice_list_process()

        process = self._synth_process
        # Detach the active process before terminating it. QProcess.finished may be
        # delivered while waitForFinished() is running; leaving self._synth_process
        # attached used to let the completion slot and cancel() clean up the same
        # object concurrently.
        self._synth_process = None
        if process is not None:
            try:
                process.finished.disconnect(self._synthesis_finished)
            except (TypeError, RuntimeError):
                pass
            try:
                if process.state() != QProcess.ProcessState.NotRunning:
                    process.kill()
                    process.waitForFinished(1000)
            finally:
                process.deleteLater()
        self._cleanup_input()
        self._cleanup_output()

    def release_output(self) -> None:
        self._cleanup_output()

    def _cleanup_input(self) -> None:
        if self._input_path is not None:
            try:
                self._input_path.unlink(missing_ok=True)
            except OSError:
                pass
            self._input_path = None

    def _cleanup_output(self) -> None:
        if self._output_path is not None:
            try:
                self._output_path.unlink(missing_ok=True)
            except OSError:
                pass
            self._output_path = None


class _SapiWorker(QObject):
    voices_ready = pyqtSignal(object)
    state_changed = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.voice = None
        self.tokens: dict[str, object] = {}
        self.timer: QTimer | None = None
        self.comtypes = None

    @pyqtSlot()
    def initialize(self) -> None:
        if os.name != "nt":
            self.voices_ready.emit([])
            return
        try:
            import comtypes
            from comtypes.client import CreateObject
            comtypes.CoInitialize()
            self.comtypes = comtypes
            self.voice = CreateObject("SAPI.SpVoice")
            self.timer = QTimer(self)
            self.timer.setInterval(150)
            self.timer.timeout.connect(self._poll)
            self._enumerate()
        except Exception as exc:
            self.error.emit(f"Native Windows-SAPI konnte nicht initialisiert werden: {exc}")
            self.voices_ready.emit([])

    @pyqtSlot()
    def refresh(self) -> None:
        if self.voice is None:
            self.initialize()
        else:
            self._enumerate()

    def _enumerate(self) -> None:
        try:
            collection = self.voice.GetVoices()
            entries = []
            self.tokens.clear()
            for index in range(int(collection.Count)):
                token = collection.Item(index)
                voice_id = str(token.Id)
                name = str(token.GetDescription())
                self.tokens[voice_id] = token
                entries.append({
                    "backend": "sapi",
                    "id": voice_id,
                    "name": name,
                    "locale": "",
                    "description": "Native Windows SAPI",
                    "gender": "",
                })
            self.voices_ready.emit(entries)
        except Exception as exc:
            self.error.emit(f"SAPI-Stimmen konnten nicht gelesen werden: {exc}")
            self.voices_ready.emit([])

    @pyqtSlot(str, str, int, int)
    def speak(self, text: str, voice_id: str, rate: int, volume: int) -> None:
        if self.voice is None:
            self.error.emit("Windows SAPI ist nicht initialisiert.")
            return
        try:
            token = self.tokens.get(voice_id)
            if token is None:
                raise RuntimeError("gewählte Stimme wurde nicht gefunden")
            self.voice.Speak("", 3)  # async + purge before speak
            self.voice.Voice = token
            self.voice.Rate = max(-10, min(10, int(rate)))
            self.voice.Volume = max(0, min(100, int(volume)))
            self.voice.Speak(text, 1)  # async
            if self.timer is not None:
                self.timer.start()
            self.state_changed.emit("speaking")
        except Exception as exc:
            self.error.emit(f"SAPI-Sprachausgabe fehlgeschlagen: {exc}")
            self.state_changed.emit("error")

    @pyqtSlot()
    def pause(self) -> None:
        try:
            if self.voice is not None:
                self.voice.Pause()
                self.state_changed.emit("paused")
        except Exception as exc:
            self.error.emit(f"SAPI konnte nicht pausiert werden: {exc}")

    @pyqtSlot()
    def resume(self) -> None:
        try:
            if self.voice is not None:
                self.voice.Resume()
                self.state_changed.emit("speaking")
        except Exception as exc:
            self.error.emit(f"SAPI konnte nicht fortgesetzt werden: {exc}")

    @pyqtSlot()
    def stop(self) -> None:
        try:
            if self.voice is not None:
                self.voice.Speak("", 3)
            if self.timer is not None:
                self.timer.stop()
            self.state_changed.emit("ready")
        except Exception:
            pass

    @pyqtSlot()
    def _poll(self) -> None:
        try:
            if self.voice is None:
                return
            running_state = int(self.voice.Status.RunningState)
            if running_state == 1:  # SRSEDone
                if self.timer is not None:
                    self.timer.stop()
                self.state_changed.emit("ready")
        except Exception as exc:
            if self.timer is not None:
                self.timer.stop()
            self.error.emit(f"SAPI-Status konnte nicht gelesen werden: {exc}")
            self.state_changed.emit("error")


class SapiTtsService(QObject):
    voices_ready = pyqtSignal(object)
    state_changed = pyqtSignal(str)
    error = pyqtSignal(str)

    request_initialize = pyqtSignal()
    request_refresh = pyqtSignal()
    request_speak = pyqtSignal(str, str, int, int)
    request_pause = pyqtSignal()
    request_resume = pyqtSignal()
    request_stop = pyqtSignal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.thread = QThread(self)
        self.worker = _SapiWorker()
        self.worker.moveToThread(self.thread)
        self.request_initialize.connect(self.worker.initialize)
        self.request_refresh.connect(self.worker.refresh)
        self.request_speak.connect(self.worker.speak)
        self.request_pause.connect(self.worker.pause)
        self.request_resume.connect(self.worker.resume)
        self.request_stop.connect(self.worker.stop)
        self.worker.voices_ready.connect(self.voices_ready)
        self.worker.state_changed.connect(self.state_changed)
        self.worker.error.connect(self.error)
        self.thread.start()
        self.request_initialize.emit()

    def refresh_voices(self) -> None:
        self.request_refresh.emit()

    def speak(self, text: str, voice_id: str, rate: int, volume: int) -> None:
        self.request_speak.emit(text, voice_id, rate, volume)

    def pause(self) -> None:
        self.request_pause.emit()

    def resume(self) -> None:
        self.request_resume.emit()

    def stop(self) -> None:
        self.request_stop.emit()

    def shutdown(self) -> None:
        self.stop()
        self.thread.quit()
        self.thread.wait(1500)


class PiperTtsService(QObject):
    """Synthesizes speech with a locally installed Piper complete package."""

    synthesis_ready = pyqtSignal(str)
    error = pyqtSignal(str)
    state_changed = pyqtSignal(str)

    def __init__(self, temp_dir: Path, parent: QObject | None = None):
        super().__init__(parent)
        self.temp_dir = Path(temp_dir)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self._process: QProcess | None = None
        self._output_path: Path | None = None

    def synthesize(
        self, text: str, voice: dict, rate: int, volume: int,
        *, noise_scale: float | None = 0.45, noise_w: float | None = 0.35,
    ) -> None:
        self.cancel()
        engine_path = Path(str(voice.get("engine_path", "")))
        model_path = Path(str(voice.get("model_path", "")))
        config_path = Path(str(voice.get("config_path", "")))
        if not engine_path.is_file():
            self.error.emit(f"Piper-Laufzeit fehlt: {engine_path}")
            return
        if not model_path.is_file() or not config_path.is_file():
            self.error.emit("Das ausgewählte Piper-Komplettpaket ist unvollständig. Bitte im Sprachmanager reparieren.")
            return

        fd, output_name = tempfile.mkstemp(prefix="scifi_piper_", suffix=".wav", dir=self.temp_dir)
        os.close(fd)
        self._output_path = Path(output_name)
        self._output_path.unlink(missing_ok=True)

        # Piper uses length_scale inversely: smaller values speak faster.
        length_scale = max(0.55, min(1.65, 1.0 - (max(-10, min(10, int(rate))) * 0.045)))
        args = [
            "--model", str(model_path),
            "--config", str(config_path),
            "--output_file", str(self._output_path),
            "--length_scale", f"{length_scale:.3f}",
        ]
        speaker_id = voice.get("speaker_id")
        if speaker_id is not None:
            args.extend(["--speaker", str(int(speaker_id))])
        if noise_scale is not None:
            args.extend(["--noise_scale", f"{float(noise_scale):.3f}"])
        if noise_w is not None:
            args.extend(["--noise_w", f"{float(noise_w):.3f}"])

        process = QProcess(self)
        self._process = process
        process.setProgram(str(engine_path))
        process.setArguments(args)
        process.finished.connect(self._synthesis_finished)
        process.errorOccurred.connect(self._process_error)
        self.state_changed.emit("preparing")
        process.start()
        if not process.waitForStarted(3000):
            self._process = None
            process.deleteLater()
            self._cleanup_output()
            self.error.emit("Piper konnte nicht gestartet werden.")
            self.state_changed.emit("error")
            return
        process.write(text.encode("utf-8"))
        process.write(b"\n")
        process.closeWriteChannel()

    @pyqtSlot(QProcess.ProcessError)
    def _process_error(self, _error: QProcess.ProcessError) -> None:
        process = self.sender()
        if process is None or process is not self._process:
            return
        message = bytes(process.readAllStandardError()).decode("utf-8", errors="replace").strip()
        self.error.emit("Piper-Sprachausgabe fehlgeschlagen: " + (message or process.errorString()))

    @pyqtSlot(int, QProcess.ExitStatus)
    def _synthesis_finished(self, exit_code: int, _status: QProcess.ExitStatus) -> None:
        process = self.sender()
        if process is None or process is not self._process:
            return
        self._process = None
        stderr = bytes(process.readAllStandardError()).decode("utf-8", errors="replace").strip()
        process.deleteLater()
        if exit_code != 0 or self._output_path is None or not self._output_path.is_file() or self._output_path.stat().st_size < 44:
            self._cleanup_output()
            self.error.emit("Piper-Sprachausgabe konnte nicht erzeugt werden: " + (stderr or f"Exit-Code {exit_code}"))
            self.state_changed.emit("error")
            return
        self.synthesis_ready.emit(str(self._output_path))

    def cancel(self) -> None:
        process = self._process
        # Break the association before killing the process. This prevents a queued
        # finished/error signal from treating a canceled request as the currently
        # selected voice request when the user switches voices quickly.
        self._process = None
        if process is not None:
            try:
                process.finished.disconnect(self._synthesis_finished)
            except (TypeError, RuntimeError):
                pass
            try:
                process.errorOccurred.disconnect(self._process_error)
            except (TypeError, RuntimeError):
                pass
            try:
                if process.state() != QProcess.ProcessState.NotRunning:
                    process.kill()
                    process.waitForFinished(1000)
            finally:
                process.deleteLater()
        self._cleanup_output()

    def release_output(self) -> None:
        self._cleanup_output()

    def _cleanup_output(self) -> None:
        if self._output_path is not None:
            try:
                self._output_path.unlink(missing_ok=True)
            except OSError:
                pass
            self._output_path = None
