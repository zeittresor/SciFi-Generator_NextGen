from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
import math
import os
import tempfile
import wave

from PyQt6.QtCore import QObject, QProcess, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QSlider, QWidget


PIPER_MODE_SECTIONS = "sections"
PIPER_MODE_CONTINUOUS = "continuous"
PIPER_PITCH_MIN = -6
PIPER_PITCH_MAX = 6

_EXPORT_WINDOW: ContextVar[object | None] = ContextVar("scifi_v6028_export_window", default=None)
_INSTALLED_MODULE_IDS: set[int] = set()


def prepare_piper_text(text: str, mode: str) -> str:
    """Prepare text for Piper without changing the visible story.

    Piper's standalone CLI treats every input line as a separate utterance. The
    historical SciFi-Generator behavior deliberately keeps those line boundaries,
    which can sound lively but also restarts pitch and rhythm at every story block.
    Continuous mode removes internal line boundaries and submits one utterance.
    """
    normalized = str(text).replace("\r\n", "\n").replace("\r", "\n").strip()
    if mode != PIPER_MODE_CONTINUOUS:
        return normalized
    parts = [" ".join(line.split()) for line in normalized.split("\n") if line.strip()]
    return " ".join(parts).strip()


def pitch_factor(semitones: int | float) -> float:
    value = max(PIPER_PITCH_MIN, min(PIPER_PITCH_MAX, float(semitones)))
    return 2.0 ** (value / 12.0)


def ffmpeg_pitch_filter(sample_rate: int, semitones: int | float) -> str:
    """Return a duration-compensated FFmpeg pitch filter.

    asetrate changes pitch and duration. atempo applies the inverse duration
    correction, so the requested speaking speed remains controlled by Piper's
    length_scale instead of changing together with pitch.
    """
    rate = max(8000, int(sample_rate))
    factor = pitch_factor(semitones)
    tempo = 1.0 / factor
    return (
        f"asetrate={rate}*{factor:.12f},"
        f"aresample={rate},"
        f"atempo={tempo:.12f}"
    )


def _wav_sample_rate(path: Path) -> int:
    try:
        with wave.open(str(path), "rb") as handle:
            return int(handle.getframerate())
    except (OSError, wave.Error) as exc:
        raise RuntimeError(f"WAV-Abtastrate konnte nicht gelesen werden: {exc}") from exc


