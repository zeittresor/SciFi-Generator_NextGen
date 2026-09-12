from __future__ import annotations

import json
import sys
from math import gcd
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QObject, pyqtSignal, pyqtSlot, QThread, QTimer, QUrl
from PyQt6.QtGui import QAction, QDesktopServices, QFont, QIcon, QResizeEvent
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer, QSoundEffect
from PyQt6.QtTextToSpeech import QTextToSpeech
from PyQt6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QFrame, QGridLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLayout, QLineEdit, QMainWindow, QMessageBox,
    QProgressBar, QProgressDialog, QPushButton, QScrollArea, QSizePolicy, QSlider, QSpinBox,
    QTabWidget, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget, QListWidget,
)

from audio_export import AudioExportRequest, AudioExportWorker, find_ffmpeg
from story_engine import APP_VERSION, GenerationResult, StoryEngine, StoryEngineError
from storyboard_generator import StoryboardScene, generate_storyboard, render_storyboard_text
from media_package_generator import MediaPackageSettings, build_media_manifest, render_media_package_text
from handoff_package import HandoffPackageError, create_handoff_zip, validate_total_package_prompt
from ollama_client import OllamaClient, OllamaClientError
from prompt_profile_manager import PromptProfile, PromptProfileManager
from theme_manager import ThemeManager
from tts_services import PiperTtsService, SapiTtsService, WinRtTtsService
from tts_package_manager import TtsPackageError, TtsPackageManager
from runtime_diagnostics import RuntimeDiagnostics

APP_NAME = "SciFi-Generator"
BASE_DIR = Path(__file__).resolve().parent
VARS_DIR = BASE_DIR / "data" / "vars"
SEQUENCE_FILE = BASE_DIR / "sequence_legacy.json"
SOUND_FILE = BASE_DIR / "data" / "sounds" / "background.wav"
STYLE_REFERENCE_FILE = BASE_DIR / "handoff_assets" / "style_reference.png"
LOG_DIR = BASE_DIR / "logs"
THEME_DIR = BASE_DIR / "themes"
PROMPT_PROFILE_DIR = BASE_DIR / "prompt_profiles"
TOOLS_DIR = BASE_DIR / "tools"
TEMP_DIR = BASE_DIR / "temp"
SETTINGS_FILE = BASE_DIR / "settings.json"
TTS_PACKAGE_CATALOG = BASE_DIR / "tts_package_catalog.json"
MLS_SPEAKER_ALIASES_FILE = BASE_DIR / "data" / "mls_speaker_aliases.json"
CONFIG_PROFILE_FORMAT = "SciFi-Generator configuration profile"
CONFIG_PROFILE_VERSION = 1

BACKEND_LABELS = {
    "winrt": "Windows OneCore/WinRT",
    "sapi": "Windows SAPI",
    "qt": "Qt",
    "piper": "Piper (lokales Komplettpaket)",
}

BASE_COMPACT_WIDTH = 1180
BASE_WINDOW_HEIGHT = 820
BASE_CONTROL_VIEWPORT_WIDTH = 1080
BASE_CONTROL_VIEWPORT_HEIGHT = 720
MAX_UI_SCALE = 1.30

VIDEO_RESOLUTION_PRESETS = [
    ("512 × 512 (1:1, kompakt)", 512, 512),
    ("1024 × 1024 (1:1, Standard)", 1024, 1024),
    ("1280 × 720 (HD, 16:9)", 1280, 720),
    ("1280 × 768 (WXGA, 5:3)", 1280, 768),
    ("1920 × 1080 (Full HD, 16:9)", 1920, 1080),
    ("2560 × 1440 (QHD, 16:9)", 2560, 1440),
    ("3840 × 2160 (4K UHD, 16:9)", 3840, 2160),
    ("Benutzerdefiniert …", 0, 0),
]

PIPER_PROSODY_PRESETS = [
    ("Stabil / gleichmäßig (empfohlen)", "stable", 0.45, 0.35),
    ("Natürlich (Modellstandard)", "natural", None, None),
    ("Ausdrucksstärker", "expressive", 0.80, 0.95),
]

PIPER_STYLE_LABELS = {
    "amused": "Amüsiert",
    "angry": "Wütend",
    "disgusted": "Angeekelt",
    "drunk": "Betrunken",
    "neutral": "Neutral",
    "sleepy": "Schläfrig",
    "surprised": "Überrascht",
    "whisper": "Flüstern",
}



def load_mls_speaker_aliases(path: Path = MLS_SPEAKER_ALIASES_FILE) -> dict[int, str]:
    """Load stable fictional mnemonic aliases for the Piper MLS speakers.

    The aliases are intentionally unrelated to the real dataset speakers. They
    exist only so humans can remember a voice more easily than a numeric ID.
    """
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        raw = payload.get("aliases", {}) if isinstance(payload, dict) else {}
        aliases = {int(key): str(value).strip() for key, value in raw.items() if str(value).strip()}
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        return {}
    return aliases

def qsoundeffect_infinite_loop_count() -> int:
    """Return Qt's infinite QSoundEffect loop value across Python Qt bindings.

    PyQt6 exposes the scoped C++ enum as QSoundEffect.Loop.Infinite while
    some older bindings exposed QSoundEffect.Infinite directly.  The numeric
    Qt value is -2.  Keeping the fallback makes the application robust against
    binding/API differences without making startup depend on one enum layout.
    """
    loop_enum = getattr(QSoundEffect, "Loop", None)
    if loop_enum is not None:
        infinite = getattr(loop_enum, "Infinite", None)
        if infinite is not None:
            value = getattr(infinite, "value", infinite)
            try:
                return int(value)
            except (TypeError, ValueError):
                pass

    legacy = getattr(QSoundEffect, "Infinite", None)
    if legacy is not None:
        value = getattr(legacy, "value", legacy)
        try:
            return int(value)
        except (TypeError, ValueError):
            pass

    # Qt defines QSoundEffect::Infinite as -2.  Reaching this branch means the
    # Python binding does not publish either enum spelling, but setLoopCount()
    # still accepts the documented integer value.
    return -2


def emergency_stylesheet(scale: float = 1.0) -> str:
    px = lambda value: max(1, round(value * scale))
    return f"""
QMainWindow, QWidget {{ background: #1B1D21; color: #F2F4F7; }}
QFrame#appHeader, QFrame#heroCard, QFrame#statusStrip {{ background: #262A31; border: 1px solid #788493; border-radius: {px(8)}px; }}
QLabel#appTitle {{ font-size: {px(19)}px; font-weight: 700; }}
QLabel#sectionHeroTitle {{ font-size: {px(15)}px; font-weight: 700; }}
QLabel#versionBadge, QLabel#stepBadge {{ background: #6B8FD6; color: #FFFFFF; border-radius: {px(8)}px; padding: {px(5)}px {px(9)}px; font-weight: 700; }}
QLabel#infoCard {{ background: #262A31; border-left: {px(4)}px solid #6B8FD6; padding: {px(9)}px; }}
QTextEdit, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{ background: #0F1115; color: #FFFFFF; border: 1px solid #788493; }}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{ min-height: {px(26)}px; padding: {px(2)}px {px(5)}px; }}
QPushButton {{ background: #343941; color: #FFFFFF; border: 1px solid #788493; padding: {px(5)}px {px(9)}px; min-height: {px(28)}px; }}
QPushButton:hover {{ background: #48505B; }}
QLabel#workflowIntro, QLabel#workflowStatus {{ background: #262A31; color: #F2F4F7; border: 1px solid #788493; padding: {px(7)}px; }}
QPushButton#primaryAction {{ background: #6B8FD6; color: #FFFFFF; font-weight: 700; min-height: {px(36)}px; }}
QPushButton#secondaryAction {{ font-weight: 600; min-height: {px(34)}px; }}
QGroupBox {{ border: 1px solid #788493; margin-top: {px(9)}px; padding-top: {px(9)}px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: {px(8)}px; padding: 0 {px(4)}px; }}
QScrollBar:vertical {{ width: {px(14)}px; }}
QScrollBar:horizontal {{ height: {px(14)}px; }}
"""



class StoryboardGenerationWorker(QObject):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(object, str, str, str)
    error = pyqtSignal(str)

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



