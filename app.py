from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QFont, QIcon, QResizeEvent
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtTextToSpeech import QTextToSpeech
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QFrame,
    QGroupBox, QHBoxLayout, QLabel, QLayout, QMainWindow, QMessageBox,
    QProgressBar, QPushButton, QScrollArea, QSizePolicy, QSlider, QSpinBox,
    QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from story_engine import APP_VERSION, GenerationResult, StoryEngine, StoryEngineError
from theme_manager import ThemeManager
from tts_services import SapiTtsService, WinRtTtsService

APP_NAME = "SciFi-Generator"
BASE_DIR = Path(__file__).resolve().parent
VARS_DIR = BASE_DIR / "data" / "vars"
SEQUENCE_FILE = BASE_DIR / "sequence_legacy.json"
SOUND_FILE = BASE_DIR / "data" / "sounds" / "background.wav"
LOG_DIR = BASE_DIR / "logs"
THEME_DIR = BASE_DIR / "themes"
TOOLS_DIR = BASE_DIR / "tools"
TEMP_DIR = BASE_DIR / "temp"
SETTINGS_FILE = BASE_DIR / "settings.json"

BACKEND_LABELS = {
    "winrt": "Windows OneCore/WinRT",
    "sapi": "Windows SAPI",
    "qt": "Qt",
}

BASE_COMPACT_WIDTH = 420
BASE_WINDOW_HEIGHT = 720
BASE_CONTROL_VIEWPORT_WIDTH = 390
BASE_CONTROL_VIEWPORT_HEIGHT = 680
MAX_UI_SCALE = 1.50


