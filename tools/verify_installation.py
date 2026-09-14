from __future__ import annotations

import importlib
import json
import platform
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from audio_mixer import read_pcm_wav  # noqa: E402
from prompt_profile_manager import PromptProfileManager  # noqa: E402
from storyboard_generator import generate_storyboard  # noqa: E402
from story_continuity import StoryContinuity  # noqa: E402
from story_engine import APP_VERSION, StoryEngine  # noqa: E402
from theme_manager import ThemeManager  # noqa: E402
from tts_package_manager import TtsPackageManager  # noqa: E402
from v6028_tts_flow import (  # noqa: E402
    PIPER_MODE_CONTINUOUS,
    PIPER_MODE_SECTIONS,
    ffmpeg_pitch_filter,
    install as install_v6028_tts_flow,
    pitch_factor,
    prepare_piper_text,
)

EXPECTED_VERSION = "60.28"
EXPECTED_SENTENCE_FILES = 232
EXPECTED_STRUCTURAL_ROUTES = 200
EXPECTED_THEMES = 9
EXPECTED_PROMPT_PROFILES = {"ChatGPT", "Grok", "Gemini", "Stable Diffusion", "Andere"}

CONTINUITY_FILES = (
    "continuity_signal_return.ini",
    "continuity_pursuit_return.ini",
    "continuity_anomaly_return.ini",
    "continuity_contact_return.ini",
    "continuity_rescue_return.ini",
    "continuity_ship_return.ini",
    "continuity_response_investigate.ini",
    "continuity_response_cautious.ini",
    "continuity_response_defer.ini",
    "continuity_outcome_resolved.ini",
    "continuity_outcome_deepens.ini",
    "continuity_outcome_false_lead.ini",
    "continuity_outcome_watchlist.ini",
    "continuity_outcome_deferred.ini",
)

REQUIRED_FILES = (
    "app.py",
    "launcher.py",
    "story_engine.py",
    "story_continuity.py",
    "v6028_tts_flow.py",
    "audio_export.py",
    "audio_mixer.py",
    "tts_services.py",
    "tts_package_manager.py",
    "tts_package_catalog.json",
    "sequence_legacy.json",
    "requirements.txt",
    "runtime_diagnostics.py",
    "storyboard_generator.py",
    "prompt_profile_manager.py",
    "ollama_client.py",
    "media_package_generator.py",
    "handoff_package.py",
    "data/sounds/background.wav",
    "data/mls_speaker_aliases.json",
    "tools/install_dependencies.py",
    "tools/index_local_tts_assets.py",
    "tools/list_winrt_voices.ps1",
    "tools/synthesize_winrt.ps1",
    "tools/synthesize_sapi.ps1",
)


def _compile_python_file(path: Path) -> str | None:
    try:
        source = path.read_text(encoding="utf-8")
        compile(source, str(path), "exec")
        return None
    except Exception as exc:
        return f"Python syntax check failed for {path.relative_to(ROOT)}: {type(exc).__name__}: {exc}"


def _cleanup_window(window) -> None:
    for service_name in ("winrt_service", "piper_service"):
        service = getattr(window, service_name, None)
        if service is not None:
            try:
                service.cancel()
            except Exception:
                pass
    try:
        window.close()
    except Exception:
        pass