class TtsPackageWorker(QObject):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(str, str)
    error = pyqtSignal(str)

    def __init__(self, manager: TtsPackageManager, package_id: str, action: str = "install") -> None:
        super().__init__()
        self.manager = manager
        self.package_id = package_id
        self.action = action
        self._canceled = False

    def cancel(self) -> None:
        self._canceled = True

    def _check_cancel(self) -> None:
        if self._canceled:
            raise TtsPackageError("Vorgang wurde abgebrochen.")

    @pyqtSlot()
    def run(self) -> None:
        try:
            if self.action == "remove":
                self.progress.emit(20, "Sprachpaket wird entfernt …")
                self.manager.remove(self.package_id)
                self.progress.emit(100, "Sprachpaket entfernt.")
                self.finished.emit(self.package_id, "removed")
            else:
                self.manager.install(
                    self.package_id,
                    callback=lambda value, message: self.progress.emit(value, message),
                    cancel_check=self._check_cancel,
                )
                self.finished.emit(self.package_id, "installed")
        except Exception as exc:
            self.error.emit(str(exc))


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
        self._narration_temp_file: str | None = None
        self.voice_catalogs: dict[str, list[dict]] = {"winrt": [], "sapi": [], "qt": [], "piper": []}
        self.qt_voice_objects: dict[str, object] = {}
        self.voice_diagnostics: list[str] = []
        self.saved_voice_backend = ""
        self.saved_voice_id = ""
        self.saved_voice_name = ""
        self._pending_saved_voice_key = ""
        self.saved_piper_speakers: dict[str, str] = {}
        self.saved_piper_prosody = "stable"
        self.mls_speaker_aliases = load_mls_speaker_aliases()
        self._settings_loaded = False
        self._settings_autosave_timer = QTimer(self)
        self._settings_autosave_timer.setSingleShot(True)
        self._settings_autosave_timer.setInterval(450)
        self._settings_autosave_timer.timeout.connect(self._save_settings)
        self.runtime_diagnostics = RuntimeDiagnostics(LOG_DIR, APP_NAME, APP_VERSION)
        self._previous_excepthook = sys.excepthook
        self._background_was_playing_before_pause = False
        self._export_thread: QThread | None = None
        self._export_worker: AudioExportWorker | None = None
        self._export_dialog: QProgressDialog | None = None
        self._tts_package_thread: QThread | None = None
        self._tts_package_worker: TtsPackageWorker | None = None
        self.storyboard_scenes: list[StoryboardScene] = []
        self.storyboard_text = ""
        self.ollama_client = OllamaClient()
        self._storyboard_thread: QThread | None = None
        self._storyboard_worker: StoryboardGenerationWorker | None = None
        self._storyboard_dialog: QProgressDialog | None = None
        self._storyboard_profile_name = "ChatGPT"
        self._storyboard_custom_target = ""
        self._storyboard_output_kind = "Gesamtpaket — fertiges Video mit TTS, Hintergrundsound und ZIP"
        self._storyboard_transition_seconds = 0.8
        self._storyboard_video_width = 1024
        self._storyboard_video_height = 1024
        self._storyboard_aspect_ratio = "1:1"
        self._storyboard_media_settings: MediaPackageSettings | None = None

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
        self.tts_package_manager = TtsPackageManager(BASE_DIR, TTS_PACKAGE_CATALOG)

        self.qt_tts = QTextToSpeech(self)
        self.qt_tts.stateChanged.connect(self._qt_tts_state_changed)

        # QSoundEffect is deliberately used for the short looping bridge ambience.
        # Running two QMediaPlayer instances at once (Piper/WinRT narration + ambience)
        # caused some Windows multimedia backends to replay only the first buffer of
        # the ambience. QSoundEffect is designed for resident, gapless WAV loops and
        # is independent from the narration QMediaPlayer.
        self.background_effect = QSoundEffect(self)
        if SOUND_FILE.is_file():
            self.background_effect.setSource(QUrl.fromLocalFile(str(SOUND_FILE)))
            self.background_effect.setLoopCount(qsoundeffect_infinite_loop_count())
            self.background_effect.setVolume(0.18)
            self.background_effect.statusChanged.connect(self._background_status_changed)

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

        self.piper_service = PiperTtsService(TEMP_DIR, self)
        self.piper_service.synthesis_ready.connect(self._piper_synthesis_ready)
        self.piper_service.error.connect(self._voice_service_error)
        self.piper_service.state_changed.connect(lambda state: self._handle_speech_state("piper", state))

        self._build_ui()
        self._load_qt_voices()
        self._refresh_piper_voice_catalog()
        self._load_settings()
        self._settings_loaded = True
        self._connect_settings_autosave()
        self._validate_installation()
        self.winrt_service.refresh_voices()
        QTimer.singleShot(0, self._update_ui_scale)
        QTimer.singleShot(150, self.refresh_ollama_models)

    def _build_ui(self) -> None:
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(1180, 820)
        self.setMinimumSize(860, 620)
        icon_path = BASE_DIR / "app_icon.svg"
        if icon_path.is_file():
            self.setWindowIcon(QIcon(str(icon_path)))

        central = QWidget()
        root = QVBoxLayout(central)
        self.root_layout = root
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(10)
        self.setCentralWidget(central)

        header = QFrame()
        header.setObjectName("appHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 12, 16, 12)
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel(APP_NAME)
        title.setObjectName("appTitle")
        subtitle = QLabel("Zufällige Sektor-Missionen · Audio · Storyboard · LLM-Gesamtpakete")
        subtitle.setObjectName("appSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header_layout.addLayout(title_box, 1)
        version_badge = QLabel(f"v{APP_VERSION}")
        version_badge.setObjectName("versionBadge")
        version_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(version_badge)
        root.addWidget(header)

        self.main_tabs = QTabWidget()
        self.main_tabs.setObjectName("mainTabs")
        self.main_tabs.setDocumentMode(True)
        self.main_tabs.setUsesScrollButtons(True)
        root.addWidget(self.main_tabs, 1)

        def make_scroll_page(object_name: str) -> tuple[QScrollArea, QWidget, QVBoxLayout]:
            content = QWidget()
            content.setObjectName(object_name)
            layout = QVBoxLayout(content)
            layout.setContentsMargins(16, 14, 16, 18)
            layout.setSpacing(12)
            layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
            scroll = QScrollArea()
            scroll.setObjectName(object_name + "Scroll")
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            scroll.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            scroll.setWidget(content)
            return scroll, content, layout

        # ------------------------------------------------------------------
        # Tab 1: Mission
        # ------------------------------------------------------------------
        mission_scroll, mission_page, mission_layout = make_scroll_page("missionPage")
        self.controls_scroll = mission_scroll
        self.controls_widget = mission_page
        self.controls_layout = mission_layout

        mission_intro = QFrame()
        mission_intro.setObjectName("heroCard")
        mission_intro_layout = QVBoxLayout(mission_intro)
        mission_intro_layout.setContentsMargins(16, 14, 16, 14)
        mission_intro_title = QLabel("Neue Mission")
        mission_intro_title.setObjectName("sectionHeroTitle")
        mission_intro_text = QLabel(
            "Jede Geschichte beginnt mit der Ankunft in einem neuen Sternensystem und endet wieder im freien Raum, "
            "bereit für den nächsten Sektorsprung. Der Mittelteil verzweigt sich abhängig vom Seed in unterschiedliche Ereignisse."
        )
        mission_intro_text.setWordWrap(True)
        mission_intro_text.setObjectName("mutedText")
        mission_intro_layout.addWidget(mission_intro_title)
        mission_intro_layout.addWidget(mission_intro_text)
        mission_layout.addWidget(mission_intro)

        action_group = QGroupBox("Sektor-Sprung")
        action_layout = QVBoxLayout(action_group)
        action_layout.setSpacing(10)
        action_buttons = QHBoxLayout()
        self.generate_button = QPushButton("Sektor-Sprung berechnen")
        self.generate_button.setObjectName("primaryAction")
        self.generate_button.setToolTip("Erzeugt eine neue Geschichte, liest sie aber noch nicht vor.")
        self.generate_button.clicked.connect(self.generate_story)
        self.execute_button = QPushButton("Sprung durchführen")
        self.execute_button.setObjectName("secondaryAction")
        self.execute_button.setToolTip(
            "Liest die zuvor berechnete Geschichte einmal vollständig vor. Für eine weitere Erzählung muss danach ein neuer Sektor-Sprung berechnet werden."
        )
        self.execute_button.clicked.connect(self.execute_jump)
        self.execute_button.setEnabled(False)
        action_buttons.addWidget(self.generate_button, 2)
        action_buttons.addWidget(self.execute_button, 2)
        action_layout.addLayout(action_buttons)

        mission_nav = QHBoxLayout()
        self.toggle_story_button = QPushButton("Story && Trace anzeigen")
        self.toggle_story_button.setToolTip("Öffnet die Story-, Auswahlprotokoll- und Produktionsansicht.")
        self.toggle_story_button.clicked.connect(self.toggle_story_panel)
        media_nav_button = QPushButton("Zum Medienpaket")
        media_nav_button.setToolTip("Öffnet die Einstellungen für Bildserie oder Gesamtpaket.")
        media_nav_button.clicked.connect(lambda: self.main_tabs.setCurrentIndex(1))
        mission_nav.addWidget(self.toggle_story_button)
        mission_nav.addWidget(media_nav_button)
        action_layout.addLayout(mission_nav)
        mission_layout.addWidget(action_group)

        workflow_group = QGroupBox("Typischer Ablauf")
        workflow_layout = QGridLayout(workflow_group)
        workflow_layout.setHorizontalSpacing(14)
        workflow_layout.setVerticalSpacing(8)
        workflow_steps = (
            ("1", "Mission erzeugen", "Sektor-Sprung berechnen und Storyzweig zufällig auswählen."),
            ("2", "Story prüfen oder vorlesen", "Text und Trace ansehen oder den Sprung per TTS durchführen."),
            ("3", "Optional Medien erzeugen", "Storyboard oder Gesamtpaket für eine Ziel-LLM vorbereiten."),
            ("4", "Nächster Sprung", "Nach Missionsende ist das Schiff wieder frei und sprungbereit."),
        )
        for row, (number, step_title, description) in enumerate(workflow_steps):
            badge = QLabel(number)
            badge.setObjectName("stepBadge")
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            workflow_layout.addWidget(badge, row, 0)
            step_label = QLabel(f"<b>{step_title}</b><br>{description}")
            step_label.setWordWrap(True)
            workflow_layout.addWidget(step_label, row, 1)
        workflow_layout.setColumnStretch(1, 1)
        mission_layout.addWidget(workflow_group)
        mission_layout.addStretch(1)
        self.main_tabs.addTab(mission_scroll, "Mission")

        # ------------------------------------------------------------------
        # Tab 2: Medienpaket
        # ------------------------------------------------------------------
        media_scroll, media_page, media_layout = make_scroll_page("mediaPage")
        self.workflow_intro_label = QLabel(
            "<b>Medienausgabe:</b> Wähle zuerst, ob nur eine Bildserie oder ein vollständiges Gesamtpaket mit TTS, "
            "Hintergrundsound, Video und ZIP erzeugt werden soll. Alle zugehörigen Optionen stehen direkt in diesem Tab."
        )
        self.workflow_intro_label.setWordWrap(True)
        self.workflow_intro_label.setObjectName("workflowIntro")
        media_layout.addWidget(self.workflow_intro_label)

        target_group = QGroupBox("Ziel und Ausgabe")
        target_form = QFormLayout(target_group)
        target_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        target_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        target_form.setHorizontalSpacing(18)
        target_form.setVerticalSpacing(9)

        self.output_kind_combo = QComboBox()
        self.output_kind_combo.addItems([
            "Gesamtpaket — fertiges Video mit TTS, Hintergrundsound und ZIP",
            "Nur Bildserie — keine Audio- oder Videodatei",
        ])
        self.output_kind_combo.setCurrentIndex(0)
        self.output_kind_combo.setToolTip(
            "Gesamtpaket erzeugt einen Produktionsauftrag für Bilder, TTS, Hintergrundmix, Video und ZIP. "
            "Nur Bildserie fordert ausdrücklich keine Audio- oder Videodateien an."
        )
        self.output_kind_combo.currentTextChanged.connect(self._update_target_ai_controls)
        target_form.addRow("Gewünschtes Ergebnis:", self.output_kind_combo)

        self.target_ai_combo = QComboBox()
        self.target_ai_combo.addItems(self.prompt_profile_manager.names())
        self.target_ai_combo.currentTextChanged.connect(self._update_target_ai_controls)
        target_form.addRow("Zielsystem / LLM:", self.target_ai_combo)

        self.scene_count_spin = QSpinBox()
        self.scene_count_spin.setRange(6, 10)
        self.scene_count_spin.setValue(8)
        self.scene_count_spin.valueChanged.connect(self._update_tab_status_summaries)
        target_form.addRow("Schlüsselszenen:", self.scene_count_spin)

        self.custom_target_container = QWidget()
        custom_target_layout = QHBoxLayout(self.custom_target_container)
        custom_target_layout.setContentsMargins(0, 0, 0, 0)
        self.custom_target_label = QLabel("Andere KI:")
        self.custom_target_edit = QLineEdit()
        self.custom_target_edit.setPlaceholderText("Name der anderen Bildsynthese-KI")
        self.custom_target_edit.setToolTip("Wird nur beim Zielprofil 'Andere' verwendet.")
        self.custom_target_edit.textChanged.connect(self._update_target_ai_controls)
        custom_target_layout.addWidget(self.custom_target_label)
        custom_target_layout.addWidget(self.custom_target_edit, 1)
        target_form.addRow("", self.custom_target_container)
        media_layout.addWidget(target_group)

        self.output_kind_status_label = QLabel()
        self.output_kind_status_label.setObjectName("workflowStatus")
        self.output_kind_status_label.setWordWrap(True)
        media_layout.addWidget(self.output_kind_status_label)

        self.media_options_group = QGroupBox("Video, Stimme und Übergänge")
        media_options_layout = QVBoxLayout(self.media_options_group)
        media_form = QFormLayout()
        media_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        media_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        media_form.setHorizontalSpacing(18)
        media_form.setVerticalSpacing(8)

        self.video_resolution_combo = QComboBox()
        for label, width, height in VIDEO_RESOLUTION_PRESETS:
            self.video_resolution_combo.addItem(label, {"width": width, "height": height})
        self.video_resolution_combo.setCurrentIndex(1)
        self.video_resolution_combo.setToolTip("Legt die exakte Zielauflösung des finalen Videos und das Seitenverhältnis der Szenenbilder fest.")
        self.video_resolution_combo.currentIndexChanged.connect(self._update_video_resolution_controls)
        self.video_resolution_combo.currentIndexChanged.connect(self._update_tab_status_summaries)
        media_form.addRow("Videoauflösung:", self.video_resolution_combo)
        self.video_resolution_label = media_form.labelForField(self.video_resolution_combo)

        self.custom_video_size_widget = QWidget()
        custom_video_layout = QHBoxLayout(self.custom_video_size_widget)
        custom_video_layout.setContentsMargins(0, 0, 0, 0)
        custom_video_layout.setSpacing(6)
        self.custom_video_width_spin = QSpinBox()
        self.custom_video_width_spin.setRange(256, 8192)
        self.custom_video_width_spin.setSingleStep(8)
        self.custom_video_width_spin.setValue(1024)
        self.custom_video_width_spin.setSuffix(" px")
        self.custom_video_height_spin = QSpinBox()
        self.custom_video_height_spin.setRange(256, 8192)
        self.custom_video_height_spin.setSingleStep(8)
        self.custom_video_height_spin.setValue(1024)
        self.custom_video_height_spin.setSuffix(" px")
        self.custom_video_width_spin.valueChanged.connect(self._update_video_resolution_controls)
        self.custom_video_height_spin.valueChanged.connect(self._update_video_resolution_controls)
        self.custom_video_width_spin.valueChanged.connect(self._update_tab_status_summaries)
        self.custom_video_height_spin.valueChanged.connect(self._update_tab_status_summaries)
        custom_video_layout.addWidget(self.custom_video_width_spin)
        custom_video_layout.addWidget(QLabel("×"))
        custom_video_layout.addWidget(self.custom_video_height_spin)
        custom_video_layout.addStretch(1)
        media_form.addRow("Eigene Größe:", self.custom_video_size_widget)
        self.custom_video_size_label = media_form.labelForField(self.custom_video_size_widget)

        self.video_aspect_info_label = QLabel("1:1 — quadratisches Video")
        self.video_aspect_info_label.setWordWrap(True)
        media_form.addRow("Seitenverhältnis:", self.video_aspect_info_label)
        self.video_aspect_info_field_label = media_form.labelForField(self.video_aspect_info_label)

        self.video_fps_combo = QComboBox()
        for fps in (8, 12, 24, 30, 60):
            label = f"{fps} fps" + (" — empfohlen für Standbilder" if fps == 8 else "")
            self.video_fps_combo.addItem(label, fps)
        self.video_fps_combo.setCurrentIndex(0)
        self.video_fps_combo.setToolTip("8 fps reichen für weitgehend statische Szenenbilder meist aus. Höhere Werte sind für stärkere Bildbewegungen sinnvoll.")
        self.video_fps_combo.currentIndexChanged.connect(self._update_tab_status_summaries)
        media_form.addRow("Bildrate:", self.video_fps_combo)
        self.video_fps_label = media_form.labelForField(self.video_fps_combo)

        self.transition_spin = QDoubleSpinBox()
        self.transition_spin.setRange(0.0, 5.0)
        self.transition_spin.setDecimals(1)
        self.transition_spin.setSingleStep(0.1)
        self.transition_spin.setValue(0.8)
        self.transition_spin.setSuffix(" s")
        self.transition_spin.setToolTip("Gewünschte Dauer der sanften Überblendung zwischen zwei Szenen im Gesamtpaket.")
        self.transition_spin.valueChanged.connect(self._update_tab_status_summaries)
        media_form.addRow("Überblendung:", self.transition_spin)
        self.transition_label = media_form.labelForField(self.transition_spin)

        self.package_voice_character_combo = QComboBox()
        self.package_voice_character_combo.addItems(["Menschlich / natürlich", "Neutral", "Robotisch / synthetisch"])
        self.package_voice_character_combo.currentTextChanged.connect(self._update_tab_status_summaries)
        media_form.addRow("Stimmcharakter:", self.package_voice_character_combo)
        self.package_voice_character_label = media_form.labelForField(self.package_voice_character_combo)

        self.package_voice_gender_combo = QComboBox()
        self.package_voice_gender_combo.addItems(["Weiblich", "Männlich", "Neutral / androgyn", "Egal"])
        self.package_voice_gender_combo.currentTextChanged.connect(self._update_tab_status_summaries)
        media_form.addRow("Stimmliche Wirkung:", self.package_voice_gender_combo)
        self.package_voice_gender_label = media_form.labelForField(self.package_voice_gender_combo)

        self.package_voice_quality_combo = QComboBox()
        self.package_voice_quality_combo.addItems(["Beste verfügbare Qualität", "Hohe Qualität", "Standard / schnell"])
        self.package_voice_quality_combo.currentTextChanged.connect(self._update_tab_status_summaries)
        media_form.addRow("TTS-Qualität:", self.package_voice_quality_combo)
        self.package_voice_quality_label = media_form.labelForField(self.package_voice_quality_combo)
        media_options_layout.addLayout(media_form)
        media_layout.addWidget(self.media_options_group)

        self.result_contents_group = QGroupBox("Lieferumfang des Ergebnis-ZIP")
        result_contents_layout = QVBoxLayout(self.result_contents_group)
        result_contents_intro = QLabel(
            "Diese Auswahl bestimmt nur den finalen ZIP-Inhalt. Produktionsdateien dürfen intern trotzdem erzeugt werden, wenn sie für das Video benötigt werden."
        )
        result_contents_intro.setWordWrap(True)
        result_contents_layout.addWidget(result_contents_intro)
        self.result_include_video_check = QCheckBox("Fertiges Video (immer enthalten)")
        self.result_include_video_check.setChecked(True)
        self.result_include_video_check.setEnabled(False)
        self.result_include_images_check = QCheckBox("Szenenbilder im Ergebnis-ZIP")
        self.result_include_images_check.setChecked(True)
        self.result_include_audio_check = QCheckBox("Szenenaudios und final_mix.wav im Ergebnis-ZIP")
        self.result_include_audio_check.setChecked(True)
        self.result_include_clips_check = QCheckBox("Einzelclips im Ergebnis-ZIP")
        self.result_include_clips_check.setChecked(False)
        self.result_include_project_files_check = QCheckBox("Story, Prompts, Manifest, Log und Build-Dateien im Ergebnis-ZIP")
        self.result_include_project_files_check.setChecked(True)
        result_contents_layout.addWidget(self.result_include_video_check)
        for checkbox in (self.result_include_images_check, self.result_include_audio_check, self.result_include_clips_check, self.result_include_project_files_check):
            checkbox.stateChanged.connect(self._update_tab_status_summaries)
            result_contents_layout.addWidget(checkbox)
        media_layout.addWidget(self.result_contents_group)

        self.prompt_options_group = QGroupBox("Prompt-Verfeinerung mit Ollama")
        prompt_options_layout = QVBoxLayout(self.prompt_options_group)
        prompt_form = QFormLayout()
        prompt_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        prompt_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.prompt_mode_combo = QComboBox()
        self.prompt_mode_combo.addItems(["Lokal (regelbasiert)", "Ollama (lokales Modell)"])
        self.prompt_mode_combo.currentIndexChanged.connect(self._update_storyboard_mode_controls)
        self.prompt_mode_combo.currentIndexChanged.connect(self._update_tab_status_summaries)
        prompt_form.addRow("Prompt-Verfeinerung:", self.prompt_mode_combo)
        self.ollama_model_combo = QComboBox()
        self.ollama_model_combo.setEditable(True)
        self.ollama_model_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.ollama_model_combo.currentTextChanged.connect(self._update_tab_status_summaries)
        prompt_form.addRow("Ollama-Modell:", self.ollama_model_combo)
        prompt_options_layout.addLayout(prompt_form)
        self.refresh_ollama_button = QPushButton("Ollama-Modelle prüfen")
        self.refresh_ollama_button.clicked.connect(self.refresh_ollama_models)
        prompt_options_layout.addWidget(self.refresh_ollama_button)
        media_layout.addWidget(self.prompt_options_group)

        self.storyboard_info_label = QLabel()
        self.storyboard_info_label.setWordWrap(True)
        self.storyboard_info_label.setObjectName("infoCard")
        media_layout.addWidget(self.storyboard_info_label)

        media_actions = QHBoxLayout()
        self.generate_prompts_button = QPushButton("Gesamtpaket-Auftrag erzeugen")
        self.generate_prompts_button.setObjectName("primaryAction")
        self.generate_prompts_button.clicked.connect(self.generate_storyboard_prompts)
        self.save_prompts_button = QPushButton("Gesamtpaket-Übergabe-ZIP speichern …")
        self.save_prompts_button.setObjectName("secondaryAction")
        self.save_prompts_button.clicked.connect(self.save_storyboard_prompts)
        self.save_prompts_button.setEnabled(False)
        media_actions.addWidget(self.generate_prompts_button, 2)
        media_actions.addWidget(self.save_prompts_button, 2)
        media_layout.addLayout(media_actions)
        media_layout.addStretch(1)
        self.main_tabs.addTab(media_scroll, "Medienpaket")

        # ------------------------------------------------------------------
        # Tab 3: Sprache & Audio
        # ------------------------------------------------------------------
        audio_scroll, audio_page, audio_layout = make_scroll_page("audioPage")
        self.audio_tab_status_label = QLabel("Aktive Stimme und Hintergrund werden nach dem Laden angezeigt.")
        self.audio_tab_status_label.setObjectName("workflowStatus")
        self.audio_tab_status_label.setWordWrap(True)
        audio_layout.addWidget(self.audio_tab_status_label)
        speech_group = QGroupBox("Lokale Sprachausgabe")
        speech_layout = QVBoxLayout(speech_group)
        voice_form = QFormLayout()
        voice_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        voice_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.voice_combo = QComboBox()
        self.voice_combo.currentIndexChanged.connect(self._voice_changed)
        self.voice_combo.activated.connect(self._voice_user_activated)
        voice_form.addRow("Stimme:", self.voice_combo)
        speech_layout.addLayout(voice_form)

        voice_info_row = QHBoxLayout()
        self.voice_count_label = QLabel("Stimmen werden gesucht …")
        self.voice_count_label.setWordWrap(True)
        self.refresh_voices_button = QPushButton("Stimmen neu laden")
        self.refresh_voices_button.clicked.connect(self.refresh_voices)
        self.open_tts_manager_button = QPushButton("Weitere Stimmen …")
        self.open_tts_manager_button.clicked.connect(lambda: self.main_tabs.setCurrentIndex(self.tts_manager_tab_index))
        voice_info_row.addWidget(self.voice_count_label, 1)
        voice_info_row.addWidget(self.refresh_voices_button)
        voice_info_row.addWidget(self.open_tts_manager_button)
        speech_layout.addLayout(voice_info_row)

        self.piper_options_group = QGroupBox("Piper-Optionen")
        piper_options_form = QFormLayout(self.piper_options_group)
        piper_options_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.piper_style_label = QLabel("Emotion / Stil:")
        self.piper_style_combo = QComboBox()
        self.piper_style_combo.currentIndexChanged.connect(self._piper_style_changed)
        piper_options_form.addRow(self.piper_style_label, self.piper_style_combo)

        # Large multi-speaker Piper models (for example MLS Deutsch with 236
        # speakers) use an always-visible scrollable list instead of a searchable
        # combo box.  The user should be able to browse voices without already
        # knowing a dataset speaker identifier.
        self.piper_speaker_list_label = QLabel("Sprecher:")
        self.piper_speaker_list = QListWidget()
        self.piper_speaker_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.piper_speaker_list.setMinimumHeight(170)
        self.piper_speaker_list.setMaximumHeight(230)
        self.piper_speaker_list.currentRowChanged.connect(self._piper_style_changed)
        piper_options_form.addRow(self.piper_speaker_list_label, self.piper_speaker_list)
        self.piper_speaker_list_hint = QLabel(
            "Bei großen Mehrsprecher-Modellen kannst du direkt durch alle verfügbaren Sprecher scrollen. "
            "Für MLS werden optional stabile, frei erfundene Merknamen angezeigt; sie haben keinen Bezug zur echten Identität der Dataset-Sprecher."
        )
        self.piper_speaker_list_hint.setWordWrap(True)
        piper_options_form.addRow("", self.piper_speaker_list_hint)

        self.piper_prosody_combo = QComboBox()
        for label, key, _noise_scale, _noise_w in PIPER_PROSODY_PRESETS:
            self.piper_prosody_combo.addItem(label, key)
        self.piper_prosody_combo.currentIndexChanged.connect(self._update_tab_status_summaries)
        piper_options_form.addRow("Prosodie:", self.piper_prosody_combo)
        self.piper_prosody_hint = QLabel(
            "Stabil reduziert die zufällige Klang- und Rhythmusvariation zwischen Sätzen. "
            "Natürlich verwendet die Werte des jeweiligen Piper-Modells."
        )
        self.piper_prosody_hint.setWordWrap(True)
        piper_options_form.addRow("", self.piper_prosody_hint)
        self.piper_options_group.setVisible(False)
        speech_layout.addWidget(self.piper_options_group)

        rate_row = QGridLayout()
        rate_row.addWidget(QLabel("Geschwindigkeit"), 0, 0)
        self.rate_slider = QSlider(Qt.Orientation.Horizontal)
        self.rate_slider.setRange(-10, 10)
        self.rate_slider.setValue(0)
        self.rate_slider.valueChanged.connect(lambda value: self.qt_tts.setRate(value / 10.0))
        rate_row.addWidget(self.rate_slider, 0, 1)
        rate_row.addWidget(QLabel("Lautstärke Stimme"), 1, 0)
        self.voice_volume = QSlider(Qt.Orientation.Horizontal)
        self.voice_volume.setRange(0, 100)
        self.voice_volume.setValue(100)
        self.voice_volume.valueChanged.connect(lambda value: self.qt_tts.setVolume(value / 100.0))
        rate_row.addWidget(self.voice_volume, 1, 1)
        rate_row.setColumnStretch(1, 1)
        speech_layout.addLayout(rate_row)

        player_row = QHBoxLayout()
        self.pause_button = QPushButton("Pause")
        self.pause_button.clicked.connect(self.pause_or_resume)
        self.pause_button.setEnabled(False)
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop_playback)
        self.stop_button.setEnabled(False)
        self.selection_button = QPushButton("Story / Markierung vorlesen")
        self.selection_button.clicked.connect(self.speak_selection)
        player_row.addWidget(self.pause_button)
        player_row.addWidget(self.stop_button)
        player_row.addWidget(self.selection_button, 2)
        speech_layout.addLayout(player_row)

        self.audio_export_button = QPushButton("Story als Audiodatei speichern …")
        self.audio_export_button.setObjectName("secondaryAction")
        self.audio_export_button.clicked.connect(self.save_story_audio)
        self.audio_export_button.setEnabled(False)
        speech_layout.addWidget(self.audio_export_button)
        audio_layout.addWidget(speech_group)

        ambience_group = QGroupBox("Brückenatmosphäre")
        ambience_layout = QVBoxLayout(ambience_group)
        self.background_check = QCheckBox("Hintergrundsound während des Vorlesens und im Gesamtpaket")
        self.background_check.setChecked(True)
        self.background_check.stateChanged.connect(self._update_tab_status_summaries)
        ambience_layout.addWidget(self.background_check)
        ambience_volume_row = QHBoxLayout()
        ambience_volume_row.addWidget(QLabel("Lautstärke Hintergrund"))
        self.background_volume = QSlider(Qt.Orientation.Horizontal)
        self.background_volume.setRange(0, 100)
        self.background_volume.setValue(18)
        self.background_volume.valueChanged.connect(lambda value: self.background_effect.setVolume(value / 100.0))
        self.background_volume.valueChanged.connect(self._update_tab_status_summaries)
        ambience_volume_row.addWidget(self.background_volume, 1)
        ambience_layout.addLayout(ambience_volume_row)
        audio_layout.addWidget(ambience_group)
        audio_layout.addStretch(1)
        self.main_tabs.addTab(audio_scroll, "Sprache && Audio")

        # ------------------------------------------------------------------
        # Tab 4: Sprachmanager / zusätzliche lokale TTS-Pakete
        # ------------------------------------------------------------------
        manager_scroll, manager_page, manager_layout = make_scroll_page("ttsManagerPage")
        manager_hero = QFrame()
        manager_hero.setObjectName("heroCard")
        manager_hero_layout = QVBoxLayout(manager_hero)
        manager_title = QLabel("Zusätzliche Sprachausgabe-Komplettpakete")
        manager_title.setObjectName("sectionHeroTitle")
        manager_intro = QLabel(
            "Hier können zusätzliche lokale TTS-Stimmen vollständig in den Programmordner installiert werden. "
            "Ein Komplettpaket enthält bzw. beschafft automatisch Laufzeit, Bibliotheken und Sprachmodell. "
            "Bereits vorhandene Piper-Dateien in Programm-Unterordnern, benachbarten Projektordnern oder Downloads "
            "werden geprüft und kopiert, bevor etwas erneut heruntergeladen wird."
        )
        manager_intro.setWordWrap(True)
        manager_hero_layout.addWidget(manager_title)
        manager_hero_layout.addWidget(manager_intro)
        manager_layout.addWidget(manager_hero)

        manager_group = QGroupBox("Verfügbare Komplettpakete")
        manager_group_layout = QVBoxLayout(manager_group)
        self.tts_package_table = QTableWidget(0, 5)
        self.tts_package_table.setHorizontalHeaderLabels(["Stimme", "Engine", "Qualität", "Größe", "Status"])
        self.tts_package_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tts_package_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tts_package_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tts_package_table.verticalHeader().setVisible(False)
        package_header = self.tts_package_table.horizontalHeader()
        # Sprachpakete sollen sich wie eine echte Verwaltungs-Tabelle verhalten:
        # Spaltenbreiten koennen per Trenner angepasst, komplette Spalten per Drag & Drop
        # verschoben und alle Kategorien per Klick auf den Kopf sortiert werden.
        package_header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        package_header.setSectionsMovable(True)
        package_header.setSectionsClickable(True)
        package_header.setSortIndicatorShown(True)
        package_header.setToolTip(
            "Spaltenkopf anklicken: sortieren · erneut anklicken: Reihenfolge umkehren · "
            "Spaltenkopf ziehen: umordnen · Trenner ziehen: Breite ändern"
        )
        package_header.setMinimumSectionSize(70)
        package_header.setStretchLastSection(False)
        for column, width in enumerate((500, 90, 180, 160, 120)):
            self.tts_package_table.setColumnWidth(column, width)
        self.tts_package_table.setSortingEnabled(True)
        self.tts_package_table.sortItems(0, Qt.SortOrder.AscendingOrder)
        self.tts_package_table.itemSelectionChanged.connect(self._tts_package_selection_changed)
        manager_group_layout.addWidget(self.tts_package_table)

        self.tts_package_details = QLabel()
        self.tts_package_details.setObjectName("infoCard")
        self.tts_package_details.setWordWrap(True)
        manager_group_layout.addWidget(self.tts_package_details)

        manager_buttons = QHBoxLayout()
        self.tts_package_install_button = QPushButton("Komplettpaket installieren / reparieren")
        self.tts_package_install_button.setObjectName("primaryAction")
        self.tts_package_install_button.clicked.connect(self.install_selected_tts_package)
        self.tts_package_remove_button = QPushButton("Paket entfernen")
        self.tts_package_remove_button.clicked.connect(self.remove_selected_tts_package)
        self.tts_package_folder_button = QPushButton("Paketordner öffnen")
        self.tts_package_folder_button.clicked.connect(self.open_selected_tts_package_folder)
        self.tts_package_rescan_button = QPushButton("Pakete und Stimmen neu scannen")
        self.tts_package_rescan_button.clicked.connect(self.refresh_tts_packages)
        manager_buttons.addWidget(self.tts_package_install_button, 2)
        manager_buttons.addWidget(self.tts_package_remove_button)
        manager_buttons.addWidget(self.tts_package_folder_button)
        manager_buttons.addWidget(self.tts_package_rescan_button)
        manager_group_layout.addLayout(manager_buttons)

        self.tts_package_progress = QProgressBar()
        self.tts_package_progress.setRange(0, 100)
        self.tts_package_progress.setValue(0)
        self.tts_package_progress.setFormat("Bereit")
        manager_group_layout.addWidget(self.tts_package_progress)
        manager_layout.addWidget(manager_group)

        manager_note = QLabel(
            "Aktuell kuratiert der Sprachmanager deutsche Piper-Stimmen. Die Haupt-Sprachauswahl zeigt weiterhin nur "
            "Stimmen an, die auf diesem Rechner wirklich vorhanden sind: Windows/Qt-Stimmen sowie vollständig installierte "
            "Piper-Pakete. Der Paketkatalog liegt extern in tts_package_catalog.json und kann später um weitere lokale TTS-Engines erweitert werden."
        )
        manager_note.setObjectName("workflowStatus")
        manager_note.setWordWrap(True)
        manager_layout.addWidget(manager_note)
        manager_layout.addStretch(1)
        self.tts_manager_tab_index = self.main_tabs.addTab(manager_scroll, "Sprachmanager")
        self._populate_tts_package_table()

        # ------------------------------------------------------------------
        # Tab 5: Story & Trace
        # ------------------------------------------------------------------
        details_page = QWidget()
        details_layout = QVBoxLayout(details_page)
        details_layout.setContentsMargins(12, 10, 12, 12)
        details_layout.setSpacing(8)
        details_top = QHBoxLayout()
        details_caption = QLabel("Story, Herkunft der Satzteile und erzeugter Produktionsauftrag")
        details_caption.setObjectName("mutedText")
        back_mission = QPushButton("Zur Mission")
        back_mission.clicked.connect(lambda: self.main_tabs.setCurrentIndex(0))
        details_top.addWidget(details_caption, 1)
        details_top.addWidget(back_mission)
        details_layout.addLayout(details_top)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("detailTabs")
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
        self.prompts_edit.setPlaceholderText("Hier erscheinen Bild-Prompts oder der Gesamtpaket-Produktionsauftrag …")
        self.tabs.addTab(self.story_edit, "Story")
        self.tabs.addTab(self.log_edit, "Auswahlprotokoll / Trace")
        self.tabs.addTab(self.prompts_edit, "Prompts / Produktion")
        details_layout.addWidget(self.tabs, 1)
        self.details_page = details_page
        self.details_tab_index = self.main_tabs.addTab(details_page, "Story && Trace")

        # ------------------------------------------------------------------
        # Tab 6: Einstellungen
        # ------------------------------------------------------------------
        settings_scroll, settings_page, settings_layout = make_scroll_page("settingsPage")
        options_group = QGroupBox("Storygenerierung")
        options_layout = QVBoxLayout(options_group)
        self.legacy_umlauts = QCheckBox("Legacy-Umlautkonvertierung (ae/ue/oe)")
        self.legacy_umlauts.setChecked(True)
        self.ignore_blanks = QCheckBox("Leere Zeilen in Satzdateien ignorieren")
        self.ignore_blanks.setChecked(True)
        self.write_log = QCheckBox("Protokolldatei automatisch speichern")
        self.write_log.setChecked(True)
        self.runtime_error_log = QCheckBox("Erweitertes Laufzeit-Fehlerprotokoll schreiben")
        self.runtime_error_log.setToolTip(
            "Schreibt bei aktivierter Option einen fortlaufenden Diagnose-Log mit Bedienpfad, "
            "Stimmenwechseln, TTS-Zuständen und Python-Fehlern in den logs-Ordner. "
            "Hilfreich bei sporadischen Abstürzen."
        )
        self.runtime_error_log.toggled.connect(self._runtime_diagnostics_toggled)
        options_layout.addWidget(self.legacy_umlauts)
        options_layout.addWidget(self.ignore_blanks)
        options_layout.addWidget(self.write_log)
        options_layout.addWidget(self.runtime_error_log)
        seed_form = QFormLayout()
        self.seed_spin = QSpinBox()
        self.seed_spin.setRange(0, 2_147_483_647)
        self.seed_spin.setSpecialValueText("Zufällig")
        self.seed_spin.setValue(0)
        self.seed_spin.valueChanged.connect(self._update_tab_status_summaries)
        self.write_log.stateChanged.connect(self._update_tab_status_summaries)
        self.runtime_error_log.stateChanged.connect(self._update_tab_status_summaries)
        self.legacy_umlauts.stateChanged.connect(self._update_tab_status_summaries)
        seed_form.addRow("Seed:", self.seed_spin)
        options_layout.addLayout(seed_form)
        settings_layout.addWidget(options_group)

        theme_group = QGroupBox("Darstellung")
        theme_form = QFormLayout(theme_group)
        self.theme_combo = QComboBox()
        self.theme_combo.currentTextChanged.connect(self.apply_theme)
        self.theme_combo.currentTextChanged.connect(self._update_tab_status_summaries)
        theme_form.addRow("Theme:", self.theme_combo)
        settings_layout.addWidget(theme_group)

        speech_settings_group = QGroupBox("Sprachoptionen")
        speech_settings_layout = QVBoxLayout(speech_settings_group)
        self.mls_aliases_check = QCheckBox("Fiktive Merknamen für MLS-Sprecher anzeigen (optional)")
        self.mls_aliases_check.setChecked(False)
        self.mls_aliases_check.setToolTip(
            "Optional: Zeigt für die 236 MLS-Sprecher stabile, frei erfundene Vornamen als Merkhilfe. "
            "Die Aliasnamen sind nicht die echten Namen und werden derzeit nicht zur Geschlechtsangabe verwendet. "
            "Die Option ist bei einer frischen Konfiguration standardmäßig ausgeschaltet."
        )
        self.mls_aliases_check.toggled.connect(self._mls_alias_setting_changed)
        speech_settings_layout.addWidget(self.mls_aliases_check)
        alias_info = QLabel(
            "Standardmäßig werden nur Sprecherposition und MLS-ID angezeigt. Die optionalen Aliasnamen stehen in "
            "data/mls_speaker_aliases.json und dienen ausschließlich als Merkhilfe; eine gespeicherte Konfiguration kann "
            "die Anzeige weiterhin bewusst aktivieren."
        )
        alias_info.setWordWrap(True)
        alias_info.setObjectName("mutedText")
        speech_settings_layout.addWidget(alias_info)
        settings_layout.addWidget(speech_settings_group)

        profile_group = QGroupBox("Konfigurationsprofile")
        profile_layout = QVBoxLayout(profile_group)
        profile_info = QLabel(
            "Die aktuellen Einstellungen werden automatisch lokal gespeichert. Zusätzlich kannst du vollständige Konfigurationsprofile als JSON sichern, austauschen und später wieder laden."
        )
        profile_info.setWordWrap(True)
        profile_layout.addWidget(profile_info)
        profile_buttons = QHBoxLayout()
        self.export_config_button = QPushButton("Konfiguration speichern …")
        self.export_config_button.clicked.connect(self.save_configuration_profile)
        self.import_config_button = QPushButton("Konfiguration laden …")
        self.import_config_button.clicked.connect(self.load_configuration_profile)
        profile_buttons.addWidget(self.export_config_button)
        profile_buttons.addWidget(self.import_config_button)
        profile_layout.addLayout(profile_buttons)
        settings_layout.addWidget(profile_group)

        utility_group = QGroupBox("Dateien")
        utility_layout = QGridLayout(utility_group)
        self.save_button = QPushButton("Story speichern …")
        self.save_button.clicked.connect(self.save_story)
        self.clear_button = QPushButton("Text löschen")
        self.clear_button.clicked.connect(self.clear_story)
        open_vars_button = QPushButton("Satzteil-Ordner öffnen")
        open_vars_button.clicked.connect(lambda: self._open_path(VARS_DIR))
        open_logs_button = QPushButton("Log-Ordner öffnen")
        open_logs_button.clicked.connect(lambda: self._open_path(LOG_DIR))
        utility_layout.addWidget(self.save_button, 0, 0)
        utility_layout.addWidget(self.clear_button, 0, 1)
        utility_layout.addWidget(open_vars_button, 1, 0)
        utility_layout.addWidget(open_logs_button, 1, 1)
        settings_layout.addWidget(utility_group)
        settings_layout.addStretch(1)
        self.main_tabs.addTab(settings_scroll, "Einstellungen")

        # Persistent status strip
        status_frame = QFrame()
        status_frame.setObjectName("statusStrip")
        status_layout = QHBoxLayout(status_frame)
        status_layout.setContentsMargins(10, 6, 10, 6)
        status_layout.setSpacing(10)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setMaximumWidth(260)
        self.status_label = QLabel("Bereit.")
        self.status_label.setWordWrap(True)
        status_layout.addWidget(self.progress)
        status_layout.addWidget(self.status_label, 1)
        root.addWidget(status_frame)

        self._populate_theme_combo()
        self._build_menus()
        self._update_storyboard_mode_controls()
        self._update_video_resolution_controls()
        self._update_target_ai_controls()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_ui_scale_timer"):
            self._ui_scale_timer.start()

    def _calculate_ui_scale(self) -> float:
        if self.centralWidget() is None:
            return 1.0
        width_ratio = max(1.0, self.centralWidget().width() / BASE_CONTROL_VIEWPORT_WIDTH)
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

        margin = round(10 * scale)
        self.root_layout.setContentsMargins(margin, margin, margin, margin)
        self.root_layout.setSpacing(round(10 * scale))
        self.controls_layout.setSpacing(round(12 * scale))

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
        tts_manager_action = QAction("Sprachmanager öffnen", self)
        tts_manager_action.triggered.connect(lambda: self.main_tabs.setCurrentIndex(self.tts_manager_tab_index))
        view_menu.addAction(tts_manager_action)
        toggle_action = QAction("Story && Trace anzeigen / zur Mission zurück", self)
        toggle_action.triggered.connect(self.toggle_story_panel)
        view_menu.addAction(toggle_action)
        view_menu.addSeparator()
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
        if not STYLE_REFERENCE_FILE.is_file():
            self.generate_prompts_button.setEnabled(False)
            self.storyboard_info_label.setText(
                "Die Stilreferenz handoff_assets/style_reference.png fehlt; Gesamtpakete können nicht vollständig erzeugt werden."
            )
        if not self.prompt_profile_manager.profiles:
            self.generate_prompts_button.setEnabled(False)
            self.storyboard_info_label.setText(
                "Keine gültigen Ziel-KI-Promptprofile gefunden. Bitte den Ordner prompt_profiles prüfen."
            )

    def toggle_story_panel(self) -> None:
        if not hasattr(self, "main_tabs"):
            return
        if self.main_tabs.currentIndex() == self.details_tab_index:
            self.main_tabs.setCurrentIndex(0)
        else:
            self.main_tabs.setCurrentIndex(self.details_tab_index)
            self.tabs.setCurrentWidget(self.story_edit)

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

    def _refresh_piper_voice_catalog(self, *, rebuild: bool = True) -> None:
        try:
            self.voice_catalogs["piper"] = self.tts_package_manager.installed_voices()
        except Exception as exc:
            self.voice_catalogs["piper"] = []
            self._voice_service_error(f"Piper-Sprachpakete konnten nicht eingelesen werden: {exc}")
        if rebuild and hasattr(self, "voice_combo"):
            self._rebuild_voice_combo()

    def _populate_tts_package_table(self) -> None:
        if not hasattr(self, "tts_package_table"):
            return
        header = self.tts_package_table.horizontalHeader()
        sort_column = header.sortIndicatorSection()
        sort_order = header.sortIndicatorOrder()
        sorting_enabled = self.tts_package_table.isSortingEnabled()
        self.tts_package_table.setSortingEnabled(False)
        self.tts_package_table.setRowCount(0)
        for definition in self.tts_package_manager.packages:
            row = self.tts_package_table.rowCount()
            self.tts_package_table.insertRow(row)
            size_text = f"{definition.model_bytes / 1048576:.0f} MiB + Runtime" if definition.model_bytes else "Runtime + Modell"
            values = (
                definition.display_name,
                "Piper",
                definition.quality,
                size_text,
                self.tts_package_manager.status_text(definition),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, definition.package_id)
                self.tts_package_table.setItem(row, column, item)
        self.tts_package_table.setSortingEnabled(sorting_enabled)
        if sorting_enabled and 0 <= sort_column < self.tts_package_table.columnCount():
            self.tts_package_table.sortItems(sort_column, sort_order)
        if self.tts_package_table.rowCount():
            self.tts_package_table.selectRow(0)
        else:
            self.tts_package_details.setText(
                "Der TTS-Paketkatalog ist leer oder ungültig. "
                + " ".join(self.tts_package_manager.catalog_errors)
            )
        self._tts_package_selection_changed()

    def _selected_tts_package_id(self) -> str:
        row = self.tts_package_table.currentRow() if hasattr(self, "tts_package_table") else -1
        if row < 0:
            return ""
        item = self.tts_package_table.item(row, 0)
        return str(item.data(Qt.ItemDataRole.UserRole) or "") if item is not None else ""

    def _tts_package_selection_changed(self) -> None:
        package_id = self._selected_tts_package_id()
        definition = self.tts_package_manager.package(package_id) if package_id else None
        if definition is None:
            self.tts_package_details.setText("Kein Sprachpaket ausgewählt.")
            self.tts_package_install_button.setEnabled(False)
            self.tts_package_remove_button.setEnabled(False)
            self.tts_package_folder_button.setEnabled(False)
            return
        installed = self.tts_package_manager.is_installed(package_id)
        supported = self.tts_package_manager.package_supported(definition)
        engine = self.tts_package_manager.engines.get(definition.engine_id, {})
        self.tts_package_details.setText(
            f"{definition.display_name} · {definition.language} · Qualität: {definition.quality} · "
            f"Stimmwirkung: {definition.gender_hint or 'nicht angegeben'}\n"
            f"Engine: {engine.get('name', definition.engine_id)} · Status: {self.tts_package_manager.status_text(definition)}\n"
            f"Quelle: {definition.source_url}\n"
            "Installation erfolgt vollständig lokal unter tts_packages/. Bereits vorhandene passende Dateien werden vor einem Download wiederverwendet."
        )
        busy = self._tts_package_thread is not None
        self.tts_package_install_button.setEnabled(supported and not busy)
        self.tts_package_remove_button.setEnabled(installed and not busy)
        self.tts_package_folder_button.setEnabled(installed and self.tts_package_manager.package_dir(package_id).exists())

    def refresh_tts_packages(self) -> None:
        self.tts_package_manager.reload_catalog()
        self._populate_tts_package_table()
        self._refresh_piper_voice_catalog()
        self.status_label.setText(
            f"Sprachmanager aktualisiert — {len(self.voice_catalogs['piper'])} installierte Piper-Stimmvarianten verfügbar."
        )

    def _start_tts_package_action(self, package_id: str, action: str) -> None:
        if self._tts_package_thread is not None:
            self.status_label.setText("Ein Sprachpaket-Vorgang läuft bereits.")
            return
        definition = self.tts_package_manager.package(package_id)
        if definition is None:
            return
        thread = QThread(self)
        worker = TtsPackageWorker(self.tts_package_manager, package_id, action)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._tts_package_progress_changed)
        worker.finished.connect(self._tts_package_action_finished)
        worker.error.connect(self._tts_package_action_failed)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.error.connect(worker.deleteLater)
        thread.finished.connect(self._tts_package_thread_finished)
        self._tts_package_thread = thread
        self._tts_package_worker = worker
        self.tts_package_progress.setValue(0)
        self.tts_package_progress.setFormat("Wird vorbereitet …")
        self._tts_package_selection_changed()
        self.status_label.setText(
            f"{'Installiere' if action == 'install' else 'Entferne'} Sprachpaket {definition.display_name} …"
        )
        thread.start()

    def install_selected_tts_package(self) -> None:
        package_id = self._selected_tts_package_id()
        if package_id:
            self._start_tts_package_action(package_id, "install")

    def remove_selected_tts_package(self) -> None:
        package_id = self._selected_tts_package_id()
        definition = self.tts_package_manager.package(package_id) if package_id else None
        if definition is None:
            return
        answer = QMessageBox.question(
            self,
            "Sprachpaket entfernen",
            f"Soll das lokale Sprachmodell „{definition.display_name}“ entfernt werden?\n\n"
            "Die gemeinsam genutzte Piper-Laufzeit und der Download-Cache bleiben erhalten, damit andere Stimmen weiterhin funktionieren und spätere Installationen nichts unnötig erneut laden.",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._start_tts_package_action(package_id, "remove")

    def open_selected_tts_package_folder(self) -> None:
        package_id = self._selected_tts_package_id()
        if package_id:
            self._open_path(self.tts_package_manager.package_dir(package_id))

    def _tts_package_progress_changed(self, value: int, message: str) -> None:
        self.tts_package_progress.setValue(max(0, min(100, value)))
        self.tts_package_progress.setFormat(message)
        self.status_label.setText(message)

    def _tts_package_action_finished(self, package_id: str, action: str) -> None:
        definition = self.tts_package_manager.package(package_id)
        name = definition.display_name if definition else package_id
        self.tts_package_progress.setValue(100)
        self.tts_package_progress.setFormat("Installiert" if action == "installed" else "Entfernt")
        self._populate_tts_package_table()
        self._refresh_piper_voice_catalog()
        self.status_label.setText(
            f"Sprachpaket {name} {'ist einsatzbereit' if action == 'installed' else 'wurde entfernt'}."
        )

    def _tts_package_action_failed(self, message: str) -> None:
        self.tts_package_progress.setFormat("Fehler")
        self.status_label.setText("Sprachpaket-Vorgang fehlgeschlagen.")
        QMessageBox.critical(self, "Sprachmanager", message)

    def _tts_package_thread_finished(self) -> None:
        thread = self._tts_package_thread
        self._tts_package_thread = None
        self._tts_package_worker = None
        if thread is not None:
            thread.deleteLater()
        self._populate_tts_package_table()
        self._tts_package_selection_changed()

    def refresh_voices(self) -> None:
        self.voice_diagnostics.clear()
        self.voice_count_label.setText("Stimmen werden neu eingelesen …")
        self._load_qt_voices()
        self.voice_catalogs["winrt"] = []
        self.voice_catalogs["sapi"] = []
        self._refresh_piper_voice_catalog(rebuild=False)
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
        for backend in ("winrt", "sapi", "qt", "piper"):
            for entry in self.voice_catalogs[backend]:
                locale = f" — {entry['locale']}" if entry.get("locale") else ""
                self.voice_combo.addItem(f"{entry['name']}{locale} [{BACKEND_LABELS[backend]}]", entry)
                total += 1
        self.voice_combo.blockSignals(False)

        target_key = self._pending_saved_voice_key or current_key or (self.saved_voice_backend + "|" + self.saved_voice_id)
        selected = -1
        if target_key != "|":
            for index in range(self.voice_combo.count()):
                entry = self.voice_combo.itemData(index)
                if entry and entry.get("backend", "") + "|" + entry.get("id", "") == target_key:
                    selected = index
                    break
        # v60.18/v60.19 exposed Thorsten Emotional styles as separate voice IDs
        # such as package:4. v60.20 keeps one voice entry and shows the style in
        # a dedicated selector, so migrate the old saved ID automatically.
        if selected < 0 and self.saved_voice_backend == "piper" and ":" in self.saved_voice_id:
            legacy_package_id, legacy_speaker_text = self.saved_voice_id.split(":", 1)
            try:
                legacy_speaker_id = int(legacy_speaker_text)
            except ValueError:
                legacy_speaker_id = None
            for index in range(self.voice_combo.count()):
                entry = self.voice_combo.itemData(index) or {}
                if entry.get("backend") == "piper" and entry.get("package_id") == legacy_package_id:
                    selected = index
                    if legacy_speaker_id is not None:
                        for option in entry.get("speaker_options") or []:
                            if int(option.get("id", -1)) == legacy_speaker_id:
                                self.saved_piper_speakers[legacy_package_id] = str(option.get("name", ""))
                                break
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
            selected_entry = self.voice_combo.itemData(selected) or {}
            selected_key = selected_entry.get("backend", "") + "|" + selected_entry.get("id", "")
            self.voice_combo.setCurrentIndex(selected)
            self._voice_changed(selected)
            if self._pending_saved_voice_key and selected_key == self._pending_saved_voice_key:
                self._pending_saved_voice_key = ""

        counts = [f"{BACKEND_LABELS[key]}: {len(self.voice_catalogs[key])}" for key in ("winrt", "sapi", "qt", "piper")]
        self.voice_count_label.setText(f"{total} Einträge — " + ", ".join(counts))
        self.execute_button.setEnabled(bool(total) and not self.playback_active)
        self.audio_export_button.setEnabled(bool(self.result and total) and self._export_thread is None)

    def _mls_alias_for_speaker(self, speaker_id: int) -> str:
        return self.mls_speaker_aliases.get(int(speaker_id), "")

    def _format_large_piper_speaker_name(self, entry: dict, option: dict, row: int) -> str:
        raw_name = str(option.get("name", ""))
        speaker_id = int(option.get("id", row))
        numeric_label = f"Sprecher {speaker_id + 1:03d}"
        if str(entry.get("package_id", "")) == "piper-de-mls-medium" and raw_name.isdigit():
            alias = self._mls_alias_for_speaker(speaker_id) if self.mls_aliases_check.isChecked() else ""
            if alias:
                return f"{alias} — {numeric_label} · MLS-ID {raw_name}"
            return f"{numeric_label} — MLS-ID {raw_name}"
        if raw_name:
            return f"{numeric_label} — {raw_name}"
        return numeric_label

    def _mls_alias_setting_changed(self, _checked: bool) -> None:
        entry = self.voice_combo.currentData() or {}
        if entry.get("backend") == "piper" and self._piper_uses_speaker_list(entry):
            selected_name = self._current_piper_style_name(entry)
            if entry.get("package_id") and selected_name:
                self.saved_piper_speakers[str(entry["package_id"])] = selected_name
            self._refresh_piper_option_controls(entry)
        self._schedule_settings_save()

    def _piper_prosody_values(self) -> tuple[float | None, float | None]:
        key = str(self.piper_prosody_combo.currentData() or "stable")
        for _label, preset_key, noise_scale, noise_w in PIPER_PROSODY_PRESETS:
            if preset_key == key:
                return noise_scale, noise_w
        return 0.45, 0.35

    def _piper_uses_speaker_list(self, entry: dict | None = None) -> bool:
        entry = entry or (self.voice_combo.currentData() or {})
        return bool(entry.get("speaker_selector") and len(entry.get("speaker_options") or []) > 32)

    def _current_piper_selector_value(self, entry: dict | None = None) -> dict | None:
        entry = entry or (self.voice_combo.currentData() or {})
        if entry.get("backend") != "piper" or not entry.get("speaker_selector"):
            return None
        if self._piper_uses_speaker_list(entry):
            item = self.piper_speaker_list.currentItem()
            if item is not None:
                value = item.data(Qt.ItemDataRole.UserRole)
                return value if isinstance(value, dict) else None
        elif self.piper_style_combo.count():
            value = self.piper_style_combo.currentData()
            return value if isinstance(value, dict) else None
        return None

    def _current_piper_speaker_id(self, entry: dict | None = None) -> int | None:
        entry = entry or (self.voice_combo.currentData() or {})
        if entry.get("backend") != "piper":
            return None
        value = self._current_piper_selector_value(entry)
        if value and value.get("id") is not None:
            return int(value["id"])
        raw_id = entry.get("speaker_id")
        return int(raw_id) if raw_id is not None else None

    def _current_piper_style_name(self, entry: dict | None = None) -> str:
        entry = entry or (self.voice_combo.currentData() or {})
        if entry.get("backend") != "piper":
            return ""
        value = self._current_piper_selector_value(entry)
        if value:
            return str(value.get("name", ""))
        return str(entry.get("speaker_name", ""))

    def _voice_with_piper_options(self, entry: dict) -> dict:
        resolved = dict(entry)
        if resolved.get("backend") == "piper":
            resolved["speaker_id"] = self._current_piper_speaker_id(resolved)
            resolved["speaker_name"] = self._current_piper_style_name(resolved)
        return resolved

    def _piper_style_changed(self, _index: int) -> None:
        entry = self.voice_combo.currentData() or {}
        if entry.get("backend") == "piper" and entry.get("package_id"):
            style_name = self._current_piper_style_name(entry)
            if style_name:
                self.saved_piper_speakers[str(entry["package_id"])] = style_name
        self._update_tab_status_summaries()

    def _refresh_piper_option_controls(self, entry: dict) -> None:
        is_piper = entry.get("backend") == "piper"
        self.piper_options_group.setVisible(is_piper)
        if not is_piper:
            return

        options = list(entry.get("speaker_options") or [])
        has_selector = bool(entry.get("speaker_selector") and options)
        list_mode = bool(has_selector and len(options) > 32)

        self.piper_style_label.setVisible(has_selector and not list_mode)
        self.piper_style_combo.setVisible(has_selector and not list_mode)
        self.piper_speaker_list_label.setVisible(list_mode)
        self.piper_speaker_list.setVisible(list_mode)
        self.piper_speaker_list_hint.setVisible(list_mode)

        if not has_selector:
            self.piper_style_combo.clear()
            self.piper_speaker_list.clear()
            return

        package_id = str(entry.get("package_id", ""))
        desired_name = self.saved_piper_speakers.get(package_id, str(entry.get("speaker_name", "")))
        selector_label = str(entry.get("speaker_selector_label") or "Sprecher / Stil") + ":"

        if list_mode:
            self.piper_speaker_list_label.setText(selector_label)
            self.piper_speaker_list.blockSignals(True)
            self.piper_speaker_list.clear()
            selected_row = -1
            for row, option in enumerate(options):
                raw_name = str(option.get("name", ""))
                display_name = self._format_large_piper_speaker_name(entry, option, row)
                self.piper_speaker_list.addItem(display_name)
                item = self.piper_speaker_list.item(row)
                item.setData(Qt.ItemDataRole.UserRole, option)
                if raw_name == desired_name:
                    selected_row = row
            if selected_row < 0 and options:
                selected_row = 0
            if selected_row >= 0:
                self.piper_speaker_list.setCurrentRow(selected_row)
                self.piper_speaker_list.scrollToItem(self.piper_speaker_list.item(selected_row))
            self.piper_speaker_list.blockSignals(False)
            self.piper_style_combo.clear()
            return

        self.piper_style_label.setText(selector_label)
        self.piper_style_combo.blockSignals(True)
        self.piper_style_combo.clear()
        selected = -1
        for option in options:
            raw_name = str(option.get("name", ""))
            display_name = PIPER_STYLE_LABELS.get(raw_name, raw_name.replace("_", " ").title())
            self.piper_style_combo.addItem(display_name, option)
            if raw_name == desired_name:
                selected = self.piper_style_combo.count() - 1
        if selected < 0:
            for i in range(self.piper_style_combo.count()):
                data = self.piper_style_combo.itemData(i) or {}
                if data.get("name") == "neutral":
                    selected = i
                    break
        self.piper_style_combo.setCurrentIndex(max(0, selected))
        self.piper_style_combo.blockSignals(False)
        self.piper_speaker_list.clear()

    def _voice_user_activated(self, index: int) -> None:
        """Record an explicit user choice and cancel any deferred startup restoration."""
        entry = self.voice_combo.itemData(index) or {}
        if not entry:
            return
        self._pending_saved_voice_key = ""
        self.saved_voice_backend = str(entry.get("backend", ""))
        self.saved_voice_id = str(entry.get("id", ""))
        self.saved_voice_name = str(entry.get("name", ""))
        self._schedule_settings_save()

    def _voice_changed(self, index: int) -> None:
        if index < 0:
            self.piper_options_group.setVisible(False)
            return
        entry = self.voice_combo.itemData(index)
        if not entry:
            self.piper_options_group.setVisible(False)
            return
        # Switching voices while Piper/WinRT is still synthesizing used to race
        # against QProcess.finished. Stop/cancel the old request first.
        if self.playback_active:
            self.runtime_diagnostics.breadcrumb(
                "voice_change_while_active", old_backend=self.active_backend, new_backend=entry.get("backend"),
                new_voice=entry.get("name")
            )
            self.stop_playback()
        self.runtime_diagnostics.breadcrumb(
            "voice_changed", backend=entry.get("backend"), voice=entry.get("name"), voice_id=entry.get("id")
        )
        if entry.get("backend") == "qt":
            voice = self.qt_voice_objects.get(entry.get("id", ""))
            if voice is not None:
                self.qt_tts.setVoice(voice)
        self._refresh_piper_option_controls(entry)
        self._update_tab_status_summaries()

    def _voice_service_error(self, message: str) -> None:
        if message not in self.voice_diagnostics:
            self.voice_diagnostics.append(message)
        self.runtime_diagnostics.breadcrumb(
            "tts_service_error", backend=self.active_backend or "none", message=message
        )
        self.status_label.setText(message)

    def _runtime_diagnostics_toggled(self, enabled: bool) -> None:
        if enabled:
            path = self.runtime_diagnostics.enable()
            if path is not None and hasattr(self, "status_label"):
                self.status_label.setText(f"Laufzeit-Diagnose aktiv: {path.name}")
        else:
            self.runtime_diagnostics.disable()

    def _handle_uncaught_exception(self, exc_type, exc_value, exc_traceback) -> None:
        try:
            if isinstance(exc_value, BaseException):
                self.runtime_diagnostics.log_exception("uncaught_python_exception", exc_value)
        finally:
            self._previous_excepthook(exc_type, exc_value, exc_traceback)

    def show_voice_diagnostics(self) -> None:
        lines = [f"{APP_NAME} v{APP_VERSION}", "", "Gefundene Stimmen:"]
        for backend in ("winrt", "sapi", "qt", "piper"):
            lines.append(f"\n{BACKEND_LABELS[backend]} ({len(self.voice_catalogs[backend])})")
            for entry in self.voice_catalogs[backend]:
                locale = f" / {entry.get('locale')}" if entry.get("locale") else ""
                lines.append(f"  • {entry.get('name')}{locale}")
        lines.append("\nSprachmanager:")
        lines.extend(f"  • {item}" for item in self.tts_package_manager.diagnostics())
        if self.voice_diagnostics:
            lines.append("\nHinweise/Fehler:")
            lines.extend(f"  • {item}" for item in self.voice_diagnostics)
        QMessageBox.information(self, "TTS-Stimmendiagnose", "\n".join(lines))

    @staticmethod
    def _setting_int(settings: dict, key: str, default: int) -> int:
        try:
            return int(settings.get(key, default))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _setting_float(settings: dict, key: str, default: float) -> float:
        try:
            return float(settings.get(key, default))
        except (TypeError, ValueError):
            return default

    def _apply_settings_dict(self, settings: dict) -> None:
        """Apply a local settings file or an imported configuration profile safely."""
        if not isinstance(settings, dict):
            settings = {}
        was_loaded = self._settings_loaded
        self._settings_loaded = False
        try:
            self.rate_slider.setValue(self._setting_int(settings, "rate", 0))
            self.voice_volume.setValue(self._setting_int(settings, "voice_volume", 100))
            self.background_volume.setValue(self._setting_int(settings, "background_volume", 18))
            self.background_check.setChecked(bool(settings.get("background", True)) and SOUND_FILE.is_file())
            self.write_log.setChecked(bool(settings.get("write_log", True)))
            self.runtime_error_log.setChecked(bool(settings.get("runtime_error_log", False)))
            self.legacy_umlauts.setChecked(bool(settings.get("legacy_umlauts", True)))
            self.ignore_blanks.setChecked(bool(settings.get("ignore_blanks", True)))
            self.seed_spin.setValue(self._setting_int(settings, "seed", 0))
            self.mls_aliases_check.setChecked(bool(settings.get("mls_speaker_aliases", False)))

            self.saved_voice_backend = str(settings.get("voice_backend", ""))
            self.saved_voice_id = str(settings.get("voice_id", ""))
            self.saved_voice_name = str(settings.get("voice_name", ""))
            self._pending_saved_voice_key = (
                self.saved_voice_backend + "|" + self.saved_voice_id
                if self.saved_voice_backend and self.saved_voice_id else ""
            )
            raw_piper_speakers = settings.get("piper_speaker_selection", {})
            self.saved_piper_speakers = (
                {str(key): str(value) for key, value in raw_piper_speakers.items()}
                if isinstance(raw_piper_speakers, dict) else {}
            )
            self.saved_piper_prosody = str(settings.get("piper_prosody", "stable"))
            prosody_index = self.piper_prosody_combo.findData(self.saved_piper_prosody)
            self.piper_prosody_combo.setCurrentIndex(prosody_index if prosody_index >= 0 else 0)

            prompt_mode = str(settings.get("storyboard_mode", "Lokal (regelbasiert)"))
            if self.prompt_mode_combo.findText(prompt_mode) >= 0:
                self.prompt_mode_combo.setCurrentText(prompt_mode)

            output_kind = str(settings.get("storyboard_output_kind", "Gesamtpaket — fertiges Video mit TTS, Hintergrundsound und ZIP"))
            legacy_output_map = {
                "Bildserie": "Gesamtpaket — fertiges Video mit TTS, Hintergrundsound und ZIP",
                "Gesamtpaket (Bilder + Audio + Video)": "Gesamtpaket — fertiges Video mit TTS, Hintergrundsound und ZIP",
                "Gesamtpaket — Video + TTS + Hintergrundsound + ZIP": "Gesamtpaket — fertiges Video mit TTS, Hintergrundsound und ZIP",
            }
            output_kind = legacy_output_map.get(output_kind, output_kind)
            if self.output_kind_combo.findText(output_kind) >= 0:
                self.output_kind_combo.setCurrentText(output_kind)
            else:
                self.output_kind_combo.setCurrentIndex(0)

            self.custom_video_width_spin.setValue(self._setting_int(settings, "package_video_custom_width", 1024))
            self.custom_video_height_spin.setValue(self._setting_int(settings, "package_video_custom_height", 1024))
            resolution_label = str(settings.get("package_video_resolution_preset", "1024 × 1024 (1:1, Standard)"))
            resolution_index = self.video_resolution_combo.findText(resolution_label)
            self.video_resolution_combo.setCurrentIndex(resolution_index if resolution_index >= 0 else 1)

            saved_fps = self._setting_int(settings, "package_video_fps", 8)
            fps_index = next(
                (index for index in range(self.video_fps_combo.count()) if int(self.video_fps_combo.itemData(index)) == saved_fps),
                0,
            )
            self.video_fps_combo.setCurrentIndex(fps_index)
            self.transition_spin.setValue(self._setting_float(settings, "storyboard_transition_seconds", 0.8))

            for combo, key, default in (
                (self.package_voice_character_combo, "package_voice_character", "Menschlich / natürlich"),
                (self.package_voice_gender_combo, "package_voice_gender", "Weiblich"),
                (self.package_voice_quality_combo, "package_voice_quality", "Beste verfügbare Qualität"),
            ):
                value = str(settings.get(key, default))
                if combo.findText(value) >= 0:
                    combo.setCurrentText(value)

            self.result_include_images_check.setChecked(bool(settings.get("result_zip_include_images", True)))
            self.result_include_audio_check.setChecked(bool(settings.get("result_zip_include_audio", True)))
            self.result_include_clips_check.setChecked(bool(settings.get("result_zip_include_clips", False)))
            self.result_include_project_files_check.setChecked(bool(settings.get("result_zip_include_project_files", True)))

            target_ai = str(settings.get("storyboard_target_ai", "ChatGPT"))
            if target_ai in self.prompt_profile_manager.profiles:
                self.target_ai_combo.setCurrentText(target_ai)
            elif self.target_ai_combo.count():
                self.target_ai_combo.setCurrentIndex(0)
            self.custom_target_edit.setText(str(settings.get("storyboard_custom_target", "")))
            self.scene_count_spin.setValue(self._setting_int(settings, "storyboard_scene_count", 8))

            saved_ollama_model = str(settings.get("ollama_model", ""))
            if saved_ollama_model:
                if self.ollama_model_combo.findText(saved_ollama_model) < 0:
                    self.ollama_model_combo.addItem(saved_ollama_model)
                self.ollama_model_combo.setCurrentText(saved_ollama_model)

            theme = str(settings.get("theme", "Aurora"))
            if theme in self.theme_manager.themes:
                self.theme_combo.setCurrentText(theme)
            elif self.theme_combo.count():
                self.theme_combo.setCurrentIndex(0)
            self.apply_theme(self.theme_combo.currentText())
            self._apply_tts_manager_table_settings(settings)
            self._rebuild_voice_combo()
            self._update_tab_status_summaries()
        finally:
            self._settings_loaded = was_loaded

    def _apply_tts_manager_table_settings(self, settings: dict) -> None:
        if not hasattr(self, "tts_package_table"):
            return
        header = self.tts_package_table.horizontalHeader()
        column_count = self.tts_package_table.columnCount()

        widths = settings.get("tts_manager_column_widths", [])
        if isinstance(widths, list) and len(widths) == column_count:
            for logical_index, raw_width in enumerate(widths):
                try:
                    width = max(header.minimumSectionSize(), int(raw_width))
                except (TypeError, ValueError):
                    continue
                self.tts_package_table.setColumnWidth(logical_index, width)

        order = settings.get("tts_manager_column_order", [])
        if isinstance(order, list):
            try:
                logical_order = [int(value) for value in order]
            except (TypeError, ValueError):
                logical_order = []
            if sorted(logical_order) == list(range(column_count)):
                for target_visual, logical_index in enumerate(logical_order):
                    current_visual = header.visualIndex(logical_index)
                    if current_visual != target_visual:
                        header.moveSection(current_visual, target_visual)

        sort_column = self._setting_int(settings, "tts_manager_sort_column", 0)
        sort_order_name = str(settings.get("tts_manager_sort_order", "ascending")).lower()
        sort_order = (
            Qt.SortOrder.DescendingOrder
            if sort_order_name == "descending"
            else Qt.SortOrder.AscendingOrder
        )
        if 0 <= sort_column < column_count:
            self.tts_package_table.sortItems(sort_column, sort_order)

    def _tts_manager_table_settings(self) -> dict:
        if not hasattr(self, "tts_package_table"):
            return {}
        header = self.tts_package_table.horizontalHeader()
        column_count = self.tts_package_table.columnCount()
        sort_order = header.sortIndicatorOrder()
        return {
            "tts_manager_column_widths": [self.tts_package_table.columnWidth(i) for i in range(column_count)],
            "tts_manager_column_order": [header.logicalIndex(i) for i in range(column_count)],
            "tts_manager_sort_column": header.sortIndicatorSection(),
            "tts_manager_sort_order": (
                "descending" if sort_order == Qt.SortOrder.DescendingOrder else "ascending"
            ),
        }

    def _load_settings(self) -> None:
        try:
            settings = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            settings = {}
        self._apply_settings_dict(settings)

    def _collect_settings(self) -> dict:
        entry = self.voice_combo.currentData() or {}
        if entry.get("backend") == "piper" and entry.get("package_id"):
            selected_name = self._current_piper_style_name(entry)
            if selected_name:
                self.saved_piper_speakers[str(entry["package_id"])] = selected_name
        if self._pending_saved_voice_key:
            voice_backend = self.saved_voice_backend
            voice_id = self.saved_voice_id
            voice_name = self.saved_voice_name
        else:
            voice_backend = entry.get("backend", "")
            voice_id = entry.get("id", "")
            voice_name = entry.get("name", "")
        return {
            "app_version": APP_VERSION,
            "ui_layout_version": 7,
            "rate": self.rate_slider.value(),
            "voice_volume": self.voice_volume.value(),
            "background_volume": self.background_volume.value(),
            "background": self.background_check.isChecked(),
            "write_log": self.write_log.isChecked(),
            "runtime_error_log": self.runtime_error_log.isChecked(),
            "legacy_umlauts": self.legacy_umlauts.isChecked(),
            "ignore_blanks": self.ignore_blanks.isChecked(),
            "seed": self.seed_spin.value(),
            "mls_speaker_aliases": self.mls_aliases_check.isChecked(),
            "theme": self.theme_combo.currentText(),
            "voice_backend": voice_backend,
            "voice_id": voice_id,
            "voice_name": voice_name,
            "piper_speaker_selection": dict(self.saved_piper_speakers),
            "piper_prosody": str(self.piper_prosody_combo.currentData() or "stable"),
            "storyboard_mode": self.prompt_mode_combo.currentText(),
            "storyboard_output_kind": self.output_kind_combo.currentText(),
            "storyboard_transition_seconds": self.transition_spin.value(),
            "package_video_resolution_preset": self.video_resolution_combo.currentText(),
            "package_video_fps": int(self.video_fps_combo.currentData() or 8),
            "package_video_custom_width": self.custom_video_width_spin.value(),
            "package_video_custom_height": self.custom_video_height_spin.value(),
            "package_voice_character": self.package_voice_character_combo.currentText(),
            "package_voice_gender": self.package_voice_gender_combo.currentText(),
            "package_voice_quality": self.package_voice_quality_combo.currentText(),
            "result_zip_include_images": self.result_include_images_check.isChecked(),
            "result_zip_include_audio": self.result_include_audio_check.isChecked(),
            "result_zip_include_clips": self.result_include_clips_check.isChecked(),
            "result_zip_include_project_files": self.result_include_project_files_check.isChecked(),
            "storyboard_target_ai": self.target_ai_combo.currentText(),
            "storyboard_custom_target": self.custom_target_edit.text().strip(),
            "storyboard_scene_count": self.scene_count_spin.value(),
            "ollama_model": self.ollama_model_combo.currentText().strip(),
            **self._tts_manager_table_settings(),
        }

    @staticmethod
    def _write_json_atomic(path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(path.name + ".tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp_path.replace(path)

    def _save_settings(self) -> None:
        if not hasattr(self, "voice_combo"):
            return
        try:
            self._write_json_atomic(SETTINGS_FILE, self._collect_settings())
        except OSError as exc:
            self.runtime_diagnostics.breadcrumb("settings_save_failed", error=str(exc))

    def _schedule_settings_save(self, *_args) -> None:
        if self._settings_loaded:
            self._settings_autosave_timer.start()

    def _connect_settings_autosave(self) -> None:
        value_widgets = (
            self.rate_slider, self.voice_volume, self.background_volume, self.seed_spin,
            self.custom_video_width_spin, self.custom_video_height_spin, self.scene_count_spin,
        )
        for widget in value_widgets:
            widget.valueChanged.connect(self._schedule_settings_save)
        self.transition_spin.valueChanged.connect(self._schedule_settings_save)

        toggle_widgets = (
            self.background_check, self.write_log, self.runtime_error_log, self.legacy_umlauts,
            self.ignore_blanks, self.mls_aliases_check, self.result_include_images_check,
            self.result_include_audio_check, self.result_include_clips_check, self.result_include_project_files_check,
        )
        for widget in toggle_widgets:
            widget.toggled.connect(self._schedule_settings_save)

        combo_widgets = (
            self.voice_combo, self.piper_style_combo, self.piper_prosody_combo, self.theme_combo,
            self.prompt_mode_combo, self.output_kind_combo, self.video_resolution_combo, self.video_fps_combo,
            self.package_voice_character_combo, self.package_voice_gender_combo, self.package_voice_quality_combo,
            self.target_ai_combo, self.ollama_model_combo,
        )
        for widget in combo_widgets:
            widget.currentIndexChanged.connect(self._schedule_settings_save)
        self.piper_speaker_list.currentRowChanged.connect(self._schedule_settings_save)
        self.custom_target_edit.textChanged.connect(self._schedule_settings_save)
        package_header = self.tts_package_table.horizontalHeader()
        package_header.sectionMoved.connect(self._schedule_settings_save)
        package_header.sectionResized.connect(self._schedule_settings_save)
        package_header.sortIndicatorChanged.connect(self._schedule_settings_save)

    def save_configuration_profile(self) -> None:
        suggested = BASE_DIR / f"SciFi-Generator_config_v{APP_VERSION}.json"
        path_text, _ = QFileDialog.getSaveFileName(
            self,
            "Konfiguration speichern",
            str(suggested),
            "SciFi-Generator-Konfiguration (*.json);;JSON-Dateien (*.json);;Alle Dateien (*.*)",
        )
        if not path_text:
            return
        path = Path(path_text)
        if path.suffix.lower() != ".json":
            path = path.with_suffix(".json")
        payload = {
            "format": CONFIG_PROFILE_FORMAT,
            "format_version": CONFIG_PROFILE_VERSION,
            "created_with": APP_VERSION,
            "saved_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "settings": self._collect_settings(),
        }
        try:
            self._write_json_atomic(path, payload)
        except OSError as exc:
            QMessageBox.critical(self, "Konfiguration speichern fehlgeschlagen", str(exc))
            return
        self.runtime_diagnostics.breadcrumb("configuration_profile_saved", path=str(path))
        self.status_label.setText(f"Konfiguration gespeichert: {path.name}")

    def load_configuration_profile(self) -> None:
        path_text, _ = QFileDialog.getOpenFileName(
            self,
            "Konfiguration laden",
            str(BASE_DIR),
            "SciFi-Generator-Konfiguration (*.json);;JSON-Dateien (*.json);;Alle Dateien (*.*)",
        )
        if not path_text:
            return
        path = Path(path_text)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            QMessageBox.critical(self, "Konfiguration laden fehlgeschlagen", f"Die Datei konnte nicht gelesen werden:\n{exc}")
            return
        if not isinstance(payload, dict):
            QMessageBox.critical(self, "Konfiguration laden fehlgeschlagen", "Die Datei enthält kein gültiges JSON-Objekt.")
            return
        if "settings" in payload:
            if payload.get("format") != CONFIG_PROFILE_FORMAT:
                QMessageBox.critical(self, "Konfiguration laden fehlgeschlagen", "Die Datei ist kein unterstütztes SciFi-Generator-Konfigurationsprofil.")
                return
            settings = payload.get("settings")
        else:
            # Backward-compatible import of a plain settings.json snapshot.
            settings = payload
        if not isinstance(settings, dict):
            QMessageBox.critical(self, "Konfiguration laden fehlgeschlagen", "Im Profil fehlt der settings-Bereich.")
            return

        if self.playback_active:
            self.stop_playback()
        self._settings_loaded = False
        try:
            self._apply_settings_dict(settings)
        except Exception as exc:
            self.runtime_diagnostics.log_exception("configuration_profile_apply_failed", exc)
            QMessageBox.critical(self, "Konfiguration laden fehlgeschlagen", f"Die Einstellungen konnten nicht angewendet werden:\n{exc}")
            self._settings_loaded = True
            return
        self._settings_loaded = True
        self._save_settings()
        self.runtime_diagnostics.breadcrumb("configuration_profile_loaded", path=str(path))
        self.status_label.setText(f"Konfiguration geladen: {path.name}")

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
        self.runtime_diagnostics.breadcrumb(
            "generate_story_requested", selected_voice=(self.voice_combo.currentText() if hasattr(self, "voice_combo") else ""),
            playback_active=self.playback_active, active_backend=self.active_backend or "none"
        )
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
            self.runtime_diagnostics.log_exception("story_generation", exc, seed=seed)
            QMessageBox.critical(self, "Generierungsfehler", str(exc))
            self.status_label.setText("Generierung fehlgeschlagen.")
            self.generate_button.setEnabled(True)
            return
        except Exception as exc:
            self.runtime_diagnostics.log_exception("story_generation_unexpected", exc, seed=seed)
            QMessageBox.critical(self, "Unerwarteter Generierungsfehler", str(exc))
            self.status_label.setText("Generierung fehlgeschlagen.")
            self.generate_button.setEnabled(True)
            return

        self.runtime_diagnostics.breadcrumb(
            "generate_story_finished", seed=self.result.seed, branch=self.result.branch_path
        )
        self.story_edit.setPlainText(self.result.display_story)
        self.current_log = self.result.build_log(APP_VERSION)
        self.log_edit.setPlainText(self.current_log)
        self.progress.setValue(100)
        hidden_note = " Mit dem Tab ‚Story & Trace‘ kann der Text angezeigt werden." if not self.tabs.isVisible() else ""
        route = self.result.branches[0].choice_label if self.result.branches else "Legacy-Story"
        self.status_label.setText(f"Sektor-Sprung berechnet — {route}. Seed: {self.result.seed}.{hidden_note}")
        self.status_label.setToolTip(self.result.branch_path or route)
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
        self.runtime_diagnostics.breadcrumb(
            "speak_requested", backend=entry.get("backend"), voice=entry.get("name"),
            purpose=purpose, background=with_background, text_chars=len(text)
        )
        self.playback_active = True
        self.playback_purpose = purpose
        self.active_backend = entry["backend"]
        self._pending_background = with_background
        self.execute_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.pause_button.setText("Pause")
        self.narration_audio.setVolume(1.0)
        self.background_effect.setVolume(self.background_volume.value() / 100.0)

        if self.active_backend == "winrt":
            self.pause_button.setEnabled(False)
            self.status_label.setText("Windows-Stimme bereitet die Story vor …")
            self.winrt_service.synthesize(text, entry["id"], self.rate_slider.value(), self.voice_volume.value())
        elif self.active_backend == "piper":
            self.pause_button.setEnabled(False)
            self.status_label.setText("Piper-Stimme bereitet die Story lokal vor …")
            piper_entry = self._voice_with_piper_options(entry)
            noise_scale, noise_w = self._piper_prosody_values()
            self.piper_service.synthesize(
                text, piper_entry, self.rate_slider.value(), self.voice_volume.value(),
                noise_scale=noise_scale, noise_w=noise_w,
            )
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
        self._narration_temp_file = filename
        self.narration_player.setSource(QUrl.fromLocalFile(filename))
        if self._pending_background and SOUND_FILE.is_file():
            self._start_background()
        self.pause_button.setEnabled(True)
        self.narration_player.play()
        self._handle_speech_state("winrt", "speaking")

    def _piper_synthesis_ready(self, filename: str) -> None:
        if not self.playback_active or self.active_backend != "piper":
            Path(filename).unlink(missing_ok=True)
            return
        self._narration_temp_file = filename
        self.narration_player.setSource(QUrl.fromLocalFile(filename))
        self.narration_audio.setVolume(self.voice_volume.value() / 100.0)
        if self._pending_background and SOUND_FILE.is_file():
            self._start_background()
        self.pause_button.setEnabled(True)
        self.narration_player.play()
        self._handle_speech_state("piper", "speaking")

    def _start_background(self) -> None:
        if not SOUND_FILE.is_file():
            return
        self.background_effect.setVolume(self.background_volume.value() / 100.0)
        self.runtime_diagnostics.breadcrumb(
            "background_start", volume=self.background_volume.value(), source=SOUND_FILE
        )
        self.background_effect.stop()
        self.background_effect.play()

    def _background_status_changed(self) -> None:
        try:
            status = self.background_effect.status()
            self.runtime_diagnostics.breadcrumb("background_status", status=str(status))
        except Exception as exc:
            self.runtime_diagnostics.log_exception("background_status", exc)

    def pause_or_resume(self) -> None:
        if not self.playback_active or not self.active_backend:
            return
        if self.speech_state == "speaking":
            if self.active_backend in {"winrt", "piper"}:
                self.narration_player.pause()
                self._handle_speech_state(self.active_backend, "paused")
            elif self.active_backend == "sapi":
                self.sapi_service.pause()
            else:
                self.qt_tts.pause()
            self._background_was_playing_before_pause = bool(self._pending_background and self.background_effect.isPlaying())
            self.background_effect.stop()
        elif self.speech_state == "paused":
            if self.active_backend in {"winrt", "piper"}:
                self.narration_player.play()
                self._handle_speech_state(self.active_backend, "speaking")
            elif self.active_backend == "sapi":
                self.sapi_service.resume()
            else:
                self.qt_tts.resume()
            if self._pending_background and SOUND_FILE.is_file() and self._background_was_playing_before_pause:
                self.background_effect.play()
            self._background_was_playing_before_pause = False

    def stop_playback(self) -> None:
        was_active = self.playback_active
        if was_active or self.active_backend:
            self.runtime_diagnostics.breadcrumb(
                "stop_playback", backend=self.active_backend or "none", purpose=self.playback_purpose, state=self.speech_state
            )
        stopped_purpose = self.playback_purpose
        self.playback_active = False
        self.playback_purpose = "generic"
        self.active_backend = None
        self.speech_state = "ready"
        self.qt_tts.stop()
        self.sapi_service.stop()
        self.winrt_service.cancel()
        self.piper_service.cancel()
        self.narration_player.stop()
        self.narration_player.setSource(QUrl())
        self.background_effect.stop()
        self.winrt_service.release_output()
        self.piper_service.release_output()
        if self._narration_temp_file:
            Path(self._narration_temp_file).unlink(missing_ok=True)
            self._narration_temp_file = None
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
            if self.active_backend in {"winrt", "piper"}:
                self._handle_speech_state(self.active_backend, "ready")
        elif status == QMediaPlayer.MediaStatus.InvalidMedia and self.active_backend in {"winrt", "piper"}:
            self._handle_speech_state(self.active_backend, "error")

    def _handle_speech_state(self, backend: str, state: str) -> None:
        self.runtime_diagnostics.breadcrumb(
            "speech_state", backend=backend, state=state, active_backend=self.active_backend or "none",
            playback_active=self.playback_active
        )
        if backend != self.active_backend:
            return
        self.speech_state = state
        if state == "preparing":
            self.pause_button.setEnabled(False)
            self.status_label.setText(
                "Piper-Stimme wird lokal synthetisiert …" if backend == "piper" else "Windows-Stimme bereitet die Story vor …"
            )
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
            self.background_effect.stop()
            self.playback_active = False
            self.playback_purpose = "generic"
            self.pause_button.setEnabled(False)
            self.stop_button.setEnabled(False)
            self.execute_button.setEnabled(self.voice_combo.count() > 0)
            self.status_label.setText("Fehler bei der Sprachausgabe. Details stehen in der TTS-Stimmendiagnose.")

    def _finish_playback(self) -> None:
        completed_purpose = self.playback_purpose
        self.background_effect.stop()
        self.narration_player.stop()
        self.narration_player.setSource(QUrl())
        self.winrt_service.release_output()
        self.piper_service.release_output()
        if self._narration_temp_file:
            Path(self._narration_temp_file).unlink(missing_ok=True)
            self._narration_temp_file = None
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
        if backend in {"winrt", "sapi", "piper"}:
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
        if export_voice and export_voice.get("backend") == "piper":
            export_voice = self._voice_with_piper_options(export_voice)
        if not export_voice:
            QMessageBox.warning(
                self,
                "Stimme nicht exportierbar",
                "Die ausgewählte Qt-Stimme kann nicht direkt in eine Audiodatei geschrieben werden "
                "und es wurde keine gleichnamige Windows-OneCore/WinRT- oder SAPI-Stimme gefunden. "
                "Bitte wählen Sie eine exportierbare Windows-Stimme oder ein installiertes Piper-Komplettpaket aus.",
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
        self.runtime_diagnostics.breadcrumb(
            "audio_export_requested", backend=export_voice.get("backend"), voice=export_voice.get("name"),
            output=output_path, background=bool(background_path), background_volume=self.background_volume.value()
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
            piper_engine_path=(Path(str(export_voice.get("engine_path"))) if export_voice.get("engine_path") else None),
            piper_model_path=(Path(str(export_voice.get("model_path"))) if export_voice.get("model_path") else None),
            piper_config_path=(Path(str(export_voice.get("config_path"))) if export_voice.get("config_path") else None),
            piper_speaker_id=(int(export_voice["speaker_id"]) if export_voice.get("speaker_id") is not None else None),
            piper_noise_scale=self._piper_prosody_values()[0],
            piper_noise_w=self._piper_prosody_values()[1],
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
        self.runtime_diagnostics.breadcrumb("audio_export_finished", output=filename)
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
        self.runtime_diagnostics.breadcrumb("audio_export_failed", message=message)
        if self._export_dialog is not None:
            self._export_dialog.close()
        self.status_label.setText("Audioexport fehlgeschlagen.")
        QMessageBox.critical(self, "Audioexport fehlgeschlagen", message)

    def _audio_export_canceled(self) -> None:
        self.runtime_diagnostics.breadcrumb("audio_export_canceled")
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

    @staticmethod
    def _aspect_ratio_text(width: int, height: int) -> str:
        divisor = gcd(max(1, width), max(1, height))
        return f"{width // divisor}:{height // divisor}"

    def _selected_video_resolution(self) -> tuple[int, int, str]:
        data = self.video_resolution_combo.currentData() or {}
        width = int(data.get("width", 0))
        height = int(data.get("height", 0))
        if width <= 0 or height <= 0:
            width = self.custom_video_width_spin.value()
            height = self.custom_video_height_spin.value()
        return width, height, self._aspect_ratio_text(width, height)

    def _update_video_resolution_controls(self) -> None:
        if not hasattr(self, "video_resolution_combo"):
            return
        is_package = self.output_kind_combo.currentText().startswith("Gesamtpaket")
        data = self.video_resolution_combo.currentData() or {}
        is_custom = int(data.get("width", 0)) <= 0 or int(data.get("height", 0)) <= 0
        show_custom = is_package and is_custom
        self.custom_video_size_widget.setVisible(show_custom)
        self.custom_video_size_widget.setEnabled(show_custom)
        if self.custom_video_size_label is not None:
            self.custom_video_size_label.setVisible(show_custom)
        width, height, ratio = self._selected_video_resolution()
        if ratio == "1:1":
            description = "quadratisches Video"
        elif ratio == "16:9":
            description = "Breitbild 16:9"
        elif width > height:
            description = "Breitbild"
        elif height > width:
            description = "Hochformat"
        else:
            description = "benutzerdefiniertes Format"
        self.video_aspect_info_label.setText(f"{ratio} — {description}; {width} × {height} px")
        self._update_tab_status_summaries()

    def _update_tab_status_summaries(self, *args) -> None:
        """Refresh compact status text for the always-visible category-tab controls."""
        if hasattr(self, "audio_tab_status_label") and hasattr(self, "voice_combo"):
            entry = self.voice_combo.currentData() if self.voice_combo.count() else None
            voice_name = (entry or {}).get("name", "Standardstimme")
            if (entry or {}).get("backend") == "piper":
                style_name = self._current_piper_style_name(entry or {})
                if style_name:
                    voice_name += " / " + PIPER_STYLE_LABELS.get(style_name, style_name)
                voice_name += f" / {self.piper_prosody_combo.currentText()}"
            ambience = (
                f"Hintergrund {self.background_volume.value()} %"
                if self.background_check.isChecked()
                else "ohne Hintergrund"
            )
            self.audio_tab_status_label.setText(f"Aktiv: {voice_name}; {ambience}")

    def _update_target_ai_controls(self) -> None:
        profile = self._selected_prompt_profile()
        is_other = bool(profile and profile.profile_id == "other")
        self.custom_target_edit.setEnabled(is_other)
        self.custom_target_container.setVisible(is_other)

        is_package = self.output_kind_combo.currentText().startswith("Gesamtpaket")
        self.media_options_group.setVisible(is_package)
        self.result_contents_group.setVisible(is_package)
        self.transition_spin.setVisible(is_package)
        self.transition_spin.setEnabled(is_package)
        if self.transition_label is not None:
            self.transition_label.setVisible(is_package)
        for widget, label in (
            (self.video_resolution_combo, self.video_resolution_label),
            (self.video_aspect_info_label, self.video_aspect_info_field_label),
            (self.video_fps_combo, self.video_fps_label),
            (self.package_voice_character_combo, self.package_voice_character_label),
            (self.package_voice_gender_combo, self.package_voice_gender_label),
            (self.package_voice_quality_combo, self.package_voice_quality_label),
        ):
            widget.setVisible(is_package)
            widget.setEnabled(is_package)
            if label is not None:
                label.setVisible(is_package)
        self._update_video_resolution_controls()
        self.generate_prompts_button.setText(
            "Gesamtpaket-Auftrag erzeugen" if is_package else "Nur Bildserien-Prompt erzeugen"
        )
        self.save_prompts_button.setText(
            "Gesamtpaket-Übergabe-ZIP speichern …" if is_package else "Bildserien-Prompt speichern …"
        )
        if is_package:
            self.output_kind_status_label.setText(
                "Fertiges Ergebnis: konsistente Bilder, Szenen-TTS, hörbarer Hintergrundmix, Video und Ergebnis-ZIP. "
                "Eine reine Bildsammlung zählt nicht als Abschluss."
            )
        else:
            self.output_kind_status_label.setText(
                "Nur Bilder: keine Sprachausgabe, kein Hintergrundmix und kein Video."
            )

        target_name = self.custom_target_edit.text().strip() if is_other else (profile.name if profile else "unbekannt")
        if is_package and profile:
            hint = (
                f"Ziel: {target_name}. Die Ausgabe fordert eine vollständige illustrierte Audiogeschichte an: "
                "Szenenbilder, getrennte TTS-Audios, an die Audiodauer angepasste Bildabschnitte, sanfte Übergänge, "
                "fertiges Video und möglichst ein ZIP-Paket. Die gewählte Videoauflösung, das daraus abgeleitete Seitenverhältnis, "
                "Stimmcharakter, stimmliche Wirkung und Qualitätsziel werden verbindlich in den Auftrag übernommen. "
                "Falls direkte Medienerzeugung fehlt, wird ein Offline-Skript verlangt. Beim Speichern als Übergabe-ZIP wird die aktive background.wav tatsächlich beigefügt."
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
        self._update_tab_status_summaries()

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
        self._update_tab_status_summaries()

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
        (
            self._storyboard_video_width,
            self._storyboard_video_height,
            self._storyboard_aspect_ratio,
        ) = self._selected_video_resolution()
        self._storyboard_media_settings = self._current_media_package_settings()
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
        if voice.get("backend") == "piper":
            voice = self._voice_with_piper_options(voice)
        backend_key = str(voice.get("backend", ""))
        backend_name = BACKEND_LABELS.get(backend_key, backend_key or "Systemstandard")
        voice_display_name = str(voice.get("name") or self.saved_voice_name or "Systemstandard")
        if backend_key == "piper" and voice.get("speaker_name"):
            style_raw = str(voice.get("speaker_name"))
            voice_display_name += " — " + PIPER_STYLE_LABELS.get(style_raw, style_raw)
        width = max(256, int(self._storyboard_video_width))
        height = max(256, int(self._storyboard_video_height))
        aspect_ratio = self._storyboard_aspect_ratio or self._aspect_ratio_text(width, height)
        return MediaPackageSettings(
            aspect_ratio=aspect_ratio,
            resolution=f"{width}x{height}",
            width=width,
            height=height,
            fps=int(self.video_fps_combo.currentData() or 8),
            transition_seconds=self._storyboard_transition_seconds,
            output_video="scifi_story.mp4",
            output_zip="scifi_story_package.zip",
            voice_name=voice_display_name,
            voice_id=str(voice.get("id") or ""),
            voice_backend=backend_name,
            voice_backend_key=backend_key,
            speech_rate=self.rate_slider.value(),
            voice_volume=self.voice_volume.value(),
            voice_character=self.package_voice_character_combo.currentText(),
            voice_gender=self.package_voice_gender_combo.currentText(),
            voice_quality=self.package_voice_quality_combo.currentText(),
            background_enabled=self.background_check.isChecked() and SOUND_FILE.is_file(),
            background_volume=self.background_volume.value(),
            background_filename=SOUND_FILE.name,
            include_images_in_result_zip=self.result_include_images_check.isChecked(),
            include_audio_in_result_zip=self.result_include_audio_check.isChecked(),
            include_clips_in_result_zip=self.result_include_clips_check.isChecked(),
            include_project_files_in_result_zip=self.result_include_project_files_check.isChecked(),
            style_reference_filename=STYLE_REFERENCE_FILE.name,
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
            package_settings = self._storyboard_media_settings or self._current_media_package_settings()
            self.storyboard_text = render_media_package_text(
                scene_list,
                full_story=self.story_edit.toPlainText(),
                source=source,
                model=model,
                profile=profile,
                custom_target_name=self._storyboard_custom_target,
                settings=package_settings,
            )
            validation_errors = validate_total_package_prompt(
                self.storyboard_text,
                background_required=package_settings.background_enabled,
            )
            if validation_errors:
                self._storyboard_generation_failed(
                    "Der erzeugte Gesamtpaket-Auftrag hat die interne Vollständigkeitsprüfung nicht bestanden:\n" +
                    "\n".join(validation_errors)
                )
                return
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

        profile = self.prompt_profile_manager.get(self._storyboard_profile_name)
        target_name = self._storyboard_custom_target or self._storyboard_profile_name
        settings = self._storyboard_media_settings or self._current_media_package_settings()

        if package_mode:
            validation_errors = validate_total_package_prompt(
                self.storyboard_text,
                background_required=settings.background_enabled,
            )
            if validation_errors:
                QMessageBox.critical(
                    self,
                    "Gesamtpaket-Auftrag unvollständig",
                    "Der Auftrag kann nicht gespeichert werden:\n" + "\n".join(validation_errors),
                )
                return
            default = BASE_DIR / f"scifi_total_package_handoff_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
            filename, selected_filter = QFileDialog.getSaveFileName(
                self,
                "Gesamtpaket-Übergabe speichern",
                str(default),
                "Empfohlenes Übergabe-ZIP (*.zip);;Nur Prompt als Text (*.txt);;Manifest/Prompt als JSON (*.json)",
            )
        else:
            default = BASE_DIR / f"scifi_storyboard_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            filename, selected_filter = QFileDialog.getSaveFileName(
                self,
                "Bildserien-Prompt speichern",
                str(default),
                "Textdatei (*.txt);;Markdown (*.md);;JSON (*.json);;Alle Dateien (*)",
            )
        if not filename:
            return

        path = Path(filename)
        try:
            if package_mode and (path.suffix.lower() == ".zip" or "ZIP" in selected_filter):
                if profile is None:
                    raise HandoffPackageError("Das ausgewählte Promptprofil ist nicht mehr verfügbar.")
                manifest = build_media_manifest(
                    self.storyboard_scenes,
                    target_name=target_name,
                    profile=profile,
                    settings=settings,
                )
                manifest.update({
                    "app_version": APP_VERSION,
                    "instruction_document": "prompts/scifi_media_package_prompt.txt",
                    "full_story": "story/full_story.txt",
                    "handoff_package": True,
                    "background_asset_included": bool(settings.background_enabled and SOUND_FILE.is_file()),
                })
                extra_files = {
                    "tools/list_winrt_voices.ps1": TOOLS_DIR / "list_winrt_voices.ps1",
                    "tools/synthesize_winrt.ps1": TOOLS_DIR / "synthesize_winrt.ps1",
                    "tools/synthesize_sapi.ps1": TOOLS_DIR / "synthesize_sapi.ps1",
                }
                saved = create_handoff_zip(
                    path,
                    prompt_text=self.storyboard_text,
                    manifest=manifest,
                    full_story=self.story_edit.toPlainText(),
                    app_version=APP_VERSION,
                    background_path=SOUND_FILE if settings.background_enabled and SOUND_FILE.is_file() else None,
                    style_reference_path=STYLE_REFERENCE_FILE,
                    extra_files=extra_files,
                )
                self.status_label.setText(f"Gesamtpaket-Übergabe-ZIP gespeichert: {saved}")
                selected_parts = ["fertiges Video"]
                if settings.include_images_in_result_zip:
                    selected_parts.append("Szenenbilder")
                if settings.include_audio_in_result_zip:
                    selected_parts.append("Szenenaudios und final_mix.wav")
                if settings.include_clips_in_result_zip:
                    selected_parts.append("Einzelclips")
                if settings.include_project_files_in_result_zip:
                    selected_parts.append("Projekt- und Build-Dateien")
                QMessageBox.information(
                    self,
                    "Übergabe-ZIP erstellt",
                    "Laden Sie in einen neuen Chat bevorzugt dieses ZIP hoch, nicht nur die Prompt-TXT.\n\n"
                    "Die Übergabe orientiert sich an der verbesserten Paketstruktur und enthält die verbindliche "
                    "style_reference.png, den Sofort-Ausführungsauftrag, vollständige Build-Skripte, Manifest, Story, "
                    "Lieferprüfung und – sofern aktiviert – die echte background.wav.\n\n"
                    "Gewünschter Inhalt des späteren Ergebnis-ZIP:\n• " + "\n• ".join(selected_parts) + "\n\n"
                    "Das Übergabe-ZIP wurde nach dem Schreiben nochmals auf alle Pflichtdateien geprüft.",
                )
                return

            if path.suffix.lower() == ".json":
                if package_mode and profile:
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
                if package_mode and settings.background_enabled:
                    answer = QMessageBox.warning(
                        self,
                        "Nur Text enthält keine Audiodatei",
                        "Die reine Promptdatei kann background.wav nicht einbetten. Ein neuer Chat könnte den Hintergrundsound deshalb weglassen.\n\n"
                        "Empfohlen ist das Übergabe-ZIP. Trotzdem nur die Textdatei speichern?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No,
                    )
                    if answer != QMessageBox.StandardButton.Yes:
                        return
                path.write_text(self.storyboard_text, encoding="utf-8-sig")
            self.status_label.setText(f"{kind_label} gespeichert: {path}")
        except (OSError, HandoffPackageError) as exc:
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
            "PyQt6-Neuauflage des früheren VB.NET-Zufallsgeschichten-Generators.<br>"
            "Originalautor und Textbestände: zeittresor.<br><br>"
            "Die Themes liegen als externe JSON-Dateien im Ordner <code>themes</code> und werden "
            "vor der Verwendung automatisch auf ausreichenden Textkontrast geprüft.<br><br>"
            "Die Stimmensuche kombiniert Windows OneCore/WinRT, native Windows-SAPI, Qt und optional installierte lokale Piper-Komplettpakete.<br>"
            "Der Sprachmanager kann Piper-Laufzeit und deutsche Modelle vollständig in den Programmordner installieren und vorhandene Dateien wiederverwenden.<br><br>"
            "Berechnete Stories können samt der aktuell eingestellten Brückenatmosphäre als WAV "
            "und bei vorhandenem FFmpeg auch als MP3 exportiert werden.<br><br>"
            "Die Oberfläche ist in die Kategorien Mission, Medienpaket, Sprache &amp; Audio, Sprachmanager, Story &amp; Trace und Einstellungen gegliedert. Die jeweiligen Optionen werden innerhalb ihres Tabs direkt angezeigt und nicht zusätzlich in auf- und zuklappbaren Unterbereichen versteckt.<br><br>"
            "Zusätzlich können ausführbare Bildserien-Aufträge oder vollständige Gesamtpaket-Prompts für "
            "Szenenbilder, TTS-Audio, Videozusammenschnitt und ZIP-Ausgabe erzeugt werden. Die Ausgabe wird für "
            "ChatGPT, Grok, Gemini, Stable Diffusion oder andere Systeme angepasst. "
            "Bei Gesamtpaketen können außerdem Videoauflösung und Seitenverhältnis sowie Stimmcharakter, stimmliche Wirkung und TTS-Qualitätsziel getrennt vorgegeben werden. "
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
        if self._tts_package_worker is not None:
            self._tts_package_worker.cancel()
        if self._tts_package_thread is not None:
            self._tts_package_thread.quit()
            self._tts_package_thread.wait(3000)
        self.sapi_service.shutdown()
        self.runtime_diagnostics.breadcrumb("application_close")
        self.runtime_diagnostics.close()
        sys.excepthook = self._previous_excepthook
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setStyle("Fusion")
    window = MainWindow()
    sys.excepthook = window._handle_uncaught_exception
    window.runtime_diagnostics.breadcrumb("main_window_shown")
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
