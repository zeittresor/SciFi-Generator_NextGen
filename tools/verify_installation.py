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

from story_engine import APP_VERSION, StoryEngine  # noqa: E402
from story_continuity import StoryContinuity  # noqa: E402
from audio_mixer import read_pcm_wav  # noqa: E402
from theme_manager import ThemeManager  # noqa: E402
from prompt_profile_manager import PromptProfileManager  # noqa: E402
from storyboard_generator import generate_storyboard  # noqa: E402
from tts_package_manager import TtsPackageManager  # noqa: E402

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


def _cleanup_winrt_voice_probe(window) -> None:
    """Stop the asynchronous WinRT voice-list probe used during GUI construction.

    MainWindow starts a short PowerShell voice enumeration in the background. A smoke
    test closes the window almost immediately, so without explicit cleanup Qt can
    print `QProcess: Destroyed while process ... is still running` even though the
    application itself constructed correctly.
    """
    service = getattr(window, "winrt_service", None)
    if service is None:
        return
    process = getattr(service, "_list_process", None)
    if process is None:
        return
    service._list_process = None
    try:
        process.finished.disconnect(service._voice_list_finished)
    except (TypeError, RuntimeError):
        pass
    try:
        from PyQt6.QtCore import QProcess
        if process.state() != QProcess.ProcessState.NotRunning:
            process.kill()
            process.waitForFinished(1500)
    finally:
        process.deleteLater()


