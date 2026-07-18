from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QObject, Signal, QThread, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QFont, QIcon, QResizeEvent
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtTextToSpeech import QTextToSpeech
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QFrame,
    QGroupBox, QHBoxLayout, QLabel, QLayout, QLineEdit, QMainWindow, QMessageBox,
    QProgressBar, QProgressDialog, QPushButton, QScrollArea, QSizePolicy, QSlider, QSpinBox,
    QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from audio_export import AudioExportRequest, AudioExportWorker, find_ffmpeg
from story_engine import APP_VERSION, GenerationResult, StoryEngine, StoryEngineError
from storyboard_generator import StoryboardScene, generate_storyboard, render_storyboard_text
from media_package_generator import MediaPackageSettings, build_media_manifest, render_media_package_text
from ollama_client import OllamaClient, OllamaClientError
from prompt_profile_manager import PromptProfile, PromptProfileManager
from theme_manager import ThemeManager
from tts_services import SapiTtsService, WinRtTtsService

APP_NAME = "SciFi-Generator"
BASE_DIR = Path(__file__).resolve().parent
VARS_DIR = BASE_DIR / "data" / "vars"
SEQUENCE_FILE = BASE_DIR / "sequence_legacy.json"
SOUND_FILE = BASE_DIR / "data" / "sounds" / "background.wav"
LOG_DIR = BASE_DIR / "logs"
THEME_DIR = BASE_DIR / "themes"
PROMPT_PROFILE_DIR = BASE_DIR / "prompt_profiles"
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
QTextEdit, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{ background: #0F1115; color: #FFFFFF; border: 1px solid #788493; }}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{ min-height: {px(26)}px; padding: {px(2)}px {px(5)}px; }}
QPushButton {{ background: #343941; color: #FFFFFF; border: 1px solid #788493; padding: {px(5)}px {px(9)}px; min-height: {px(28)}px; }}
QPushButton:hover {{ background: #48505B; }}
QGroupBox {{ border: 1px solid #788493; margin-top: {px(9)}px; padding-top: {px(9)}px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: {px(8)}px; padding: 0 {px(4)}px; }}
QScrollBar:vertical {{ width: {px(14)}px; }}
QScrollBar:horizontal {{ height: {px(14)}px; }}
"""


class StoryboardGenerationWorker(QObject):
    progress = Signal(int, str)
    finished = Signal(object, str, str, str)
    error = Signal(str)

    def __init__(
        self,
        story_text: str,
        local_scenes: list[StoryboardScene],
        use_ollama: bool,
        model_name: str,
        target_name: str,
        target_mode: str,
        output_kind: str,
    ):
        super().__init__()
        self.story_text = story_text
        self.local_scenes = local_scenes
        self.use_ollama = use_ollama
        self.model_name = model_name
        self.target_name = target_name
        self.target_mode = target_mode
        self.output_kind = output_kind
        self._canceled = False

    def cancel(self) -> None:
        self._canceled = True

    def run(self) -> None:
        if self._canceled:
            return
        self.progress.emit(15, "Szenen und Produktionsdaten werden vorbereitet …")
        scenes = self.local_scenes
        source = "Lokal"
        model = ""
        note = ""
        if self.use_ollama and self.model_name.strip():
            self.progress.emit(45, "Ollama verfeinert die Bild-Prompts …")
            try:
                client = OllamaClient()
                scenes = client.generate_storyboard_prompts(
                    self.story_text,
                    self.local_scenes,
                    self.model_name.strip(),
                    target_name=self.target_name,
                    target_mode=self.target_mode,
                )
                source = "Ollama"
                model = self.model_name.strip()
            except OllamaClientError as exc:
                note = str(exc)
                source = "Lokal"
                model = ""
        if self._canceled:
            return
        done_message = "Gesamtpaket-Prompt bereit." if self.output_kind.startswith("Gesamtpaket") else "Bild-Prompts bereit."
        self.progress.emit(100, done_message)
        self.finished.emit(scenes, source, model, note)



class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.engine = StoryEngine(VARS_DIR, SEQUENCE_FILE)
        self.result: GenerationResult | None = None
        self.current_log = ""
        self.playback_active = False
        self.active_backend: str | None = None
        self.speech_state = "ready"
        self.playback_purpose = "generic"
        self.story_completed = False
        self.current_activation_text = ""
        self._pending_background = False
        self._winrt_audio_file: str | None = None
        self.voice_catalogs: dict[str, list[dict]] = {"winrt": [], "sapi": [], "qt": []}
        self.qt_voice_objects: dict[str, object] = {}
        self.voice_diagnostics: list[str] = []
        self.saved_voice_backend = ""
        self.saved_voice_id = ""
        self.saved_voice_name = ""
        self._export_thread: QThread | None = None
        self._export_worker: AudioExportWorker | None = None
        self._export_dialog: QProgressDialog | None = None
        self.storyboard_scenes: list[StoryboardScene] = []
        self.storyboard_text = ""
        self.ollama_client = OllamaClient()
        self._storyboard_thread: QThread | None = None
        self._storyboard_worker: StoryboardGenerationWorker | None = None
        self._storyboard_dialog: QProgressDialog | None = None
        self._storyboard_profile_name = "ChatGPT"
        self._storyboard_custom_target = ""
        self._storyboard_output_kind = "Bildserie"
        self._storyboard_transition_seconds = 0.8

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
        self.prompt_profile_manager = PromptProfileManager(PROMPT_PROFILE_DIR)
        self.prompt_profile_manager.load()

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
        QTimer.singleShot(150, self.refresh_ollama_models)

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
        self.prompts_edit = QTextEdit()
        self.prompts_edit.setReadOnly(True)
        self.prompts_edit.setAcceptRichText(False)
        self.prompts_edit.setPlaceholderText("Hier können optionale Bild-Prompts oder ein Gesamtpaket-Produktionsauftrag angezeigt werden …")
        self.tabs.addTab(self.story_edit, "Story")
        self.tabs.addTab(self.log_edit, "Auswahlprotokoll")
        self.tabs.addTab(self.prompts_edit, "Prompts / Produktion")
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
        self.execute_button.setToolTip(
            "Liest die zuvor berechnete Geschichte einmal vollständig vor. "
            "Für eine weitere Erzählung muss danach ein neuer Sektor-Sprung berechnet werden."
        )
        self.execute_button.clicked.connect(self.execute_jump)
        self.execute_button.setEnabled(False)
        self.toggle_story_button = QPushButton("Story / Log / Prompts einblenden  >")
        self.toggle_story_button.setToolTip("Blendet die berechnete Story, das Auswahlprotokoll und optionale Bild-Prompts ein oder aus.")
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

        self.audio_export_button = QPushButton("Story als Audiodatei speichern …")
        self.audio_export_button.setToolTip(
            "Erzeugt eine WAV-Datei aus der aktuellen Story und mischt auf Wunsch "
            "die eingestellte Brückenatmosphäre hinzu. MP3 wird angeboten, wenn FFmpeg gefunden wurde."
        )
        self.audio_export_button.clicked.connect(self.save_story_audio)
        self.audio_export_button.setEnabled(False)
        speech_layout.addWidget(self.audio_export_button)
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

        storyboard_group = QGroupBox("Bildserie / Storyboard")
        storyboard_layout = QVBoxLayout(storyboard_group)
        storyboard_form = QFormLayout()
        storyboard_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        storyboard_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.output_kind_combo = QComboBox()
        self.output_kind_combo.addItems([
            "Bildserie",
            "Gesamtpaket (Bilder + Audio + Video)",
        ])
        self.output_kind_combo.currentTextChanged.connect(self._update_target_ai_controls)
        storyboard_form.addRow("Ausgabeart:", self.output_kind_combo)
        self.target_ai_combo = QComboBox()
        self.target_ai_combo.addItems(self.prompt_profile_manager.names())
        self.target_ai_combo.currentTextChanged.connect(self._update_target_ai_controls)
        storyboard_form.addRow("Zielsystem / LLM:", self.target_ai_combo)
        self.custom_target_edit = QLineEdit()
        self.custom_target_edit.setPlaceholderText("Name der anderen Bildsynthese-KI")
        self.custom_target_edit.setToolTip("Wird nur beim Zielprofil 'Andere' verwendet.")
        self.custom_target_edit.textChanged.connect(self._update_target_ai_controls)
        storyboard_form.addRow("Andere KI:", self.custom_target_edit)
        self.custom_target_label = storyboard_form.labelForField(self.custom_target_edit)
        self.prompt_mode_combo = QComboBox()
        self.prompt_mode_combo.addItems(["Lokal (regelbasiert)", "Ollama (lokales Modell)"])
        self.prompt_mode_combo.currentIndexChanged.connect(self._update_storyboard_mode_controls)
        storyboard_form.addRow("Prompt-Verfeinerung:", self.prompt_mode_combo)
        self.scene_count_spin = QSpinBox()
        self.scene_count_spin.setRange(6, 10)
        self.scene_count_spin.setValue(8)
        storyboard_form.addRow("Schlüsselszenen:", self.scene_count_spin)
        self.transition_spin = QDoubleSpinBox()
        self.transition_spin.setRange(0.0, 5.0)
        self.transition_spin.setDecimals(1)
        self.transition_spin.setSingleStep(0.1)
        self.transition_spin.setValue(0.8)
        self.transition_spin.setSuffix(" s")
        self.transition_spin.setToolTip("Gewünschte Dauer der sanften Überblendung zwischen zwei Szenen im Gesamtpaket.")
        storyboard_form.addRow("Überblendung:", self.transition_spin)
        self.transition_label = storyboard_form.labelForField(self.transition_spin)
        self.ollama_model_combo = QComboBox()
        self.ollama_model_combo.setEditable(True)
        self.ollama_model_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.ollama_model_combo.setMinimumContentsLength(18)
        storyboard_form.addRow("Ollama-Modell:", self.ollama_model_combo)
        storyboard_layout.addLayout(storyboard_form)

        storyboard_button_row = QHBoxLayout()
        self.refresh_ollama_button = QPushButton("Modelle prüfen")
        self.refresh_ollama_button.setToolTip("Prüft, ob ein lokaler Ollama-Server läuft, und liest die verfügbaren Modelle ein.")
        self.refresh_ollama_button.clicked.connect(self.refresh_ollama_models)
        self.generate_prompts_button = QPushButton("Bild-Prompts erzeugen")
        self.generate_prompts_button.setToolTip("Erzeugt wahlweise einen Bildserien-Auftrag oder einen vollständigen Produktionsauftrag für Bilder, Szenen-Audio, Videozusammenschnitt und ZIP-Paket. Diese Texte werden nicht vorgelesen.")
        self.generate_prompts_button.clicked.connect(self.generate_storyboard_prompts)
        storyboard_button_row.addWidget(self.refresh_ollama_button)
        storyboard_button_row.addWidget(self.generate_prompts_button)
        storyboard_layout.addLayout(storyboard_button_row)

        storyboard_save_row = QHBoxLayout()
        self.save_prompts_button = QPushButton("Prompts speichern …")
        self.save_prompts_button.clicked.connect(self.save_storyboard_prompts)
        self.save_prompts_button.setEnabled(False)
        storyboard_save_row.addWidget(self.save_prompts_button)
        storyboard_layout.addLayout(storyboard_save_row)

        self.storyboard_info_label = QLabel("Optional: Bildserie oder vollständigen Produktionsauftrag lokal erzeugen und bei Bedarf über Ollama verfeinern.")
        self.storyboard_info_label.setWordWrap(True)
        storyboard_layout.addWidget(self.storyboard_info_label)
        right.addWidget(storyboard_group)

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
        self._update_storyboard_mode_controls()
        self._update_target_ai_controls()

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
        export_audio_action = QAction("Story als Audiodatei speichern …", self)
        export_audio_action.triggered.connect(self.save_story_audio)
        file_menu.addAction(export_audio_action)
        export_prompts_action = QAction("Prompts / Produktionsauftrag speichern …", self)
        export_prompts_action.triggered.connect(self.save_storyboard_prompts)
        file_menu.addAction(export_prompts_action)
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
        toggle_action = QAction("Story / Log / Prompts ein- oder ausblenden", self)
        toggle_action.triggered.connect(self.toggle_story_panel)
        view_menu.addAction(toggle_action)
        open_themes = QAction("Theme-Ordner öffnen", self)
        open_themes.triggered.connect(lambda: self._open_path(THEME_DIR))
        view_menu.addAction(open_themes)
        reload_themes = QAction("Themes neu laden", self)
        reload_themes.triggered.connect(self.reload_themes)
        view_menu.addAction(reload_themes)
        open_prompt_profiles = QAction("Prompt-Profilordner öffnen", self)
        open_prompt_profiles.triggered.connect(lambda: self._open_path(PROMPT_PROFILE_DIR))
        view_menu.addAction(open_prompt_profiles)
        reload_prompt_profiles = QAction("Prompt-Profile neu laden", self)
        reload_prompt_profiles.triggered.connect(self.reload_prompt_profiles)
        view_menu.addAction(reload_prompt_profiles)

        help_menu = self.menuBar().addMenu("Hilfe")
        ollama_diag = QAction("Ollama / Storyboard prüfen", self)
        ollama_diag.triggered.connect(self.show_ollama_diagnostics)
        help_menu.addAction(ollama_diag)
        voice_diag = QAction("TTS-Stimmendiagnose", self)
        voice_diag.triggered.connect(self.show_voice_diagnostics)
        help_menu.addAction(voice_diag)
        theme_diag = QAction("Theme-Prüfung", self)
        theme_diag.triggered.connect(self.show_theme_diagnostics)
        help_menu.addAction(theme_diag)
        prompt_profile_diag = QAction("Prompt-Profilprüfung", self)
        prompt_profile_diag.triggered.connect(self.show_prompt_profile_diagnostics)
        help_menu.addAction(prompt_profile_diag)
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
        if not self.prompt_profile_manager.profiles:
            self.generate_prompts_button.setEnabled(False)
            self.storyboard_info_label.setText(
                "Keine gültigen Ziel-KI-Promptprofile gefunden. Bitte den Ordner prompt_profiles prüfen."
            )

    def toggle_story_panel(self) -> None:
        showing = self.tabs.isVisible()
        if showing:
            self.tabs.hide()
            self.toggle_story_button.setText("Story / Log / Prompts einblenden  >")
            self.resize(BASE_COMPACT_WIDTH, self.height())
        else:
            self.tabs.show()
            self.toggle_story_button.setText("<  Story / Log / Prompts ausblenden")
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
        self.execute_button.setEnabled(bool(total) and not self.playback_active)
        self.audio_export_button.setEnabled(bool(self.result and total) and self._export_thread is None)

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
        self.prompt_mode_combo.setCurrentText(str(settings.get("storyboard_mode", "Lokal (regelbasiert)")))
        output_kind = str(settings.get("storyboard_output_kind", "Bildserie"))
        if self.output_kind_combo.findText(output_kind) >= 0:
            self.output_kind_combo.setCurrentText(output_kind)
        self.transition_spin.setValue(float(settings.get("storyboard_transition_seconds", 0.8)))
        target_ai = str(settings.get("storyboard_target_ai", "ChatGPT"))
        if target_ai in self.prompt_profile_manager.profiles:
            self.target_ai_combo.setCurrentText(target_ai)
        elif self.target_ai_combo.count():
            self.target_ai_combo.setCurrentIndex(0)
        self.custom_target_edit.setText(str(settings.get("storyboard_custom_target", "")))
        self.scene_count_spin.setValue(int(settings.get("storyboard_scene_count", 8)))
        saved_ollama_model = str(settings.get("ollama_model", ""))
        if saved_ollama_model:
            self.ollama_model_combo.addItem(saved_ollama_model)
            self.ollama_model_combo.setCurrentText(saved_ollama_model)
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
            "storyboard_mode": self.prompt_mode_combo.currentText(),
            "storyboard_output_kind": self.output_kind_combo.currentText(),
            "storyboard_transition_seconds": self.transition_spin.value(),
            "storyboard_target_ai": self.target_ai_combo.currentText(),
            "storyboard_custom_target": self.custom_target_edit.text().strip(),
            "storyboard_scene_count": self.scene_count_spin.value(),
            "ollama_model": self.ollama_model_combo.currentText().strip(),
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

    def _selected_prompt_profile(self) -> PromptProfile | None:
        return self.prompt_profile_manager.get(self.target_ai_combo.currentText())

    def _populate_target_ai_combo(self, preferred: str = "") -> None:
        current = preferred or self.target_ai_combo.currentText()
        self.target_ai_combo.blockSignals(True)
        self.target_ai_combo.clear()
        self.target_ai_combo.addItems(self.prompt_profile_manager.names())
        if current in self.prompt_profile_manager.profiles:
            self.target_ai_combo.setCurrentText(current)
        elif "ChatGPT" in self.prompt_profile_manager.profiles:
            self.target_ai_combo.setCurrentText("ChatGPT")
        elif self.target_ai_combo.count():
            self.target_ai_combo.setCurrentIndex(0)
        self.target_ai_combo.blockSignals(False)
        self._update_target_ai_controls()

    def reload_prompt_profiles(self) -> None:
        current = self.target_ai_combo.currentText()
        self.prompt_profile_manager.load()
        self._populate_target_ai_combo(current)
        valid = len(self.prompt_profile_manager.profiles)
        invalid = len(self.prompt_profile_manager.errors)
        self.generate_prompts_button.setEnabled(valid > 0 and self._storyboard_thread is None)
        self.status_label.setText(
            f"Prompt-Profile neu geladen: {valid} gültig, {invalid} abgelehnt."
        )

    def show_prompt_profile_diagnostics(self) -> None:
        lines = [f"Externe Ziel-KI-Promptprofile: {len(self.prompt_profile_manager.profiles)} gültig."]
        for profile in self.prompt_profile_manager.profiles.values():
            lines.append(f"  • {profile.name} [{profile.mode}]: {profile.source.name}")
        if self.prompt_profile_manager.errors:
            lines.append("\nAbgelehnte Prompt-Profile:")
            lines.extend(f"  • {error}" for error in self.prompt_profile_manager.errors)
        else:
            lines.append("\nAlle Prompt-Profile wurden erfolgreich geladen.")
        QMessageBox.information(self, "Prompt-Profilprüfung", "\n".join(lines))

    def generate_story(self) -> None:
        self.stop_playback()
        self.story_completed = False
        self.current_activation_text = ""
        self.storyboard_scenes = []
        self.storyboard_text = ""
        self.prompts_edit.clear()
        self.save_prompts_button.setEnabled(False)
        self.generate_button.setEnabled(False)
        self.execute_button.setEnabled(False)
        self.audio_export_button.setEnabled(False)
        self.save_prompts_button.setEnabled(False)
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
        self.audio_export_button.setEnabled(self.voice_combo.count() > 0)
        self.storyboard_info_label.setText(
            "Optional: Bild-Prompts oder ein vollständiger Gesamtpaket-Produktionsauftrag können jetzt erzeugt und über Ollama verfeinert werden."
        )
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

    def _random_notice(self, filename: str, fallback: str) -> str:
        try:
            notice = self.engine.random_line(filename, ignore_blank_lines=True)
            if self.legacy_umlauts.isChecked():
                notice = self.engine.legacy_umlaut_conversion(notice)
            return notice
        except StoryEngineError:
            return fallback

    def _current_narration_text(self) -> str:
        story = self.story_edit.toPlainText().strip()
        if not story:
            return ""
        if not self.current_activation_text:
            try:
                activation = self.engine.random_line("jumpdrive_activated.ini", ignore_blank_lines=True)
                if self.legacy_umlauts.isChecked():
                    activation = self.engine.legacy_umlaut_conversion(activation)
            except StoryEngineError:
                activation = "Sprungantrieb aktiviert."
            self.current_activation_text = activation
        return f"{self.current_activation_text}\n{story}"

    def execute_jump(self) -> None:
        if self.playback_active:
            return
        if not self.result or not self.story_edit.toPlainText().strip():
            notice = self._random_notice(
                "jump_missing_story.ini",
                "Ernsthaft? Sie müssen zuerst einen Sektor-Sprung berechnen.",
            )
            self._speak(notice, with_background=False, purpose="notice")
            return
        if self.story_completed:
            notice = self._random_notice(
                "jump_story_already_used.ini",
                "Nein. Diesen Sektor-Sprung haben wir bereits durchgeführt. Berechnen Sie bitte einen neuen.",
            )
            self._speak(notice, with_background=False, purpose="notice")
            return
        narration = self._current_narration_text()
        self._speak(
            narration,
            with_background=self.background_check.isChecked(),
            purpose="jump",
        )

    def speak_selection(self) -> None:
        cursor = self.story_edit.textCursor()
        text = cursor.selectedText().replace("\u2029", "\n").strip()
        if not text:
            text = self.story_edit.toPlainText().strip()
        if not text:
            self.status_label.setText("Kein Text zum Vorlesen vorhanden.")
            return
        self._speak(text, with_background=False, purpose="selection")

    def _speak(self, text: str, *, with_background: bool, purpose: str = "generic") -> None:
        entry = self.voice_combo.currentData()
        if not entry:
            QMessageBox.warning(self, "Keine Stimme", "Es wurde keine verwendbare TTS-Stimme gefunden.")
            return
        self.stop_playback()
        self.playback_active = True
        self.playback_purpose = purpose
        self.active_backend = entry["backend"]
        self._pending_background = with_background
        self.execute_button.setEnabled(False)
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
        stopped_purpose = self.playback_purpose
        self.playback_active = False
        self.playback_purpose = "generic"
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
        self.execute_button.setEnabled(self.voice_combo.count() > 0)
        if was_active:
            if stopped_purpose == "jump" and not self.story_completed:
                self.status_label.setText("Wiedergabe gestoppt. Der aktuelle Sprung kann erneut durchgeführt werden.")
            else:
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
            self.playback_purpose = "generic"
            self.pause_button.setEnabled(False)
            self.stop_button.setEnabled(False)
            self.execute_button.setEnabled(self.voice_combo.count() > 0)
            self.status_label.setText("Fehler bei der Sprachausgabe. Details stehen in der TTS-Stimmendiagnose.")

    def _finish_playback(self) -> None:
        completed_purpose = self.playback_purpose
        self.background_player.stop()
        self.narration_player.stop()
        self.narration_player.setSource(QUrl())
        self.winrt_service.release_output()
        if self._winrt_audio_file:
            Path(self._winrt_audio_file).unlink(missing_ok=True)
            self._winrt_audio_file = None
        self.playback_active = False
        self.playback_purpose = "generic"
        self.active_backend = None
        self.speech_state = "ready"
        self.pause_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.pause_button.setText("Pause")
        self.execute_button.setEnabled(self.voice_combo.count() > 0)
        if completed_purpose == "jump":
            self.story_completed = True
            self.status_label.setText(
                "Sprung abgeschlossen. Für die nächste Erzählung muss ein neuer Sektor-Sprung berechnet werden."
            )
        elif completed_purpose == "notice":
            self.status_label.setText("Bitte zunächst einen neuen Sektor-Sprung berechnen.")
        else:
            self.status_label.setText("Wiedergabe abgeschlossen.")

    def _resolve_audio_export_voice(self, selected: dict) -> dict | None:
        backend = selected.get("backend", "")
        if backend in {"winrt", "sapi"}:
            return selected
        selected_name = " ".join(str(selected.get("name", "")).lower().split())
        selected_locale = str(selected.get("locale", "")).lower()
        for candidate_backend in ("winrt", "sapi"):
            candidates = self.voice_catalogs.get(candidate_backend, [])
            for candidate in candidates:
                candidate_name = " ".join(str(candidate.get("name", "")).lower().split())
                candidate_locale = str(candidate.get("locale", "")).lower()
                if candidate_name == selected_name and (
                    not selected_locale or not candidate_locale or selected_locale == candidate_locale
                ):
                    return candidate
        return None

    def save_story_audio(self) -> None:
        if self._export_thread is not None:
            self.status_label.setText("Ein Audioexport läuft bereits.")
            return
        if not self.result or not self.story_edit.toPlainText().strip():
            QMessageBox.information(
                self,
                "Keine berechnete Story",
                "Berechnen Sie zuerst einen Sektor-Sprung, bevor Sie eine Audiodatei erzeugen.",
            )
            return
        selected = self.voice_combo.currentData() or {}
        export_voice = self._resolve_audio_export_voice(selected)
        if not export_voice:
            QMessageBox.warning(
                self,
                "Stimme nicht exportierbar",
                "Die ausgewählte Qt-Stimme kann nicht direkt in eine Audiodatei geschrieben werden "
                "und es wurde keine gleichnamige Windows-OneCore/WinRT- oder SAPI-Stimme gefunden. "
                "Bitte wählen Sie für den Export eine Windows-Stimme aus.",
            )
            return

        ffmpeg_path = find_ffmpeg(TOOLS_DIR)
        filters = "WAV-Audiodatei (*.wav)"
        if ffmpeg_path:
            filters += ";;MP3-Audiodatei (*.mp3)"
        default = BASE_DIR / f"scifi_story_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
        filename, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Story als Audiodatei speichern",
            str(default),
            filters,
        )
        if not filename:
            return
        output_path = Path(filename)
        if not output_path.suffix:
            output_path = output_path.with_suffix(".mp3" if "MP3" in selected_filter else ".wav")
        if output_path.suffix.lower() not in {".wav", ".mp3"}:
            output_path = output_path.with_suffix(".wav")

        narration = self._current_narration_text()
        background_path = (
            SOUND_FILE
            if self.background_check.isChecked() and SOUND_FILE.is_file()
            else None
        )
        request = AudioExportRequest(
            text=narration,
            backend=str(export_voice.get("backend", "")),
            voice_id=str(export_voice.get("id", "")),
            rate=self.rate_slider.value(),
            voice_volume=self.voice_volume.value(),
            background_path=background_path,
            background_volume=self.background_volume.value(),
            output_path=output_path,
            tools_dir=TOOLS_DIR,
            temp_dir=TEMP_DIR,
            ffmpeg_path=ffmpeg_path,
        )

        dialog = QProgressDialog(
            "Audioexport wird vorbereitet …",
            "Abbrechen",
            0,
            100,
            self,
        )
        dialog.setWindowTitle(f"{APP_NAME} – Audioexport")
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.setMinimumDuration(0)
        dialog.setAutoClose(False)
        dialog.setAutoReset(False)
        dialog.setValue(0)

        thread = QThread(self)
        worker = AudioExportWorker(request)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._audio_export_progress)
        worker.finished.connect(self._audio_export_finished)
        worker.error.connect(self._audio_export_failed)
        worker.canceled.connect(self._audio_export_canceled)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        worker.canceled.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.error.connect(worker.deleteLater)
        worker.canceled.connect(worker.deleteLater)
        thread.finished.connect(self._audio_export_thread_finished)
        dialog.canceled.connect(self._cancel_audio_export)

        self._export_thread = thread
        self._export_worker = worker
        self._export_dialog = dialog
        self.audio_export_button.setEnabled(False)
        self.status_label.setText("Story wird als Audiodatei exportiert …")
        dialog.show()
        thread.start()

    def _audio_export_progress(self, value: int, message: str) -> None:
        if self._export_dialog is not None:
            self._export_dialog.setLabelText(message)
            self._export_dialog.setValue(value)
        self.status_label.setText(message)

    def _cancel_audio_export(self) -> None:
        if self._export_worker is not None:
            self.status_label.setText("Audioexport wird abgebrochen …")
            self._export_worker.cancel()

    def _audio_export_finished(self, filename: str) -> None:
        if self._export_dialog is not None:
            self._export_dialog.setValue(100)
            self._export_dialog.close()
        self.status_label.setText(f"Audiodatei gespeichert: {filename}")
        QMessageBox.information(
            self,
            "Audioexport abgeschlossen",
            f"Die Story wurde als Audiodatei gespeichert:\n{filename}",
        )

    def _audio_export_failed(self, message: str) -> None:
        if self._export_dialog is not None:
            self._export_dialog.close()
        self.status_label.setText("Audioexport fehlgeschlagen.")
        QMessageBox.critical(self, "Audioexport fehlgeschlagen", message)

    def _audio_export_canceled(self) -> None:
        if self._export_dialog is not None:
            self._export_dialog.close()
        self.status_label.setText("Audioexport abgebrochen.")

    def _audio_export_thread_finished(self) -> None:
        thread = self._export_thread
        self._export_thread = None
        self._export_worker = None
        self._export_dialog = None
        self.audio_export_button.setEnabled(bool(self.result and self.voice_combo.count()))
        if thread is not None:
            thread.deleteLater()

    def _update_target_ai_controls(self) -> None:
        profile = self._selected_prompt_profile()
        is_other = bool(profile and profile.profile_id == "other")
        self.custom_target_edit.setEnabled(is_other)
        self.custom_target_edit.setVisible(is_other)
        if self.custom_target_label is not None:
            self.custom_target_label.setVisible(is_other)

        is_package = self.output_kind_combo.currentText().startswith("Gesamtpaket")
        self.transition_spin.setVisible(is_package)
        self.transition_spin.setEnabled(is_package)
        if self.transition_label is not None:
            self.transition_label.setVisible(is_package)
        self.generate_prompts_button.setText(
            "Gesamtpaket-Prompt erzeugen" if is_package else "Bild-Prompts erzeugen"
        )
        self.save_prompts_button.setText(
            "Gesamtpaket-Prompt speichern …" if is_package else "Bild-Prompts speichern …"
        )

        target_name = self.custom_target_edit.text().strip() if is_other else (profile.name if profile else "unbekannt")
        if is_package and profile:
            hint = (
                f"Ziel: {target_name}. Die Ausgabe fordert eine vollständige illustrierte Audiogeschichte an: "
                "Szenenbilder, getrennte TTS-Audios, an die Audiodauer angepasste Bildabschnitte, sanfte Übergänge, "
                "fertiges Video und möglichst ein ZIP-Paket. Falls direkte Medienerzeugung fehlt, wird ein Offline-Skript verlangt."
            )
        elif profile and profile.is_diffusion:
            hint = (
                f"Ziel: {target_name}. Die Ausgabe enthält einen Workflow-Steuerblock, einzelne Positive Prompts "
                "und einen globalen Negative Prompt. Jede Szene muss separat erzeugt werden."
            )
        elif profile:
            hint = (
                f"Ziel: {target_name}. Die Ausgabe beginnt mit einem ausdrücklichen Bildserien-Arbeitsauftrag "
                "und enthält eine globale Serienbibel für konsistente Folgebilder."
            )
        else:
            hint = "Kein gültiges Ziel-KI-Profil ausgewählt."
        self.storyboard_info_label.setText(hint)

    def _update_storyboard_mode_controls(self) -> None:
        use_ollama = self.prompt_mode_combo.currentText().startswith("Ollama")
        self.ollama_model_combo.setEnabled(use_ollama)
        self.refresh_ollama_button.setEnabled(True)
        self._update_target_ai_controls()
        if use_ollama:
            self.storyboard_info_label.setText(
                self.storyboard_info_label.text()
                + " Die Szenenprompts werden zusätzlich von einem lokalen Ollama-Modell zielsystemspezifisch verfeinert."
            )

    def refresh_ollama_models(self) -> None:
        current = self.ollama_model_combo.currentText().strip()
        self.ollama_model_combo.blockSignals(True)
        self.ollama_model_combo.clear()
        try:
            models = self.ollama_client.list_models()
        except OllamaClientError as exc:
            if current:
                self.ollama_model_combo.addItem(current)
                self.ollama_model_combo.setCurrentText(current)
            self.storyboard_info_label.setText(
                "Ollama wurde nicht gefunden oder antwortet nicht. Lokale Bild-Prompts bleiben weiterhin verfügbar."
            )
            self.ollama_model_combo.blockSignals(False)
            return
        if not models:
            if current:
                self.ollama_model_combo.addItem(current)
                self.ollama_model_combo.setCurrentText(current)
            self.storyboard_info_label.setText("Ollama ist erreichbar, aber es wurden keine Modelle gemeldet.")
            self.ollama_model_combo.blockSignals(False)
            return
        self.ollama_model_combo.addItems(models)
        if current and current in models:
            self.ollama_model_combo.setCurrentText(current)
        self.ollama_model_combo.blockSignals(False)
        self.storyboard_info_label.setText(f"Ollama erreichbar: {len(models)} Modell(e) gefunden.")

    def show_ollama_diagnostics(self) -> None:
        try:
            models = self.ollama_client.list_models()
            lines = ["Ollama-Server: erreichbar", "", "Modelle:"]
            if models:
                lines.extend(f"  • {name}" for name in models)
            else:
                lines.append("  (keine Modelle gemeldet)")
        except OllamaClientError as exc:
            lines = ["Ollama-Server: nicht erreichbar", "", str(exc)]
        lines.extend(["", "Hinweis: Die Storyboard-Funktion arbeitet immer lokal.", "Wenn Ollama erreichbar ist, können die Bild-Prompts zusätzlich verfeinert werden."])
        QMessageBox.information(self, "Ollama / Storyboard prüfen", "\n".join(lines))

    def generate_storyboard_prompts(self) -> None:
        if self._storyboard_thread is not None:
            self.status_label.setText("Eine Bild-Prompt-Erzeugung läuft bereits.")
            return
        if not self.result or not self.story_edit.toPlainText().strip():
            QMessageBox.information(
                self,
                "Keine berechnete Story",
                "Berechnen Sie zuerst einen Sektor-Sprung, bevor Sie Bild-Prompts oder einen Produktionsauftrag erzeugen.",
            )
            return
        profile = self._selected_prompt_profile()
        if profile is None:
            QMessageBox.critical(
                self,
                "Kein Ziel-KI-Profil",
                "Es wurde kein gültiges Ziel-KI-Profil gefunden. Bitte die externen Dateien im Ordner prompt_profiles prüfen.",
            )
            return
        custom_target_name = self.custom_target_edit.text().strip() if profile.profile_id == "other" else ""
        target_name = custom_target_name or profile.name
        self._storyboard_profile_name = profile.name
        self._storyboard_custom_target = custom_target_name
        self._storyboard_output_kind = self.output_kind_combo.currentText()
        self._storyboard_transition_seconds = self.transition_spin.value()
        local_scenes = generate_storyboard(self.result, self.scene_count_spin.value())
        use_ollama = self.prompt_mode_combo.currentText().startswith("Ollama")
        model_name = self.ollama_model_combo.currentText().strip()
        if use_ollama and not model_name:
            self.refresh_ollama_models()
            model_name = self.ollama_model_combo.currentText().strip()
        if use_ollama and not model_name:
            QMessageBox.information(
                self,
                "Kein Ollama-Modell ausgewählt",
                "Es wurde kein Ollama-Modell gefunden oder ausgewählt. Die App kann die Bild-Prompts aber weiterhin lokal erzeugen.",
            )
            use_ollama = False

        package_mode = self._storyboard_output_kind.startswith("Gesamtpaket")
        dialog_label = "Gesamtpaket-Produktionsauftrag wird erzeugt …" if package_mode else "Bild-Prompts werden erzeugt …"
        dialog = QProgressDialog(dialog_label, "Abbrechen", 0, 100, self)
        dialog.setWindowTitle(f"{APP_NAME} – {'Gesamtpaket' if package_mode else 'Storyboard'}")
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.setMinimumDuration(0)
        dialog.setAutoClose(False)
        dialog.setAutoReset(False)
        dialog.setValue(0)

        thread = QThread(self)
        worker = StoryboardGenerationWorker(
            self.story_edit.toPlainText(),
            local_scenes,
            use_ollama,
            model_name,
            target_name,
            profile.mode,
            self._storyboard_output_kind,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._storyboard_generation_progress)
        worker.finished.connect(self._storyboard_generation_finished)
        worker.error.connect(self._storyboard_generation_failed)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.error.connect(worker.deleteLater)
        thread.finished.connect(self._storyboard_thread_finished)
        dialog.canceled.connect(self._cancel_storyboard_generation)

        self._storyboard_thread = thread
        self._storyboard_worker = worker
        self._storyboard_dialog = dialog
        self.generate_prompts_button.setEnabled(False)
        self.save_prompts_button.setEnabled(False)
        self.status_label.setText(
            "Gesamtpaket-Produktionsauftrag wird erzeugt …" if package_mode else "Bild-Prompts werden erzeugt …"
        )
        dialog.show()
        thread.start()

    def _storyboard_generation_progress(self, value: int, message: str) -> None:
        if self._storyboard_dialog is not None:
            self._storyboard_dialog.setLabelText(message)
            self._storyboard_dialog.setValue(value)
        self.status_label.setText(message)

    def _cancel_storyboard_generation(self) -> None:
        if self._storyboard_worker is not None:
            self._storyboard_worker.cancel()
        if self._storyboard_thread is not None:
            self._storyboard_thread.quit()
        if self._storyboard_dialog is not None:
            self._storyboard_dialog.close()
        self.status_label.setText("Prompt-Erzeugung abgebrochen.")

    def _current_media_package_settings(self) -> MediaPackageSettings:
        voice = self.voice_combo.currentData() or {}
        backend_key = str(voice.get("backend", ""))
        backend_name = BACKEND_LABELS.get(backend_key, backend_key or "Systemstandard")
        return MediaPackageSettings(
            aspect_ratio="16:9",
            resolution="1920x1080",
            fps=30,
            transition_seconds=self._storyboard_transition_seconds,
            output_video="scifi_story.mp4",
            output_zip="scifi_story_package.zip",
            voice_name=str(voice.get("name") or self.saved_voice_name or "Systemstandard"),
            voice_backend=backend_name,
            speech_rate=self.rate_slider.value(),
            voice_volume=self.voice_volume.value(),
            background_enabled=self.background_check.isChecked() and SOUND_FILE.is_file(),
            background_volume=self.background_volume.value(),
            background_filename=SOUND_FILE.name,
        )

    def _storyboard_generation_finished(self, scenes: object, source: str, model: str, note: str) -> None:
        scene_list = list(scenes or [])
        self.storyboard_scenes = scene_list
        profile = self.prompt_profile_manager.get(self._storyboard_profile_name)
        package_mode = self._storyboard_output_kind.startswith("Gesamtpaket")
        if profile is None:
            self._storyboard_generation_failed("Das ausgewählte Zielprofil ist nicht mehr verfügbar.")
            return
        if package_mode:
            self.storyboard_text = render_media_package_text(
                scene_list,
                full_story=self.story_edit.toPlainText(),
                source=source,
                model=model,
                profile=profile,
                custom_target_name=self._storyboard_custom_target,
                settings=self._current_media_package_settings(),
            )
        else:
            self.storyboard_text = render_storyboard_text(
                scene_list,
                source=source,
                model=model,
                profile=profile,
                custom_target_name=self._storyboard_custom_target,
                aspect_ratio="16:9",
            )
        self.prompts_edit.setPlainText(self.storyboard_text)
        if not self.tabs.isVisible():
            self.toggle_story_panel()
        self.tabs.setCurrentWidget(self.prompts_edit)
        self.save_prompts_button.setEnabled(bool(scene_list))
        if self._storyboard_dialog is not None:
            self._storyboard_dialog.setValue(100)
            self._storyboard_dialog.close()
        if note:
            kind = "Gesamtpaket-Prompt" if package_mode else "Bild-Prompts"
            self.storyboard_info_label.setText(
                f"{kind} lokal erzeugt. Ollama-Hinweis: {note}"
            )
            self.status_label.setText(f"{kind} lokal erzeugt (Ollama-Fallback).")
        else:
            target = self._storyboard_custom_target or self._storyboard_profile_name
            if package_mode:
                self.storyboard_info_label.setText(
                    f"Gesamtpaket-Produktionsauftrag für {target} bereit ({source}{' / ' + model if model else ''})."
                )
                self.status_label.setText("Gesamtpaket-Produktionsauftrag wurde erzeugt.")
            else:
                self.storyboard_info_label.setText(
                    f"Ausführbarer Bildserien-Auftrag für {target} bereit ({source}{' / ' + model if model else ''})."
                )
                self.status_label.setText("Bild-Prompts wurden erzeugt.")

    def _storyboard_generation_failed(self, message: str) -> None:
        if self._storyboard_dialog is not None:
            self._storyboard_dialog.close()
        self.status_label.setText("Prompt-Erzeugung fehlgeschlagen.")
        QMessageBox.critical(self, "Prompt-Erzeugung fehlgeschlagen", message)

    def _storyboard_thread_finished(self) -> None:
        thread = self._storyboard_thread
        self._storyboard_thread = None
        self._storyboard_worker = None
        self._storyboard_dialog = None
        self.generate_prompts_button.setEnabled(bool(self.prompt_profile_manager.profiles))
        if thread is not None:
            thread.deleteLater()

    def save_storyboard_prompts(self) -> None:
        package_mode = self._storyboard_output_kind.startswith("Gesamtpaket")
        kind_label = "Gesamtpaket-Produktionsauftrag" if package_mode else "Bild-Prompts"
        if not self.storyboard_text.strip():
            QMessageBox.information(self, f"Kein {kind_label}", f"Es gibt noch keinen {kind_label} zum Speichern.")
            return
        stem = "scifi_media_package_prompt" if package_mode else "scifi_storyboard"
        default = BASE_DIR / f"{stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        filename, _ = QFileDialog.getSaveFileName(
            self, f"{kind_label} speichern", str(default),
            "Textdatei (*.txt);;Markdown (*.md);;JSON (*.json);;Alle Dateien (*)",
        )
        if not filename:
            return
        path = Path(filename)
        try:
            if path.suffix.lower() == ".json":
                profile = self.prompt_profile_manager.get(self._storyboard_profile_name)
                target_name = self._storyboard_custom_target or self._storyboard_profile_name
                if package_mode and profile:
                    settings = self._current_media_package_settings()
                    payload = build_media_manifest(
                        self.storyboard_scenes,
                        target_name=target_name,
                        profile=profile,
                        settings=settings,
                    )
                    payload.update({
                        "app_version": APP_VERSION,
                        "instruction_document": self.storyboard_text,
                        "full_story": self.story_edit.toPlainText(),
                    })
                else:
                    payload = {
                        "app_version": APP_VERSION,
                        "task": "generate_image_series",
                        "target_ai": target_name,
                        "target_profile": self._storyboard_profile_name,
                        "target_mode": profile.mode if profile else "unknown",
                        "aspect_ratio": "16:9",
                        "scene_count": len(self.storyboard_scenes),
                        "global_negative_prompt": profile.negative_prompt if profile else "",
                        "instruction_document": self.storyboard_text,
                        "scenes": [
                            {
                                "index": scene.index,
                                "title": scene.title,
                                "summary": scene.summary,
                                "narration_text": scene.narration_text,
                                "prompt": scene.prompt,
                                "start_step": scene.start_step,
                                "end_step": scene.end_step,
                            }
                            for scene in self.storyboard_scenes
                        ],
                    }
                path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8-sig")
            else:
                path.write_text(self.storyboard_text, encoding="utf-8-sig")
            self.status_label.setText(f"{kind_label} gespeichert: {path}")
        except OSError as exc:
            QMessageBox.critical(self, "Speicherfehler", str(exc))

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
        self.story_completed = False
        self.current_activation_text = ""
        self.storyboard_scenes = []
        self.storyboard_text = ""
        self.prompts_edit.clear()
        self.execute_button.setEnabled(self.voice_combo.count() > 0)
        self.audio_export_button.setEnabled(False)
        self.save_prompts_button.setEnabled(False)
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
            "Berechnete Stories können samt der aktuell eingestellten Brückenatmosphäre als WAV "
            "und bei vorhandenem FFmpeg auch als MP3 exportiert werden.<br><br>"
            "Zusätzlich können ausführbare Bildserien-Aufträge oder vollständige Gesamtpaket-Prompts für "
            "Szenenbilder, TTS-Audio, Videozusammenschnitt und ZIP-Ausgabe erzeugt werden. Die Ausgabe wird für "
            "ChatGPT, Grok, Gemini, Stable Diffusion oder andere Systeme angepasst. "
            "Die Zielprofile liegen extern im Ordner <code>prompt_profiles</code>.<br><br>"
            "Der enthaltene Hintergrundklang ist eine neu erzeugte, generische Sci-Fi-Atmosphäre; "
            "es sind keine Star-Trek-Audiodateien enthalten.<br><br>"
            "Original source / updates: github.com/zeittresor",
        )

    def closeEvent(self, event) -> None:
        self._save_settings()
        self.stop_playback()
        if self._export_worker is not None:
            self._export_worker.cancel()
        if self._export_thread is not None:
            self._export_thread.quit()
            if not self._export_thread.wait(10_000):
                QMessageBox.warning(
                    self,
                    "Audioexport läuft noch",
                    "Der laufende Audioexport konnte noch nicht sauber beendet werden. "
                    "Bitte warten Sie kurz und schließen Sie die Anwendung danach erneut.",
                )
                event.ignore()
                return
        if self._storyboard_worker is not None:
            self._storyboard_worker.cancel()
        if self._storyboard_thread is not None:
            self._storyboard_thread.quit()
            self._storyboard_thread.wait(2000)
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