def _unlink(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


class EnhancedPiperTtsService(QObject):
    """Piper playback service with selectable utterance flow and pitch shift."""

    synthesis_ready = pyqtSignal(str)
    error = pyqtSignal(str)
    state_changed = pyqtSignal(str)

    def __init__(self, temp_dir: Path, parent: QObject | None = None):
        super().__init__(parent)
        self.temp_dir = Path(temp_dir)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self._process: QProcess | None = None
        self._phase = ""
        self._raw_output_path: Path | None = None
        self._output_path: Path | None = None
        self.synthesis_mode = PIPER_MODE_SECTIONS
        self.pitch_semitones = 0
        self.ffmpeg_path: Path | None = None

    def _new_temp_wav(self, prefix: str) -> Path:
        fd, name = tempfile.mkstemp(prefix=prefix, suffix=".wav", dir=self.temp_dir)
        os.close(fd)
        path = Path(name)
        path.unlink(missing_ok=True)
        return path

    def synthesize(
        self,
        text: str,
        voice: dict,
        rate: int,
        volume: int,
        *,
        noise_scale: float | None = 0.45,
        noise_w: float | None = 0.35,
    ) -> None:
        del volume  # Playback volume is handled by QAudioOutput, as before.
        self.cancel()
        engine_path = Path(str(voice.get("engine_path", "")))
        model_path = Path(str(voice.get("model_path", "")))
        config_path = Path(str(voice.get("config_path", "")))
        if not engine_path.is_file():
            self.error.emit(f"Piper-Laufzeit fehlt: {engine_path}")
            self.state_changed.emit("error")
            return
        if not model_path.is_file() or not config_path.is_file():
            self.error.emit(
                "Das ausgewählte Piper-Komplettpaket ist unvollständig. "
                "Bitte im Sprachmanager reparieren."
            )
            self.state_changed.emit("error")
            return

        prepared_text = prepare_piper_text(text, self.synthesis_mode)
        if not prepared_text:
            self.error.emit("Der Piper-Erzähltext ist leer.")
            self.state_changed.emit("error")
            return

        requested_pitch = max(PIPER_PITCH_MIN, min(PIPER_PITCH_MAX, int(self.pitch_semitones)))
        ffmpeg = Path(self.ffmpeg_path) if self.ffmpeg_path else None
        if requested_pitch and (ffmpeg is None or not ffmpeg.is_file()):
            requested_pitch = 0
        self.pitch_semitones = requested_pitch

        self._raw_output_path = self._new_temp_wav("scifi_piper_raw_")
        self._output_path = (
            self._new_temp_wav("scifi_piper_pitch_")
            if requested_pitch
            else self._raw_output_path
        )

        # Piper uses length_scale inversely: smaller values speak faster.
        length_scale = max(
            0.55,
            min(1.65, 1.0 - (max(-10, min(10, int(rate))) * 0.045)),
        )
        args = [
            "--model", str(model_path),
            "--config", str(config_path),
            "--output_file", str(self._raw_output_path),
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
        self._phase = "piper"
        process.setProgram(str(engine_path))
        process.setArguments(args)
        process.finished.connect(self._process_finished)
        process.errorOccurred.connect(self._process_error)
        self.state_changed.emit("preparing")
        process.start()
        if not process.waitForStarted(3000):
            self._process = None
            process.deleteLater()
            self._cleanup_outputs()
            self.error.emit("Piper konnte nicht gestartet werden.")
            self.state_changed.emit("error")
            return
        process.write(prepared_text.encode("utf-8"))
        process.write(b"\n")
        process.closeWriteChannel()

    def _start_pitch_process(self) -> None:
        raw = self._raw_output_path
        output = self._output_path
        ffmpeg = Path(self.ffmpeg_path) if self.ffmpeg_path else None
        if raw is None or output is None or ffmpeg is None or not ffmpeg.is_file():
            raise RuntimeError("FFmpeg steht für die Piper-Tonhöhenänderung nicht zur Verfügung.")
        sample_rate = _wav_sample_rate(raw)
        audio_filter = ffmpeg_pitch_filter(sample_rate, self.pitch_semitones)
        process = QProcess(self)
        self._process = process
        self._phase = "pitch"
        process.setProgram(str(ffmpeg))
        process.setArguments([
            "-y",
            "-i", str(raw),
            "-vn",
            "-af", audio_filter,
            "-acodec", "pcm_s16le",
            str(output),
        ])
        process.finished.connect(self._process_finished)
        process.errorOccurred.connect(self._process_error)
        process.start()
        if not process.waitForStarted(3000):
            self._process = None
            process.deleteLater()
            raise RuntimeError("FFmpeg konnte für die Tonhöhenänderung nicht gestartet werden.")

    @pyqtSlot(QProcess.ProcessError)
    def _process_error(self, _error: QProcess.ProcessError) -> None:
        process = self.sender()
        if process is None or process is not self._process:
            return
        message = bytes(process.readAllStandardError()).decode("utf-8", errors="replace").strip()
        phase = "Piper-Sprachausgabe" if self._phase == "piper" else "Piper-Tonhöhenänderung"
        self.error.emit(f"{phase} fehlgeschlagen: " + (message or process.errorString()))

    @pyqtSlot(int, QProcess.ExitStatus)
    def _process_finished(self, exit_code: int, _status: QProcess.ExitStatus) -> None:
        process = self.sender()
        if process is None or process is not self._process:
            return
        phase = self._phase
        self._process = None
        stderr = bytes(process.readAllStandardError()).decode("utf-8", errors="replace").strip()
        process.deleteLater()

        if phase == "piper":
            raw = self._raw_output_path
            if exit_code != 0 or raw is None or not raw.is_file() or raw.stat().st_size < 44:
                self._cleanup_outputs()
                self.error.emit(
                    "Piper-Sprachausgabe konnte nicht erzeugt werden: "
                    + (stderr or f"Exit-Code {exit_code}")
                )
                self.state_changed.emit("error")
                return
            if self.pitch_semitones:
                try:
                    self._start_pitch_process()
                except Exception as exc:
                    self._cleanup_outputs()
                    self.error.emit(str(exc))
                    self.state_changed.emit("error")
                return
            self.synthesis_ready.emit(str(raw))
            return

        output = self._output_path
        if exit_code != 0 or output is None or not output.is_file() or output.stat().st_size < 44:
            self._cleanup_outputs()
            self.error.emit(
                "Piper-Tonhöhenänderung konnte nicht erzeugt werden: "
                + (stderr or f"Exit-Code {exit_code}")
            )
            self.state_changed.emit("error")
            return
        if self._raw_output_path != output:
            _unlink(self._raw_output_path)
            self._raw_output_path = None
        self.synthesis_ready.emit(str(output))

    def cancel(self) -> None:
        process = self._process
        self._process = None
        self._phase = ""
        if process is not None:
            try:
                process.finished.disconnect(self._process_finished)
            except (TypeError, RuntimeError):
                pass
            try:
                process.errorOccurred.disconnect(self._process_error)
            except (TypeError, RuntimeError):
                pass
            try:
                if process.state() != QProcess.ProcessState.NotRunning:
                    process.kill()
                    process.waitForFinished(1200)
            finally:
                process.deleteLater()
        self._cleanup_outputs()

    def release_output(self) -> None:
        self._cleanup_outputs()

    def _cleanup_outputs(self) -> None:
        raw = self._raw_output_path
        output = self._output_path
        self._raw_output_path = None
        self._output_path = None
        _unlink(raw)
        if output != raw:
            _unlink(output)


def _apply_control_values(window: object, settings: dict) -> None:
    mode_combo = getattr(window, "piper_synthesis_mode_combo", None)
    pitch_slider = getattr(window, "piper_pitch_slider", None)
    if mode_combo is None or pitch_slider is None:
        setattr(window, "_v6028_pending_settings", dict(settings))
        return

    mode = str(settings.get("piper_synthesis_mode", PIPER_MODE_SECTIONS))
    if mode not in {PIPER_MODE_SECTIONS, PIPER_MODE_CONTINUOUS}:
        mode = PIPER_MODE_SECTIONS
    pitch = max(
        PIPER_PITCH_MIN,
        min(PIPER_PITCH_MAX, int(settings.get("piper_pitch_semitones", 0) or 0)),
    )
    if not pitch_slider.isEnabled():
        pitch = 0

    mode_combo.blockSignals(True)
    pitch_slider.blockSignals(True)
    mode_index = mode_combo.findData(mode)
    mode_combo.setCurrentIndex(mode_index if mode_index >= 0 else 0)
    pitch_slider.setValue(pitch)
    mode_combo.blockSignals(False)
    pitch_slider.blockSignals(False)
    _update_pitch_label(window)
    setattr(window, "_v6028_pending_settings", dict(settings))


def _update_pitch_label(window: object) -> None:
    slider = getattr(window, "piper_pitch_slider", None)
    label = getattr(window, "piper_pitch_value_label", None)
    if slider is None or label is None:
        return
    value = int(slider.value())
    if value == 0:
        label.setText("Original")
    elif value > 0:
        label.setText(f"+{value} Halbtöne")
    else:
        label.setText(f"{value} Halbtöne")


def _install_controls(window: object, app_module: object) -> None:
    if hasattr(window, "piper_synthesis_mode_combo"):
        return
    form = window.piper_options_group.layout()

    mode_combo = QComboBox(window.piper_options_group)
    mode_combo.addItem("Abschnittsweise — lebendiger / wechselnder", PIPER_MODE_SECTIONS)
    mode_combo.addItem("Gesamtstory in einem Fluss — gleichmäßiger", PIPER_MODE_CONTINUOUS)
    mode_combo.setToolTip(
        "Abschnittsweise behält die Zeilengrenzen der Story und lässt Piper die Prosodie je Block neu ansetzen. "
        "Gesamtfluss entfernt interne Zeilenumbrüche vor der Synthese."
    )
    window.piper_synthesis_mode_combo = mode_combo
    form.addRow("Syntheseart:", mode_combo)

    mode_hint = QLabel(
        "Der Gesamtfluss klingt meist einheitlicher. Die abschnittsweise Synthese kann unterhaltsamer wirken, "
        "aber Tonlage und Sprechtempo zwischen Storyblöcken stärker variieren.",
        window.piper_options_group,
    )
    mode_hint.setWordWrap(True)
    window.piper_synthesis_mode_hint = mode_hint
    form.addRow("", mode_hint)

    pitch_widget = QWidget(window.piper_options_group)
    pitch_layout = QHBoxLayout(pitch_widget)
    pitch_layout.setContentsMargins(0, 0, 0, 0)
    pitch_slider = QSlider(Qt.Orientation.Horizontal, pitch_widget)
    pitch_slider.setRange(PIPER_PITCH_MIN, PIPER_PITCH_MAX)
    pitch_slider.setValue(0)
    pitch_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
    pitch_slider.setTickInterval(1)
    pitch_value = QLabel("Original", pitch_widget)
    pitch_value.setMinimumWidth(92)
    pitch_layout.addWidget(pitch_slider, 1)
    pitch_layout.addWidget(pitch_value)
    window.piper_pitch_slider = pitch_slider
    window.piper_pitch_value_label = pitch_value
    form.addRow("Tonhöhe:", pitch_widget)

    ffmpeg = app_module.find_ffmpeg(app_module.TOOLS_DIR)
    window._v6028_ffmpeg_path = ffmpeg
    pitch_hint = QLabel(window.piper_options_group)
    pitch_hint.setWordWrap(True)
    window.piper_pitch_hint = pitch_hint
    if ffmpeg is None:
        pitch_slider.setEnabled(False)
        pitch_hint.setText(
            "Tonhöhe bleibt auf Original. Für eine unabhängige Tonhöhenänderung wird FFmpeg im Ordner tools "
            "oder im PATH benötigt."
        )
    else:
        pitch_hint.setText(
            "Ändert die Tonhöhe um Halbtöne. Das Sprechtempo wird anschließend ausgeglichen und bleibt vom "
            "Geschwindigkeitsregler getrennt."
        )
    form.addRow("", pitch_hint)

    pending = getattr(window, "_v6028_pending_settings", {})
    _apply_control_values(window, pending if isinstance(pending, dict) else {})

    mode_combo.currentIndexChanged.connect(window._schedule_settings_save)
    mode_combo.currentIndexChanged.connect(window._update_tab_status_summaries)
    pitch_slider.valueChanged.connect(lambda _value: _update_pitch_label(window))
    pitch_slider.valueChanged.connect(window._schedule_settings_save)
    pitch_slider.valueChanged.connect(window._update_tab_status_summaries)


def _replace_piper_service(window: object, app_module: object) -> None:
    old_service = getattr(window, "piper_service", None)
    if old_service is not None:
        try:
            old_service.cancel()
        except Exception:
            pass
        try:
            old_service.deleteLater()
        except Exception:
            pass

    service = EnhancedPiperTtsService(app_module.TEMP_DIR, window)
    service.synthesis_ready.connect(window._piper_synthesis_ready)
    service.error.connect(window._voice_service_error)
    service.state_changed.connect(lambda state: window._handle_speech_state("piper", state))
    window.piper_service = service


def install(app_module: object) -> None:
    """Install the v60.28 GUI/service extension into the imported app module."""
    module_id = id(app_module)
    if module_id in _INSTALLED_MODULE_IDS:
        return
    _INSTALLED_MODULE_IDS.add(module_id)

    original_request_class = app_module.AudioExportRequest
    original_worker_class = app_module.AudioExportWorker

    @dataclass(frozen=True)
    class V6028AudioExportRequest(original_request_class):
        piper_synthesis_mode: str = PIPER_MODE_SECTIONS
        piper_pitch_semitones: int = 0

    def request_factory(*args, **kwargs):
        window = _EXPORT_WINDOW.get()
        if window is not None and str(kwargs.get("backend", "")) == "piper":
            combo = getattr(window, "piper_synthesis_mode_combo", None)
            slider = getattr(window, "piper_pitch_slider", None)
            kwargs.setdefault(
                "piper_synthesis_mode",
                str(combo.currentData() or PIPER_MODE_SECTIONS) if combo is not None else PIPER_MODE_SECTIONS,
            )
            kwargs.setdefault(
                "piper_pitch_semitones",
                int(slider.value()) if slider is not None and slider.isEnabled() else 0,
            )
        return V6028AudioExportRequest(*args, **kwargs)

    class V6028AudioExportWorker(original_worker_class):
        def _synthesize(self, input_path: Path, narration_path: Path) -> None:
            request = self.request
            if request.backend == "piper":
                mode = str(getattr(request, "piper_synthesis_mode", PIPER_MODE_SECTIONS))
                prepared = prepare_piper_text(input_path.read_text(encoding="utf-8"), mode)
                input_path.write_text(prepared, encoding="utf-8")
            super()._synthesize(input_path, narration_path)

            if request.backend != "piper":
                return
            semitones = max(
                PIPER_PITCH_MIN,
                min(PIPER_PITCH_MAX, int(getattr(request, "piper_pitch_semitones", 0) or 0)),
            )
            if not semitones:
                return
            ffmpeg = Path(request.ffmpeg_path or "")
            if not ffmpeg.is_file():
                raise RuntimeError(
                    "Für die gewählte Piper-Tonhöhe wird FFmpeg im Ordner tools oder im PATH benötigt."
                )
            shifted = narration_path.with_name("narration_pitch.wav")
            sample_rate = _wav_sample_rate(narration_path)
            self._run_process(
                [
                    str(ffmpeg), "-y",
                    "-i", str(narration_path),
                    "-vn",
                    "-af", ffmpeg_pitch_filter(sample_rate, semitones),
                    "-acodec", "pcm_s16le",
                    str(shifted),
                ],
                "Piper-Tonhöhenänderung",
            )
            if not shifted.is_file() or shifted.stat().st_size < 44:
                raise RuntimeError("Die Piper-Tonhöhenänderung hat keine verwendbare WAV-Datei erzeugt.")
            os.replace(shifted, narration_path)

    app_module.AudioExportRequest = request_factory
    app_module.AudioExportWorker = V6028AudioExportWorker

    main_window_class = app_module.MainWindow
    original_init = main_window_class.__init__
    original_apply_settings = main_window_class._apply_settings_dict
    original_collect_settings = main_window_class._collect_settings
    original_speak = main_window_class._speak
    original_save_audio = main_window_class.save_story_audio
    original_update_summary = main_window_class._update_tab_status_summaries

    def patched_apply_settings(self, settings: dict) -> None:
        self._v6028_pending_settings = dict(settings) if isinstance(settings, dict) else {}
        original_apply_settings(self, settings)
        if hasattr(self, "piper_synthesis_mode_combo"):
            _apply_control_values(self, self._v6028_pending_settings)

    def patched_collect_settings(self) -> dict:
        payload = original_collect_settings(self)
        combo = getattr(self, "piper_synthesis_mode_combo", None)
        slider = getattr(self, "piper_pitch_slider", None)
        payload["piper_synthesis_mode"] = (
            str(combo.currentData() or PIPER_MODE_SECTIONS)
            if combo is not None
            else PIPER_MODE_SECTIONS
        )
        payload["piper_pitch_semitones"] = (
            int(slider.value()) if slider is not None and slider.isEnabled() else 0
        )
        payload["ui_layout_version"] = max(8, int(payload.get("ui_layout_version", 0) or 0))
        return payload

    def patched_speak(self, text: str, *, with_background: bool, purpose: str = "generic") -> None:
        entry = self.voice_combo.currentData() or {}
        if entry.get("backend") == "piper":
            combo = getattr(self, "piper_synthesis_mode_combo", None)
            slider = getattr(self, "piper_pitch_slider", None)
            self.piper_service.synthesis_mode = (
                str(combo.currentData() or PIPER_MODE_SECTIONS)
                if combo is not None
                else PIPER_MODE_SECTIONS
            )
            self.piper_service.pitch_semitones = (
                int(slider.value()) if slider is not None and slider.isEnabled() else 0
            )
            self.piper_service.ffmpeg_path = getattr(self, "_v6028_ffmpeg_path", None)
            self.runtime_diagnostics.breadcrumb(
                "piper_flow_settings",
                synthesis_mode=self.piper_service.synthesis_mode,
                pitch_semitones=self.piper_service.pitch_semitones,
            )
        return original_speak(self, text, with_background=with_background, purpose=purpose)

    def patched_save_audio(self) -> None:
        token = _EXPORT_WINDOW.set(self)
        try:
            return original_save_audio(self)
        finally:
            _EXPORT_WINDOW.reset(token)

    def patched_update_summary(self, *args) -> None:
        original_update_summary(self, *args)
        entry = self.voice_combo.currentData() if self.voice_combo.count() else None
        if not entry or entry.get("backend") != "piper":
            return
        label = getattr(self, "audio_tab_status_label", None)
        combo = getattr(self, "piper_synthesis_mode_combo", None)
        slider = getattr(self, "piper_pitch_slider", None)
        if label is None or combo is None or slider is None:
            return
        mode_label = "Gesamtfluss" if combo.currentData() == PIPER_MODE_CONTINUOUS else "Abschnitte"
        pitch_value = int(slider.value()) if slider.isEnabled() else 0
        pitch_label = "Originaltonhöhe" if pitch_value == 0 else f"Tonhöhe {pitch_value:+d} HT"
        label.setText(label.text() + f"; {mode_label}; {pitch_label}")

    def patched_init(self) -> None:
        original_init(self)
        _install_controls(self, app_module)
        _replace_piper_service(self, app_module)
        pending = getattr(self, "_v6028_pending_settings", {})
        _apply_control_values(self, pending if isinstance(pending, dict) else {})
        self._update_tab_status_summaries()

    main_window_class._apply_settings_dict = patched_apply_settings
    main_window_class._collect_settings = patched_collect_settings
    main_window_class._speak = patched_speak
    main_window_class.save_story_audio = patched_save_audio
    main_window_class._update_tab_status_summaries = patched_update_summary
    main_window_class.__init__ = patched_init