def emergency_stylesheet(scale: float = 1.0) -> str:
    px = lambda value: max(1, round(value * scale))
    return f"""
QMainWindow, QWidget {{ background: #1B1D21; color: #F2F4F7; }}
QTextEdit, QComboBox, QSpinBox {{ background: #0F1115; color: #FFFFFF; border: 1px solid #788493; }}
QComboBox, QSpinBox {{ min-height: {px(26)}px; padding: {px(2)}px {px(5)}px; }}
QPushButton {{ background: #343941; color: #FFFFFF; border: 1px solid #788493; padding: {px(5)}px {px(9)}px; min-height: {px(28)}px; }}
QPushButton:hover {{ background: #48505B; }}
QGroupBox {{ border: 1px solid #788493; margin-top: {px(9)}px; padding-top: {px(9)}px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: {px(8)}px; padding: 0 {px(4)}px; }}
QScrollBar:vertical {{ width: {px(14)}px; }}
QScrollBar:horizontal {{ height: {px(14)}px; }}
"""


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.engine = StoryEngine(VARS_DIR, SEQUENCE_FILE)
        self.result: GenerationResult | None = None
        self.current_log = ""
        self.playback_active = False
        self.active_backend: str | None = None
        self.speech_state = "ready"
        self._pending_background = False
        self._winrt_audio_file: str | None = None
        self.voice_catalogs: dict[str, list[dict]] = {"winrt": [], "sapi": [], "qt": []}
        self.qt_voice_objects: dict[str, object] = {}
        self.voice_diagnostics: list[str] = []
        self.saved_voice_backend = ""
        self.saved_voice_id = ""
        self.saved_voice_name = ""

        app = QApplication.instance()
        self._base_app_font = QFont(app.font())
        self._base_font_point_size = max(8.0, self._base_app_font.pointSizeF())
        self._ui_scale = 1.0
        self._ui_scale_timer = QTimer(self)
        self._ui_scale_timer.setSingleShot(True)
        self._ui_scale_timer.setInterval(90)
        self._ui_scale_timer.timeout.connect(self._update_ui_scale)

        self.theme_manager = ThemeManager(THEME_DIR)
        self.theme_manager.load()

        self.qt_tts = QTextToSpeech(self)
        self.qt_tts.stateChanged.connect(self._qt_tts_state_changed)

        self.background_audio = QAudioOutput(self)
        self.background_player = QMediaPlayer(self)
        self.background_player.setAudioOutput(self.background_audio)
        if SOUND_FILE.is_file():
            self.background_player.setSource(QUrl.fromLocalFile(str(SOUND_FILE)))
            try:
                self.background_player.setLoops(QMediaPlayer.Loops.Infinite)
            except AttributeError:
                self.background_player.setLoops(-1)

        self.narration_audio = QAudioOutput(self)
        self.narration_player = QMediaPlayer(self)
        self.narration_player.setAudioOutput(self.narration_audio)
        self.narration_player.mediaStatusChanged.connect(self._narration_media_status_changed)

        self.winrt_service = WinRtTtsService(TOOLS_DIR, TEMP_DIR, self)
        self.winrt_service.voices_ready.connect(self._winrt_voices_ready)
        self.winrt_service.synthesis_ready.connect(self._winrt_synthesis_ready)
        self.winrt_service.error.connect(self._voice_service_error)
        self.winrt_service.state_changed.connect(lambda state: self._handle_speech_state("winrt", state))

        self.sapi_service = SapiTtsService(self)
        self.sapi_service.voices_ready.connect(self._sapi_voices_ready)
        self.sapi_service.state_changed.connect(lambda state: self._handle_speech_state("sapi", state))
        self.sapi_service.error.connect(self._voice_service_error)

        self._build_ui()
        self._load_qt_voices()
        self._load_settings()
        self._validate_installation()
        self.winrt_service.refresh_voices()
        QTimer.singleShot(0, self._update_ui_scale)

    def _build_ui(self) -> None:
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(BASE_COMPACT_WIDTH, BASE_WINDOW_HEIGHT)
        self.setMinimumSize(330, 480)
        icon_path = BASE_DIR / "app_icon.svg"
        if icon_path.is_file():
            self.setWindowIcon(QIcon(str(icon_path)))

        central = QWidget()
        root = QHBoxLayout(central)
        self.root_layout = root
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)
        self.setCentralWidget(central)

        self.tabs = QTabWidget()
        self.story_edit = QTextEdit()
        self.story_edit.setPlaceholderText("Zuerst „Sektor-Sprung berechnen“ anklicken …")
        self.story_edit.setAcceptRichText(False)
        self.story_edit.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setAcceptRichText(False)
        self.tabs.addTab(self.story_edit, "Story")
        self.tabs.addTab(self.log_edit, "Auswahlprotokoll")
        self.tabs.setMinimumWidth(570)
        self.tabs.hide()
        root.addWidget(self.tabs, 2)

        controls = QWidget()
        self.controls_widget = controls
        controls.setObjectName("controlsContent")
        controls.setMinimumWidth(340)
        controls.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.MinimumExpanding,
        )
        right = QVBoxLayout(controls)
        self.controls_layout = right
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(8)
        right.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)

        action_group = QGroupBox("Sektor-Sprung")
        action_layout = QVBoxLayout(action_group)
        self.generate_button = QPushButton("Sektor-Sprung berechnen")
        self.generate_button.setToolTip("Erzeugt eine neue Geschichte, liest sie aber noch nicht vor.")
        self.generate_button.clicked.connect(self.generate_story)
        self.execute_button = QPushButton("Sprung durchführen")
        self.execute_button.setToolTip("Liest die zuvor berechnete Geschichte mit der ausgewählten Windows-Stimme vor.")
        self.execute_button.clicked.connect(self.execute_jump)
        self.execute_button.setEnabled(False)
        self.toggle_story_button = QPushButton("Story / Log einblenden  >")
        self.toggle_story_button.setToolTip("Blendet die berechnete Story und das Auswahlprotokoll ein oder aus.")
        self.toggle_story_button.clicked.connect(self.toggle_story_panel)
        action_layout.addWidget(self.generate_button)
        action_layout.addWidget(self.execute_button)
        action_layout.addWidget(self.toggle_story_button)
        right.addWidget(action_group)

        speech_group = QGroupBox("Sprachausgabe")
        speech_layout = QVBoxLayout(speech_group)
        voice_form = QFormLayout()
        voice_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        voice_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.voice_combo = QComboBox()
        self.voice_combo.setMinimumContentsLength(22)
        self.voice_combo.currentIndexChanged.connect(self._voice_changed)
        voice_form.addRow("Stimme:", self.voice_combo)
        speech_layout.addLayout(voice_form)

        voice_info_row = QHBoxLayout()
        self.voice_count_label = QLabel("Stimmen werden gesucht …")
        self.voice_count_label.setWordWrap(True)
        self.refresh_voices_button = QPushButton("Neu laden")
        self.refresh_voices_button.setToolTip("Liest die Stimmen aus Windows OneCore/WinRT, nativer SAPI und Qt erneut ein.")
        self.refresh_voices_button.clicked.connect(self.refresh_voices)
        voice_info_row.addWidget(self.voice_count_label, 1)
        voice_info_row.addWidget(self.refresh_voices_button)
        speech_layout.addLayout(voice_info_row)

        speech_layout.addWidget(QLabel("Geschwindigkeit"))
        self.rate_slider = QSlider(Qt.Orientation.Horizontal)
        self.rate_slider.setRange(-10, 10)
        self.rate_slider.setValue(0)
        self.rate_slider.valueChanged.connect(lambda value: self.qt_tts.setRate(value / 10.0))
        speech_layout.addWidget(self.rate_slider)

        speech_layout.addWidget(QLabel("Lautstärke Stimme"))
        self.voice_volume = QSlider(Qt.Orientation.Horizontal)
        self.voice_volume.setRange(0, 100)
        self.voice_volume.setValue(100)
        self.voice_volume.valueChanged.connect(lambda value: self.qt_tts.setVolume(value / 100.0))
        speech_layout.addWidget(self.voice_volume)

        player_row = QHBoxLayout()
        self.pause_button = QPushButton("Pause")
        self.pause_button.clicked.connect(self.pause_or_resume)
        self.pause_button.setEnabled(False)
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop_playback)
        self.stop_button.setEnabled(False)
        player_row.addWidget(self.pause_button)
        player_row.addWidget(self.stop_button)
        speech_layout.addLayout(player_row)

        self.selection_button = QPushButton("Story / Markierung vorlesen")
        self.selection_button.setToolTip("Liest den markierten Text vor; ohne Markierung wird die ganze Story gelesen.")
        self.selection_button.clicked.connect(self.speak_selection)
        speech_layout.addWidget(self.selection_button)
        right.addWidget(speech_group)

        ambience_group = QGroupBox("Brückenatmosphäre")
        ambience_layout = QVBoxLayout(ambience_group)
        self.background_check = QCheckBox("Hintergrundsound während des Vorlesens")
        self.background_check.setChecked(True)
        ambience_layout.addWidget(self.background_check)
        ambience_layout.addWidget(QLabel("Lautstärke Hintergrund"))
        self.background_volume = QSlider(Qt.Orientation.Horizontal)
        self.background_volume.setRange(0, 100)
        self.background_volume.setValue(18)
        self.background_volume.valueChanged.connect(lambda value: self.background_audio.setVolume(value / 100.0))
        ambience_layout.addWidget(self.background_volume)
        right.addWidget(ambience_group)

        options_group = QGroupBox("Generierung")
        options_layout = QVBoxLayout(options_group)
        self.legacy_umlauts = QCheckBox("Legacy-Umlautkonvertierung (ae/ue/oe)")
        self.legacy_umlauts.setChecked(True)
        self.ignore_blanks = QCheckBox("Leere Zeilen in Satzdateien ignorieren")
        self.ignore_blanks.setChecked(True)
        self.write_log = QCheckBox("Protokolldatei automatisch speichern")
        self.write_log.setChecked(True)
        options_layout.addWidget(self.legacy_umlauts)
        options_layout.addWidget(self.ignore_blanks)
        options_layout.addWidget(self.write_log)
        seed_form = QFormLayout()
        seed_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        seed_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.seed_spin = QSpinBox()
        self.seed_spin.setRange(0, 2_147_483_647)
        self.seed_spin.setSpecialValueText("Zufällig")
        self.seed_spin.setValue(0)
        seed_form.addRow("Seed:", self.seed_spin)
        options_layout.addLayout(seed_form)
        right.addWidget(options_group)

        utility_row = QHBoxLayout()
        self.save_button = QPushButton("Speichern …")
        self.save_button.clicked.connect(self.save_story)
        self.clear_button = QPushButton("Text löschen")
        self.clear_button.clicked.connect(self.clear_story)
        utility_row.addWidget(self.save_button)
        utility_row.addWidget(self.clear_button)
        right.addLayout(utility_row)

        theme_form = QFormLayout()
        theme_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        theme_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.theme_combo = QComboBox()
        self.theme_combo.currentTextChanged.connect(self.apply_theme)
        theme_form.addRow("Theme:", self.theme_combo)
        right.addLayout(theme_form)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status_label = QLabel("Bereit.")
        self.status_label.setWordWrap(True)
        right.addWidget(self.progress)
        right.addWidget(self.status_label)
        right.addStretch(1)

        self.controls_scroll = QScrollArea()
        self.controls_scroll.setObjectName("controlsScrollArea")
        self.controls_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.controls_scroll.setWidgetResizable(True)
        self.controls_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.controls_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.controls_scroll.setMinimumWidth(250)
        self.controls_scroll.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.controls_scroll.setWidget(controls)
        root.addWidget(self.controls_scroll, 1)

        self._populate_theme_combo()
        self._build_menus()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_ui_scale_timer"):
            self._ui_scale_timer.start()

    def _calculate_ui_scale(self) -> float:
        if not hasattr(self, "controls_scroll") or not self.controls_scroll.viewport():
            return 1.0
        viewport = self.controls_scroll.viewport()
        width_ratio = max(1.0, viewport.width() / BASE_CONTROL_VIEWPORT_WIDTH)
        height_ratio = max(1.0, self.centralWidget().height() / BASE_CONTROL_VIEWPORT_HEIGHT)
        return round(min(MAX_UI_SCALE, width_ratio, height_ratio), 2)

    def _update_ui_scale(self) -> None:
        scale = self._calculate_ui_scale()
        if abs(scale - self._ui_scale) < 0.025:
            return
        self._ui_scale = scale

        font = QFont(self._base_app_font)
        font.setPointSizeF(round(self._base_font_point_size * scale, 2))
        QApplication.instance().setFont(font)

        self.controls_widget.setMinimumWidth(round(340 * scale))
        self.tabs.setMinimumWidth(round(570 * scale))
        margin = round(8 * scale)
        self.root_layout.setContentsMargins(margin, margin, margin, margin)
        self.root_layout.setSpacing(round(8 * scale))
        self.controls_layout.setSpacing(round(8 * scale))

        self.apply_theme(self.theme_combo.currentText())
        self.controls_widget.updateGeometry()
        self.controls_scroll.updateGeometry()

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("Datei")
        save_action = QAction("Story speichern …", self)
        save_action.triggered.connect(self.save_story)
        file_menu.addAction(save_action)
        open_vars = QAction("Satzteil-Ordner öffnen", self)
        open_vars.triggered.connect(lambda: self._open_path(VARS_DIR))
        file_menu.addAction(open_vars)
        open_sequence = QAction("Reihenfolge öffnen", self)
        open_sequence.triggered.connect(lambda: self._open_path(SEQUENCE_FILE))
        file_menu.addAction(open_sequence)
        open_logs = QAction("Log-Ordner öffnen", self)
        open_logs.triggered.connect(lambda: self._open_path(LOG_DIR))
        file_menu.addAction(open_logs)
        file_menu.addSeparator()
        quit_action = QAction("Beenden", self)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        view_menu = self.menuBar().addMenu("Ansicht")
        toggle_action = QAction("Story / Log ein- oder ausblenden", self)
        toggle_action.triggered.connect(self.toggle_story_panel)
        view_menu.addAction(toggle_action)
        open_themes = QAction("Theme-Ordner öffnen", self)
        open_themes.triggered.connect(lambda: self._open_path(THEME_DIR))
        view_menu.addAction(open_themes)
        reload_themes = QAction("Themes neu laden", self)
        reload_themes.triggered.connect(self.reload_themes)
        view_menu.addAction(reload_themes)

        help_menu = self.menuBar().addMenu("Hilfe")
        voice_diag = QAction("TTS-Stimmendiagnose", self)
        voice_diag.triggered.connect(self.show_voice_diagnostics)
        help_menu.addAction(voice_diag)
        theme_diag = QAction("Theme-Prüfung", self)
        theme_diag.triggered.connect(self.show_theme_diagnostics)
        help_menu.addAction(theme_diag)
        about_action = QAction("Über …", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def _validate_installation(self) -> None:
        missing = self.engine.validate_sources()
        if missing:
            QMessageBox.critical(self, "Satzdateien fehlen", "Folgende Dateien fehlen:\n" + "\n".join(missing))
            self.generate_button.setEnabled(False)
        if not SOUND_FILE.is_file():
            self.background_check.setChecked(False)
            self.background_check.setEnabled(False)
            self.status_label.setText("Hintergrundsound fehlt; Story-Generierung und TTS bleiben verfügbar.")
        if not self.theme_manager.themes:
            QApplication.instance().setStyleSheet(emergency_stylesheet(self._ui_scale))
            self.status_label.setText("Keine gültigen externen Themes gefunden; Notfall-Theme ist aktiv.")

    def toggle_story_panel(self) -> None:
        showing = self.tabs.isVisible()
        if showing:
            self.tabs.hide()
            self.toggle_story_button.setText("Story / Log einblenden  >")
            self.resize(BASE_COMPACT_WIDTH, self.height())
        else:
            self.tabs.show()
            self.toggle_story_button.setText("<  Story / Log ausblenden")
            self.resize(max(1020, self.width() + 630), max(650, self.height()))

    def _load_qt_voices(self) -> None:
        entries: list[dict] = []
        self.qt_voice_objects.clear()
        for index, voice in enumerate(self.qt_tts.availableVoices()):
            locale = voice.locale().name()
            voice_id = f"qt:{index}:{voice.name()}:{locale}"
            self.qt_voice_objects[voice_id] = voice
            entries.append({
                "backend": "qt",
                "id": voice_id,
                "name": voice.name(),
                "locale": locale,
                "description": "Qt TextToSpeech",
                "gender": str(voice.gender()),
            })
        self.voice_catalogs["qt"] = entries
        self._rebuild_voice_combo()

    def refresh_voices(self) -> None:
        self.voice_diagnostics.clear()
        self.voice_count_label.setText("Stimmen werden neu eingelesen …")
        self._load_qt_voices()
        self.voice_catalogs["winrt"] = []
        self.voice_catalogs["sapi"] = []
        self._rebuild_voice_combo()
        self.winrt_service.refresh_voices()
        self.sapi_service.refresh_voices()

    def _winrt_voices_ready(self, voices: list[dict]) -> None:
        self.voice_catalogs["winrt"] = voices
        self._rebuild_voice_combo()

    def _sapi_voices_ready(self, voices: list[dict]) -> None:
        self.voice_catalogs["sapi"] = voices
        self._rebuild_voice_combo()

    def _rebuild_voice_combo(self) -> None:
        current = self.voice_combo.currentData() if self.voice_combo.count() else None
        current_key = (current or {}).get("backend", "") + "|" + (current or {}).get("id", "")
        self.voice_combo.blockSignals(True)
        self.voice_combo.clear()
        total = 0
        for backend in ("winrt", "sapi", "qt"):
            for entry in self.voice_catalogs[backend]:
                locale = f" — {entry['locale']}" if entry.get("locale") else ""
                self.voice_combo.addItem(f"{entry['name']}{locale} [{BACKEND_LABELS[backend]}]", entry)
                total += 1
        self.voice_combo.blockSignals(False)

        target_key = current_key or (self.saved_voice_backend + "|" + self.saved_voice_id)
        selected = -1
        if target_key != "|":
            for index in range(self.voice_combo.count()):
                entry = self.voice_combo.itemData(index)
                if entry and entry.get("backend", "") + "|" + entry.get("id", "") == target_key:
                    selected = index
                    break
        if selected < 0 and self.saved_voice_name:
            for index in range(self.voice_combo.count()):
                entry = self.voice_combo.itemData(index)
                if entry and entry.get("name") == self.saved_voice_name:
                    selected = index
                    break
        if selected < 0 and self.voice_combo.count():
            selected = 0
        if selected >= 0:
            self.voice_combo.setCurrentIndex(selected)
            self._voice_changed(selected)

        counts = [f"{BACKEND_LABELS[key]}: {len(self.voice_catalogs[key])}" for key in ("winrt", "sapi", "qt")]
        self.voice_count_label.setText(f"{total} Einträge — " + ", ".join(counts))
        self.execute_button.setEnabled(bool(self.result and total))

    def _voice_changed(self, index: int) -> None:
        if index < 0:
            return
        entry = self.voice_combo.itemData(index)
        if not entry:
            return
        if entry.get("backend") == "qt":
            voice = self.qt_voice_objects.get(entry.get("id", ""))
            if voice is not None:
                self.qt_tts.setVoice(voice)

    def _voice_service_error(self, message: str) -> None:
        if message not in self.voice_diagnostics:
            self.voice_diagnostics.append(message)
        self.status_label.setText(message)

    def show_voice_diagnostics(self) -> None:
        lines = [f"{APP_NAME} v{APP_VERSION}", "", "Gefundene Stimmen:"]
        for backend in ("winrt", "sapi", "qt"):
            lines.append(f"\n{BACKEND_LABELS[backend]} ({len(self.voice_catalogs[backend])})")
            for entry in self.voice_catalogs[backend]:
                locale = f" / {entry.get('locale')}" if entry.get("locale") else ""
                lines.append(f"  • {entry.get('name')}{locale}")
        if self.voice_diagnostics:
            lines.append("\nHinweise/Fehler:")
            lines.extend(f"  • {item}" for item in self.voice_diagnostics)
        QMessageBox.information(self, "TTS-Stimmendiagnose", "\n".join(lines))

    def _load_settings(self) -> None:
        try:
            settings = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            settings = {}
        self.rate_slider.setValue(int(settings.get("rate", 0)))
        self.voice_volume.setValue(int(settings.get("voice_volume", 100)))
        self.background_volume.setValue(int(settings.get("background_volume", 18)))
        self.background_check.setChecked(bool(settings.get("background", True)) and SOUND_FILE.is_file())
        self.write_log.setChecked(bool(settings.get("write_log", True)))
        self.legacy_umlauts.setChecked(bool(settings.get("legacy_umlauts", True)))
        self.ignore_blanks.setChecked(bool(settings.get("ignore_blanks", True)))
        self.saved_voice_backend = str(settings.get("voice_backend", ""))
        self.saved_voice_id = str(settings.get("voice_id", ""))
        self.saved_voice_name = str(settings.get("voice_name", ""))
        theme = str(settings.get("theme", "Legacy Beige"))
        if theme in self.theme_manager.themes:
            self.theme_combo.setCurrentText(theme)
        elif self.theme_combo.count():
            self.theme_combo.setCurrentIndex(0)
        self.apply_theme(self.theme_combo.currentText())
        self._rebuild_voice_combo()

    def _save_settings(self) -> None:
        entry = self.voice_combo.currentData() or {}
        settings = {
            "app_version": APP_VERSION,
            "rate": self.rate_slider.value(),
            "voice_volume": self.voice_volume.value(),
            "background_volume": self.background_volume.value(),
            "background": self.background_check.isChecked(),
            "write_log": self.write_log.isChecked(),
            "legacy_umlauts": self.legacy_umlauts.isChecked(),
            "ignore_blanks": self.ignore_blanks.isChecked(),
            "theme": self.theme_combo.currentText(),
            "voice_backend": entry.get("backend", ""),
            "voice_id": entry.get("id", ""),
            "voice_name": entry.get("name", ""),
        }
        try:
            SETTINGS_FILE.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    def _populate_theme_combo(self) -> None:
        self.theme_combo.blockSignals(True)
        self.theme_combo.clear()
        self.theme_combo.addItems(self.theme_manager.names())
        self.theme_combo.blockSignals(False)

    def apply_theme(self, name: str) -> None:
        theme = self.theme_manager.get(name)
        stylesheet = theme.stylesheet(self._ui_scale) if theme else emergency_stylesheet(self._ui_scale)
        QApplication.instance().setStyleSheet(stylesheet)

    def reload_themes(self) -> None:
        current = self.theme_combo.currentText()
        self.theme_manager.load()
        self._populate_theme_combo()
        if current in self.theme_manager.themes:
            self.theme_combo.setCurrentText(current)
        elif "Legacy Beige" in self.theme_manager.themes:
            self.theme_combo.setCurrentText("Legacy Beige")
        elif self.theme_combo.count():
            self.theme_combo.setCurrentIndex(0)
        self.apply_theme(self.theme_combo.currentText())
        valid = len(self.theme_manager.themes)
        invalid = len(self.theme_manager.errors)
        self.status_label.setText(f"Themes neu geladen: {valid} gültig, {invalid} abgelehnt.")

    def show_theme_diagnostics(self) -> None:
        lines = [f"Externe Theme-Dateien: {len(self.theme_manager.themes)} gültig."]
        for theme in self.theme_manager.themes.values():
            lines.append(f"  • {theme.name}: {theme.source.name}")
        if self.theme_manager.errors:
            lines.append("\nAbgelehnte Themes:")
            lines.extend(f"  • {error}" for error in self.theme_manager.errors)
        else:
            lines.append("\nAlle Themes haben die Kontrastprüfung bestanden.")
        QMessageBox.information(self, "Theme-Prüfung", "\n".join(lines))

    def generate_story(self) -> None:
        self.stop_playback()
        self.generate_button.setEnabled(False)
        self.execute_button.setEnabled(False)
        self.progress.setValue(0)
        seed = self.seed_spin.value() or None

        def on_progress(current: int, total: int, filename: str) -> None:
            self.progress.setValue(round(current * 100 / total))
            self.status_label.setText(f"Satzteil {current}/{total}: {filename}")
            QApplication.processEvents()

        try:
            self.result = self.engine.generate(
                seed,
                legacy_umlauts=self.legacy_umlauts.isChecked(),
                ignore_blank_lines=self.ignore_blanks.isChecked(),
                progress=on_progress,
            )
        except StoryEngineError as exc:
            QMessageBox.critical(self, "Generierungsfehler", str(exc))
            self.status_label.setText("Generierung fehlgeschlagen.")
            self.generate_button.setEnabled(True)
            return

        self.story_edit.setPlainText(self.result.display_story)
        self.current_log = self.result.build_log(APP_VERSION)
        self.log_edit.setPlainText(self.current_log)
        self.progress.setValue(100)
        hidden_note = " Mit ‚Story / Log einblenden‘ kann der Text angezeigt werden." if not self.tabs.isVisible() else ""
        self.status_label.setText(f"Sektor-Sprung berechnet. Seed: {self.result.seed}.{hidden_note}")
        self.generate_button.setEnabled(True)
        self.execute_button.setEnabled(self.voice_combo.count() > 0)
        if self.write_log.isChecked():
            self._write_generation_log()

    def _write_generation_log(self) -> None:
        if not self.result:
            return
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            stamp = self.result.created_at.strftime("%Y%m%d_%H%M%S")
            path = LOG_DIR / f"scifi-generator_v{APP_VERSION}_{stamp}_seed-{self.result.seed}.log"
            path.write_text(self.current_log, encoding="utf-8-sig")
            self.status_label.setText(self.status_label.text() + f" Log: {path.name}")
        except OSError as exc:
            QMessageBox.warning(self, "Log konnte nicht gespeichert werden", str(exc))

    def execute_jump(self) -> None:
        story = self.story_edit.toPlainText().strip()
        if not story:
            self._speak("Ernsthaft? Sie müssen zunächst einen Sektor-Sprung berechnen.", with_background=False)
            return
        try:
            activation = self.engine.random_line("jumpdrive_activated.ini", ignore_blank_lines=True)
            if self.legacy_umlauts.isChecked():
                activation = self.engine.legacy_umlaut_conversion(activation)
        except StoryEngineError:
            activation = "Sprungantrieb aktiviert."
        self._speak(f"{activation}\n{story}", with_background=self.background_check.isChecked())

    def speak_selection(self) -> None:
        cursor = self.story_edit.textCursor()
        text = cursor.selectedText().replace("\u2029", "\n").strip()
        if not text:
            text = self.story_edit.toPlainText().strip()
        if not text:
            self.status_label.setText("Kein Text zum Vorlesen vorhanden.")
            return
        self._speak(text, with_background=False)

    def _speak(self, text: str, *, with_background: bool) -> None:
        entry = self.voice_combo.currentData()
        if not entry:
            QMessageBox.warning(self, "Keine Stimme", "Es wurde keine verwendbare TTS-Stimme gefunden.")
            return
        self.stop_playback()
        self.playback_active = True
        self.active_backend = entry["backend"]
        self._pending_background = with_background
        self.stop_button.setEnabled(True)
        self.pause_button.setText("Pause")
        self.narration_audio.setVolume(1.0)
        self.background_audio.setVolume(self.background_volume.value() / 100.0)

        if self.active_backend == "winrt":
            self.pause_button.setEnabled(False)
            self.status_label.setText("Windows-Stimme bereitet die Story vor …")
            self.winrt_service.synthesize(text, entry["id"], self.rate_slider.value(), self.voice_volume.value())
        elif self.active_backend == "sapi":
            self.pause_button.setEnabled(True)
            if with_background and SOUND_FILE.is_file():
                self._start_background()
            self.sapi_service.speak(text, entry["id"], self.rate_slider.value(), self.voice_volume.value())
        else:
            voice = self.qt_voice_objects.get(entry["id"])
            if voice is not None:
                self.qt_tts.setVoice(voice)
            self.qt_tts.setRate(self.rate_slider.value() / 10.0)
            self.qt_tts.setVolume(self.voice_volume.value() / 100.0)
            self.pause_button.setEnabled(True)
            if with_background and SOUND_FILE.is_file():
                self._start_background()
            self.qt_tts.say(text)

    def _winrt_synthesis_ready(self, filename: str) -> None:
        if not self.playback_active or self.active_backend != "winrt":
            Path(filename).unlink(missing_ok=True)
            return
        self._winrt_audio_file = filename
        self.narration_player.setSource(QUrl.fromLocalFile(filename))
        if self._pending_background and SOUND_FILE.is_file():
            self._start_background()
        self.pause_button.setEnabled(True)
        self.narration_player.play()
        self._handle_speech_state("winrt", "speaking")

    def _start_background(self) -> None:
        self.background_player.setPosition(0)
        self.background_player.play()

    def pause_or_resume(self) -> None:
        if not self.playback_active or not self.active_backend:
            return
        if self.speech_state == "speaking":
            if self.active_backend == "winrt":
                self.narration_player.pause()
                self._handle_speech_state("winrt", "paused")
            elif self.active_backend == "sapi":
                self.sapi_service.pause()
            else:
                self.qt_tts.pause()
            self.background_player.pause()
        elif self.speech_state == "paused":
            if self.active_backend == "winrt":
                self.narration_player.play()
                self._handle_speech_state("winrt", "speaking")
            elif self.active_backend == "sapi":
                self.sapi_service.resume()
            else:
                self.qt_tts.resume()
            if self._pending_background and SOUND_FILE.is_file():
                self.background_player.play()

    def stop_playback(self) -> None:
        was_active = self.playback_active
        self.playback_active = False
        self.active_backend = None
        self.speech_state = "ready"
        self.qt_tts.stop()
        self.sapi_service.stop()
        self.winrt_service.cancel()
        self.narration_player.stop()
        self.narration_player.setSource(QUrl())
        self.background_player.stop()
        self.winrt_service.release_output()
        if self._winrt_audio_file:
            Path(self._winrt_audio_file).unlink(missing_ok=True)
            self._winrt_audio_file = None
        self.pause_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.pause_button.setText("Pause")
        if was_active:
            self.status_label.setText("Wiedergabe gestoppt.")

    def _qt_tts_state_changed(self, state: QTextToSpeech.State) -> None:
        mapping = {
            QTextToSpeech.State.Speaking: "speaking",
            QTextToSpeech.State.Paused: "paused",
            QTextToSpeech.State.Ready: "ready",
            QTextToSpeech.State.Error: "error",
        }
        self._handle_speech_state("qt", mapping.get(state, "ready"))

    def _narration_media_status_changed(self, status: QMediaPlayer.MediaStatus) -> None:
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._handle_speech_state("winrt", "ready")
        elif status == QMediaPlayer.MediaStatus.InvalidMedia and self.active_backend == "winrt":
            self._handle_speech_state("winrt", "error")

    def _handle_speech_state(self, backend: str, state: str) -> None:
        if backend != self.active_backend:
            return
        self.speech_state = state
        if state == "preparing":
            self.pause_button.setEnabled(False)
            self.status_label.setText("Windows-Stimme bereitet die Story vor …")
        elif state == "speaking":
            self.pause_button.setEnabled(True)
            self.pause_button.setText("Pause")
            self.status_label.setText("Story wird vorgelesen …")
        elif state == "paused":
            self.pause_button.setText("Fortsetzen")
            self.status_label.setText("Wiedergabe pausiert.")
        elif state == "ready" and self.playback_active:
            self._finish_playback()
        elif state == "error":
            self.background_player.stop()
            self.playback_active = False
            self.pause_button.setEnabled(False)
            self.stop_button.setEnabled(False)
            self.status_label.setText("Fehler bei der Sprachausgabe. Details stehen in der TTS-Stimmendiagnose.")

    def _finish_playback(self) -> None:
        self.background_player.stop()
        self.narration_player.stop()
        self.narration_player.setSource(QUrl())
        self.winrt_service.release_output()
        if self._winrt_audio_file:
            Path(self._winrt_audio_file).unlink(missing_ok=True)
            self._winrt_audio_file = None
        self.playback_active = False
        self.active_backend = None
        self.speech_state = "ready"
        self.pause_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.pause_button.setText("Pause")
        self.status_label.setText("Sprung abgeschlossen. Story kann erneut abgespielt werden.")

    def save_story(self) -> None:
        story = self.story_edit.toPlainText()
        if not story.strip():
            QMessageBox.information(self, "Keine Story", "Es gibt noch keine Story zum Speichern.")
            return
        default = BASE_DIR / f"scifi_story_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        filename, _ = QFileDialog.getSaveFileName(
            self, "Story speichern", str(default),
            "Textdatei (*.txt);;Markdown (*.md);;Alle Dateien (*)",
        )
        if not filename:
            return
        try:
            Path(filename).write_text(story, encoding="utf-8-sig")
            self.status_label.setText(f"Story gespeichert: {filename}")
        except OSError as exc:
            QMessageBox.critical(self, "Speicherfehler", str(exc))

    def clear_story(self) -> None:
        self.stop_playback()
        self.story_edit.clear()
        self.log_edit.clear()
        self.result = None
        self.current_log = ""
        self.execute_button.setEnabled(False)
        self.progress.setValue(0)
        self.status_label.setText("Text gelöscht. Bitte nächsten Sektor-Sprung berechnen.")

    @staticmethod
    def _open_path(path: Path) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))

    def show_about(self) -> None:
        QMessageBox.about(
            self,
            f"Über {APP_NAME}",
            f"<b>{APP_NAME} v{APP_VERSION}</b><br><br>"
            "Python-Neuauflage des früheren VB.NET-Zufallsgeschichten-Generators.<br>"
            "Originalautor und Textbestände: zeittresor.<br><br>"
            "Die Themes liegen als externe JSON-Dateien im Ordner <code>themes</code> und werden "
            "vor der Verwendung automatisch auf ausreichenden Textkontrast geprüft.<br><br>"
            "Die Stimmensuche kombiniert Windows OneCore/WinRT, native Windows-SAPI und Qt.<br><br>"
            "Der enthaltene Hintergrundklang ist eine neu erzeugte, generische Sci-Fi-Atmosphäre; "
            "es sind keine Star-Trek-Audiodateien enthalten.<br><br>"
            "Original source / updates: github.com/zeittresor",
        )

    def closeEvent(self, event) -> None:
        self._save_settings()
        self.stop_playback()
        self.sapi_service.shutdown()
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