def main() -> int:
    errors: list[str] = []
    version_file = ROOT / "version.txt"
    expected_version = version_file.read_text(encoding="utf-8").strip() if version_file.is_file() else ""

    print(f"SciFi-Generator installation verification v{APP_VERSION}")
    print(f"Python: {sys.version.split()[0]}")

    if not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", APP_VERSION):
        errors.append(f"Invalid application version format: {APP_VERSION!r}")
    if APP_VERSION != expected_version:
        errors.append(
            f"Version mismatch: story_engine={APP_VERSION!r}, version.txt={expected_version!r}"
        )
    if APP_VERSION != "60.27.1":
        errors.append(f"This verifier belongs to v60.27.1, but application reports {APP_VERSION!r}")

    vars_dir = ROOT / "data" / "vars"
    engine = StoryEngine(vars_dir, ROOT / "sequence_legacy.json")
    missing = engine.validate_sources()
    if missing:
        errors.append("Missing sentence files: " + ", ".join(missing))

    source_count = len(list(vars_dir.glob("*.ini")))
    print(f"Sentence files: {source_count}")
    if source_count != EXPECTED_SENTENCE_FILES:
        errors.append(
            f"Unexpected sentence-file count for v{APP_VERSION}: "
            f"{source_count} (expected {EXPECTED_SENTENCE_FILES})"
        )

    route_count = len(engine.enumerate_branch_routes())
    print(f"Structural branch routes: {route_count}")
    if route_count != EXPECTED_STRUCTURAL_ROUTES:
        errors.append(
            f"Unexpected structural route count: {route_count} "
            f"(expected {EXPECTED_STRUCTURAL_ROUTES})"
        )
    errors.extend(
        f"Terminal invariant: {message}"
        for message in engine.validate_terminal_invariant()
    )

    for ini_path in sorted(vars_dir.glob("*.ini")):
        selectable = [text.strip().casefold() for _, text in engine._read_lines(ini_path, True)]
        if len(selectable) != len(set(selectable)):
            errors.append(f"Duplicate selectable fragment in: {ini_path.name}")

    continuity_module = ROOT / "story_continuity.py"
    if not continuity_module.is_file():
        errors.append("Required v60.27 continuity module is missing: story_continuity.py")
    for filename in CONTINUITY_FILES:
        path = vars_dir / filename
        if not path.is_file():
            errors.append(f"Required v60.27 continuity fragment is missing: data/vars/{filename}")
            continue
        lines = [text.strip() for _, text in engine._read_lines(path, True)]
        if len(lines) < 8:
            errors.append(f"Continuity fragment {filename} has only {len(lines)} selectable lines; expected >= 8")

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

    requirements_text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    if "PyQt6>=6.7,<7" not in requirements_text:
        errors.append("GUI requirements do not declare PyQt6>=6.7,<7")

    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    if "from PyQt6" not in app_source or "from PySide6" in app_source:
        errors.append("Desktop frontend is not fully migrated to PyQt6")
    if "QSoundEffect" not in app_source or "background_effect.setLoopCount(qsoundeffect_infinite_loop_count())" not in app_source:
        errors.append("Bridge ambience is not using the compatible infinite QSoundEffect loop")
    if '"seed": self.seed_spin.value()' not in app_source:
        errors.append("Seed is not persisted in the complete settings profile")
    if "_settings_autosave_timer" not in app_source or "_write_json_atomic" not in app_source:
        errors.append("Debounced atomic settings autosave is missing")

    if platform.system() == "Windows":
        window = None
        try:
            gui_module = importlib.import_module("app")
            print("GUI import smoke test: OK")
            loop_count = gui_module.qsoundeffect_infinite_loop_count()
            if loop_count != -2:
                errors.append(f"GUI QSoundEffect loop compatibility returned {loop_count}, expected -2")
            else:
                print("GUI QSoundEffect loop compatibility: OK")

            from PyQt6.QtWidgets import QApplication
            qt_app = QApplication.instance() or QApplication([])
            window = gui_module.MainWindow()
            _cleanup_winrt_voice_probe(window)
            window.close()
            qt_app.processEvents()
            print("GUI MainWindow construction smoke test: OK")
        except Exception as exc:
            errors.append(f"GUI import/API/MainWindow smoke test failed: {type(exc).__name__}: {exc}")
            if window is not None:
                try:
                    _cleanup_winrt_voice_probe(window)
                    window.close()
                except Exception:
                    pass

    required_files = (
        ROOT / "app.py",
        ROOT / "story_engine.py",
        ROOT / "story_continuity.py",
        ROOT / "runtime_diagnostics.py",
        ROOT / "launcher.py",
        ROOT / "sequence_legacy.json",
        ROOT / "requirements.txt",
        ROOT / "audio_export.py",
        ROOT / "audio_mixer.py",
        ROOT / "storyboard_generator.py",
        ROOT / "prompt_profile_manager.py",
        ROOT / "ollama_client.py",
        ROOT / "media_package_generator.py",
        ROOT / "handoff_package.py",
        ROOT / "tts_services.py",
        ROOT / "tts_package_manager.py",
        ROOT / "tts_package_catalog.json",
        ROOT / "data" / "sounds" / "background.wav",
        ROOT / "data" / "mls_speaker_aliases.json",
        ROOT / "tools" / "list_winrt_voices.ps1",
        ROOT / "tools" / "synthesize_winrt.ps1",
        ROOT / "tools" / "synthesize_sapi.ps1",
        ROOT / "handoff_assets" / "build_story_video.py",
        ROOT / "handoff_assets" / "build_video.bat",
        ROOT / "handoff_assets" / "validate_handoff.py",
        ROOT / "scifi_console.py",
        ROOT / "requirements_console.txt",
        ROOT / "tools" / "audit_stories.py",
    )
    for path in required_files:
        if not path.is_file():
            errors.append(f"Required file is missing: {path.relative_to(ROOT)}")

    try:
        alias_payload = json.loads((ROOT / "data" / "mls_speaker_aliases.json").read_text(encoding="utf-8"))
        aliases = alias_payload.get("aliases", {}) if isinstance(alias_payload, dict) else {}
        if len(aliases) != 236:
            errors.append(f"MLS mnemonic alias count is {len(aliases)}, expected 236")
        if len(set(str(value) for value in aliases.values())) != len(aliases):
            errors.append("MLS mnemonic aliases are not unique")
        print(f"MLS mnemonic aliases: {len(aliases)}")
    except Exception as exc:
        errors.append(f"MLS mnemonic alias verification failed: {exc}")

    try:
        tts_packages = TtsPackageManager(ROOT, ROOT / "tts_package_catalog.json")
        if tts_packages.catalog_errors:
            errors.extend(f"TTS package catalog: {message}" for message in tts_packages.catalog_errors)
        print(f"TTS complete packages: {len(tts_packages.packages)}")
        if len(tts_packages.packages) < 10:
            errors.append(f"Expected at least 10 curated German TTS packages, got {len(tts_packages.packages)}")
    except Exception as exc:
        errors.append(f"TTS package catalog verification failed: {exc}")

    try:
        background_samples, background_rate = read_pcm_wav(ROOT / "data" / "sounds" / "background.wav")
        if background_samples.size == 0 or background_rate < 1:
            errors.append("Background WAV could not be decoded")
    except Exception as exc:
        errors.append(f"Background WAV verification failed: {exc}")

    try:
        before_state = state_path.read_bytes() if state_path.is_file() else None
        first = engine.generate(seed=60_027)
        second = engine.generate(seed=60_027)
        if first.raw_story != second.raw_story or first.branch_path != second.branch_path:
            errors.append("Explicit seeded story generation is not deterministic")
        if not first.display_story or len(first.selections) < 25 or not first.branches:
            errors.append("Deterministic branched test generation returned incomplete output")
        terminal_sources = tuple(Path(item.source).name for item in first.selections[-4:])
        expected_terminal = (
            "mission_free_space.ini",
            "mission_end_status.ini",
            "ship_liftoff_jumpready.ini",
            "mission_jump_prompt.ini",
        )
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