def main() -> int:
    errors: list[str] = []
    version_file = ROOT / "version.txt"
    expected_from_file = version_file.read_text(encoding="utf-8").strip() if version_file.is_file() else ""

    print(f"SciFi-Generator installation verification v{APP_VERSION}")
    print(f"Python: {sys.version.split()[0]}")

    if not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", APP_VERSION):
        errors.append(f"Invalid application version format: {APP_VERSION!r}")
    if APP_VERSION != expected_from_file:
        errors.append(f"Version mismatch: story_engine={APP_VERSION!r}, version.txt={expected_from_file!r}")
    if APP_VERSION != EXPECTED_VERSION:
        errors.append(f"This verifier belongs to v{EXPECTED_VERSION}, but application reports {APP_VERSION!r}")

    for relative in REQUIRED_FILES:
        path = ROOT / relative
        if not path.is_file():
            errors.append(f"Required file is missing: {relative}")
    for relative in (
        "app.py",
        "launcher.py",
        "story_engine.py",
        "story_continuity.py",
        "v6028_tts_flow.py",
        "audio_export.py",
        "tts_services.py",
        "tools/install_dependencies.py",
        "tools/index_local_tts_assets.py",
    ):
        path = ROOT / relative
        if path.is_file():
            syntax_error = _compile_python_file(path)
            if syntax_error:
                errors.append(syntax_error)

    vars_dir = ROOT / "data" / "vars"
    engine = StoryEngine(vars_dir, ROOT / "sequence_legacy.json")
    missing = engine.validate_sources()
    if missing:
        errors.append("Missing sentence files: " + ", ".join(missing))

    source_count = len(list(vars_dir.glob("*.ini")))
    print(f"Sentence files: {source_count}")
    if source_count != EXPECTED_SENTENCE_FILES:
        errors.append(
            f"Unexpected sentence-file count for v{APP_VERSION}: {source_count} "
            f"(expected {EXPECTED_SENTENCE_FILES})"
        )

    route_count = len(engine.enumerate_branch_routes())
    print(f"Structural branch routes: {route_count}")
    if route_count != EXPECTED_STRUCTURAL_ROUTES:
        errors.append(
            f"Unexpected structural route count: {route_count} "
            f"(expected {EXPECTED_STRUCTURAL_ROUTES})"
        )
    errors.extend(f"Terminal invariant: {message}" for message in engine.validate_terminal_invariant())

    for filename in CONTINUITY_FILES:
        path = vars_dir / filename
        if not path.is_file():
            errors.append(f"Required continuity fragment is missing: data/vars/{filename}")
            continue
        selectable = [text.strip() for _, text in engine._read_lines(path, True)]
        if len(selectable) < 8:
            errors.append(f"Continuity fragment {filename} has {len(selectable)} lines; expected >= 8")

    state_path = ROOT / "story_state.json"
    state_existed_before = state_path.exists()
    continuity = StoryContinuity(state_path)
    default_state = continuity.default_state()
    for key in ("jump_index", "recent_routes", "open_hooks", "ship_state", "history"):
        if key not in default_state:
            errors.append(f"Continuity default state is missing key: {key}")
    if not state_existed_before and state_path.exists():
        errors.append("Continuity verification unexpectedly created story_state.json")

    manager = ThemeManager(ROOT / "themes")
    manager.load()
    print(f"Themes: {len(manager.themes)}")
    errors.extend(f"Theme: {message}" for message in manager.errors)
    if len(manager.themes) < EXPECTED_THEMES:
        errors.append(f"Expected at least {EXPECTED_THEMES} themes, got {len(manager.themes)}")

    prompt_manager = PromptProfileManager(ROOT / "prompt_profiles")
    prompt_manager.load()
    print(f"Prompt profiles: {len(prompt_manager.profiles)}")
    errors.extend(f"Prompt profile: {message}" for message in prompt_manager.errors)
    missing_profiles = EXPECTED_PROMPT_PROFILES.difference(prompt_manager.profiles)
    if missing_profiles:
        errors.append("Missing target AI prompt profiles: " + ", ".join(sorted(missing_profiles)))

    try:
        section_text = prepare_piper_text("Alpha.\n\nBeta.", PIPER_MODE_SECTIONS)
        continuous_text = prepare_piper_text("Alpha.\n\nBeta.", PIPER_MODE_CONTINUOUS)
        if section_text != "Alpha.\n\nBeta.":
            errors.append("Piper section mode unexpectedly changed story line boundaries")
        if continuous_text != "Alpha. Beta.":
            errors.append(f"Piper continuous mode returned unexpected text: {continuous_text!r}")
        if not (1.41 < pitch_factor(6) < 1.42):
            errors.append("Piper pitch-factor calculation is invalid")
        filter_text = ffmpeg_pitch_filter(22050, 2)
        if "asetrate=" not in filter_text or "atempo=" not in filter_text:
            errors.append("Piper duration-compensated pitch filter is incomplete")
        print("Piper continuous-flow helper: OK")
        print("Piper independent pitch helper: OK")
    except Exception as exc:
        errors.append(f"Piper v60.28 helper verification failed: {type(exc).__name__}: {exc}")

    if platform.system() == "Windows":
        window = None
        try:
            gui_module = importlib.import_module("app")
            install_v6028_tts_flow(gui_module)
            print("GUI import smoke test: OK")
            loop_count = gui_module.qsoundeffect_infinite_loop_count()
            if loop_count != -2:
                errors.append(f"GUI QSoundEffect loop compatibility returned {loop_count}, expected -2")
            else:
                print("GUI QSoundEffect loop compatibility: OK")

            from PyQt6.QtWidgets import QApplication

            qt_app = QApplication.instance() or QApplication([])
            window = gui_module.MainWindow()
            if not hasattr(window, "piper_synthesis_mode_combo"):
                errors.append("v60.28 Piper synthesis-mode control is missing")
            if not hasattr(window, "piper_pitch_slider"):
                errors.append("v60.28 Piper pitch control is missing")
            if window.piper_synthesis_mode_combo.findData(PIPER_MODE_CONTINUOUS) < 0:
                errors.append("Piper continuous-flow option is missing from the GUI")
            settings = window._collect_settings()
            if "piper_synthesis_mode" not in settings or "piper_pitch_semitones" not in settings:
                errors.append("v60.28 Piper settings are not persisted in configuration profiles")
            if type(window.piper_service).__name__ != "EnhancedPiperTtsService":
                errors.append("Enhanced v60.28 Piper playback service is not active")
            _cleanup_window(window)
            qt_app.processEvents()
            print("GUI MainWindow construction smoke test: OK")
            print("GUI Piper v60.28 controls: OK")
        except Exception as exc:
            errors.append(f"GUI import/API/MainWindow smoke test failed: {type(exc).__name__}: {exc}")
            if window is not None:
                _cleanup_window(window)

    try:
        aliases_payload = json.loads((ROOT / "data" / "mls_speaker_aliases.json").read_text(encoding="utf-8"))
        aliases = aliases_payload.get("aliases", {}) if isinstance(aliases_payload, dict) else {}
        print(f"MLS mnemonic aliases: {len(aliases)}")
        if len(aliases) != 236:
            errors.append(f"MLS mnemonic alias count is {len(aliases)}, expected 236")
    except Exception as exc:
        errors.append(f"MLS mnemonic alias verification failed: {exc}")

    try:
        packages = TtsPackageManager(ROOT, ROOT / "tts_package_catalog.json")
        errors.extend(f"TTS package catalog: {message}" for message in packages.catalog_errors)
        print(f"TTS complete packages: {len(packages.packages)}")
        if len(packages.packages) < 10:
            errors.append(f"Expected at least 10 curated German TTS packages, got {len(packages.packages)}")
    except Exception as exc:
        errors.append(f"TTS package catalog verification failed: {exc}")

    try:
        samples, sample_rate = read_pcm_wav(ROOT / "data" / "sounds" / "background.wav")
        if samples.size == 0 or sample_rate < 1:
            errors.append("Background WAV could not be decoded")
    except Exception as exc:
        errors.append(f"Background WAV verification failed: {exc}")

    try:
        before_state = state_path.read_bytes() if state_path.is_file() else None
        first = engine.generate(seed=60_028)
        second = engine.generate(seed=60_028)
        if first.raw_story != second.raw_story or first.branch_path != second.branch_path:
            errors.append("Explicit seeded story generation is not deterministic")
        expected_terminal = (
            "mission_free_space.ini",
            "mission_end_status.ini",
            "ship_liftoff_jumpready.ini",
            "mission_jump_prompt.ini",
        )
        terminal_sources = tuple(Path(item.source).name for item in first.selections[-4:])
        if terminal_sources != expected_terminal:
            errors.append(f"Generated story does not end jump-ready: {terminal_sources!r}")
        scenes = generate_storyboard(first, 8)
        if not scenes or len(scenes) > 8:
            errors.append(f"Storyboard smoke test produced an invalid scene count: {len(scenes)}")
        after_state = state_path.read_bytes() if state_path.is_file() else None
        if before_state != after_state:
            errors.append("Explicit seeded verification modified persistent story_state.json")
    except Exception as exc:
        errors.append(f"Story/continuity generation smoke test failed: {type(exc).__name__}: {exc}")

    print(f"Version: {APP_VERSION}")
    if errors:
        print("Verification failed:")
        for message in errors:
            print(f"  - {message}")
        return 1

    print("Verification OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
