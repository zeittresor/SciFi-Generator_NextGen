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

from story_engine import APP_VERSION, StoryEngine, StoryEngineError  # noqa: E402
from audio_mixer import read_pcm_wav  # noqa: E402
from theme_manager import ThemeManager  # noqa: E402
from prompt_profile_manager import PromptProfileManager  # noqa: E402
from storyboard_generator import generate_storyboard, render_storyboard_text  # noqa: E402
from media_package_generator import MediaPackageSettings, render_media_package_text  # noqa: E402
from tts_package_manager import TtsPackageManager  # noqa: E402


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

    engine = StoryEngine(ROOT / "data" / "vars", ROOT / "sequence_legacy.json")
    missing = engine.validate_sources()
    if missing:
        errors.append("Missing sentence files: " + ", ".join(missing))

    source_count = len(list((ROOT / "data" / "vars").glob("*.ini")))
    print(f"Sentence files: {source_count}")
    if source_count != 218:
        errors.append(f"Unexpected sentence-file count for v60.26: {source_count} (expected 218)")

    route_count = len(engine.enumerate_branch_routes())
    print(f"Structural branch routes: {route_count}")
    if route_count != 200:
        errors.append(f"Unexpected structural route count: {route_count} (expected 200)")
    terminal_errors = engine.validate_terminal_invariant()
    errors.extend(f"Terminal invariant: {message}" for message in terminal_errors)

    for ini_path in sorted((ROOT / "data" / "vars").glob("*.ini")):
        selectable = [text.strip().casefold() for _, text in engine._read_lines(ini_path, True)]
        if len(selectable) != len(set(selectable)):
            errors.append(f"Duplicate selectable fragment in: {ini_path.name}")

    manager = ThemeManager(ROOT / "themes")
    manager.load()
    print(f"Themes: {len(manager.themes)}")
    errors.extend(f"Theme: {message}" for message in manager.errors)

    prompt_manager = PromptProfileManager(ROOT / "prompt_profiles")
    prompt_manager.load()
    print(f"Prompt profiles: {len(prompt_manager.profiles)}")
    errors.extend(f"Prompt profile: {message}" for message in prompt_manager.errors)
    expected_prompt_profiles = {"ChatGPT", "Grok", "Gemini", "Stable Diffusion", "Andere"}
    missing_profiles = expected_prompt_profiles.difference(prompt_manager.profiles)
    if missing_profiles:
        errors.append("Missing target AI prompt profiles: " + ", ".join(sorted(missing_profiles)))

    requirements_text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    if "PyQt6>=6.7,<7" not in requirements_text:
        errors.append("GUI requirements do not declare PyQt6>=6.7,<7")
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    if "from PyQt6" not in app_source or "from PySide6" in app_source:
        errors.append("Desktop frontend is not fully migrated to PyQt6")
    first_import_block = "\n".join(app_source.splitlines()[:20])
    if "@pyqtSlot" in app_source and "pyqtSlot" not in first_import_block:
        errors.append("PyQt startup decorator pyqtSlot is used but not imported")
    for tab_token in (
        'addTab(mission_scroll, "Mission")',
        'addTab(media_scroll, "Medienpaket")',
        'addTab(audio_scroll, "Sprache && Audio")',
        'addTab(manager_scroll, "Sprachmanager")',
        'addTab(details_page, "Story && Trace")',
        'addTab(settings_scroll, "Einstellungen")',
    ):
        if tab_token not in app_source:
            errors.append(f"PyQt category tab is missing: {tab_token}")
    if "class CollapsibleSection" in app_source or "collapsibleHeader" in app_source:
        errors.append("Obsolete nested collapsible UI is still present; category tabs must show their controls directly")
    for group_token in (
        'QGroupBox("Video, Stimme und Übergänge")',
        'QGroupBox("Lieferumfang des Ergebnis-ZIP")',
        'QGroupBox("Prompt-Verfeinerung mit Ollama")',
        'QGroupBox("Lokale Sprachausgabe")',
        'QGroupBox("Brückenatmosphäre")',
    ):
        if group_token not in app_source:
            errors.append(f"Direct tab option group is missing: {group_token}")
    if 'QPushButton("Story & Trace anzeigen")' in app_source:
        errors.append("Literal ampersand in Story & Trace button still creates a Qt mnemonic underline")
    if "QSoundEffect" not in app_source or "background_effect.setLoopCount(qsoundeffect_infinite_loop_count())" not in app_source:
        errors.append("Bridge ambience is not using the compatible infinite QSoundEffect loop")
    if "QSoundEffect.Infinite" in app_source and "getattr(QSoundEffect, \"Infinite\", None)" not in app_source:
        errors.append("Direct QSoundEffect.Infinite access can crash on scoped-enum PyQt6 builds")
    if "Erweitertes Laufzeit-Fehlerprotokoll schreiben" not in app_source:
        errors.append("Runtime error-log option is missing from Settings")
    if '"runtime_error_log": self.runtime_error_log.isChecked()' not in app_source:
        errors.append("Runtime error-log option is not persisted")
    if "Fiktive Merknamen für MLS-Sprecher anzeigen" not in app_source:
        errors.append("Optional fictional MLS speaker aliases are missing from Settings")
    if "Konfiguration speichern …" not in app_source or "Konfiguration laden …" not in app_source:
        errors.append("Configuration profile save/load controls are missing")
    if '"seed": self.seed_spin.value()' not in app_source:
        errors.append("Seed is not persisted in the complete settings profile")
    if "_settings_autosave_timer" not in app_source or "_write_json_atomic" not in app_source:
        errors.append("Debounced atomic settings autosave is missing")

    if "self.piper_style_combo = QComboBox()" not in app_source:
        errors.append("Dedicated Piper style selector is missing")
    if "self.piper_prosody_combo = QComboBox()" not in app_source:
        errors.append("Piper prosody selector is missing")
    audio_export_source = (ROOT / "audio_export.py").read_text(encoding="utf-8")
    if '"-hide_banner"' in audio_export_source:
        errors.append("Direct MP3 exporter still depends on FFmpeg -hide_banner")
    if '"-acodec", "libmp3lame"' not in audio_export_source:
        errors.append("Legacy-compatible MP3 codec syntax is missing")

    # On the actual Windows installation PyQt6 is installed at this point. Importing
    # and constructing MainWindow catches both class-definition failures and Qt API
    # mismatches that only happen inside __init__ (the v60.21 QSoundEffect crash was
    # exactly such a case). The window is never shown.
    if platform.system() == "Windows":
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
            window.close()
            qt_app.processEvents()
            print("GUI MainWindow construction smoke test: OK")
        except Exception as exc:
            errors.append(f"GUI import/API/MainWindow smoke test failed: {type(exc).__name__}: {exc}")

    required_files = (
        ROOT / "app.py",
        ROOT / "runtime_diagnostics.py",
        ROOT / "launcher.py",
        ROOT / "data" / "sounds" / "background.wav",
        ROOT / "tools" / "list_winrt_voices.ps1",
        ROOT / "tools" / "synthesize_winrt.ps1",
        ROOT / "tools" / "synthesize_sapi.ps1",
        ROOT / "audio_export.py",
        ROOT / "audio_mixer.py",
        ROOT / "storyboard_generator.py",
        ROOT / "prompt_profile_manager.py",
        ROOT / "ollama_client.py",
        ROOT / "media_package_generator.py",
        ROOT / "handoff_package.py",
        ROOT / "handoff_assets" / "build_story_video.py",
        ROOT / "handoff_assets" / "build_video.bat",
        ROOT / "handoff_assets" / "requirements.txt",
        ROOT / "handoff_assets" / "audio_mixer.py",
        ROOT / "handoff_assets" / "style_reference.png",
        ROOT / "handoff_assets" / "validate_handoff.py",
        ROOT / "handoff_assets" / "tools" / "list_winrt_voices.ps1",
        ROOT / "handoff_assets" / "tools" / "list_sapi_voices.ps1",
        ROOT / "handoff_assets" / "tools" / "synthesize_winrt.ps1",
        ROOT / "handoff_assets" / "tools" / "synthesize_sapi.ps1",
        ROOT / "data" / "vars" / "jump_missing_story.ini",
        ROOT / "data" / "vars" / "jump_story_already_used.ini",
        ROOT / "data" / "branch_fragments_v60.15.json",
        ROOT / "data" / "branch_fragments_v60.16.json",
        ROOT / "data" / "fragment_expansion_v60.16.json",
        ROOT / "data" / "fragment_repairs_v60.16.json",
        ROOT / "data" / "mls_speaker_aliases.json",
        ROOT / "scifi_console.py",
        ROOT / "run_console.sh",
        ROOT / "start_console.bat",
        ROOT / "requirements_console.txt",
        ROOT / "tools" / "audit_stories.py",
        ROOT / "docs" / "CONSOLE_v60.16.md",
        ROOT / "docs" / "STORY_BRANCHES_v60.16.md",
        ROOT / "docs" / "GUI_v60.17.md",
        ROOT / "docs" / "TTS_PACKAGES_v60.18.md",
        ROOT / "docs" / "TTS_PACKAGES_v60.20.md",
        ROOT / "docs" / "RUNTIME_DIAGNOSTICS_v60.21.md",
        ROOT / "docs" / "GUI_v60.22.md",
        ROOT / "docs" / "PIPER_MULTISPEAKER_v60.23.md",
        ROOT / "docs" / "SETTINGS_PROFILES_v60.24.md",
        ROOT / "docs" / "VOICE_MANAGER_TABLE_v60.25.md",
        ROOT / "docs" / "MLS_ALIASES_v60.26.md",
        ROOT / "tts_package_manager.py",
        ROOT / "tts_package_catalog.json",
        ROOT / "data" / "vars" / "mission_free_space.ini",
        ROOT / "data" / "vars" / "mission_end_status.ini",
        ROOT / "data" / "vars" / "mission_jump_prompt.ini",
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
        if aliases.get("2") != "Mirko":
            errors.append("Stable MLS alias mapping changed unexpectedly for speaker 003")
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
        package_ids = {item.package_id for item in tts_packages.packages}
        for package_id in (
            "piper-de-eva-k-x-low", "piper-de-karlsson-low", "piper-de-kerstin-low",
            "piper-de-mls-medium", "piper-de-pavoque-low", "piper-de-ramona-low",
            "piper-de-thorsten-low", "piper-de-thorsten-medium", "piper-de-thorsten-high",
            "piper-de-thorsten-emotional-medium",
        ):
            if package_id not in package_ids:
                errors.append(f"Missing curated TTS package: {package_id}")
        emotional = tts_packages.package("piper-de-thorsten-emotional-medium")
        if emotional is None or not emotional.speaker_selector:
            errors.append("Thorsten Emotional does not enable the dedicated style selector")
        elif emotional.default_speaker != "neutral":
            errors.append(f"Thorsten Emotional default speaker is {emotional.default_speaker!r}, expected 'neutral'")
        mls = tts_packages.package("piper-de-mls-medium")
        if mls is None or not mls.speaker_selector:
            errors.append("MLS Deutsch does not enable the 236-speaker selector")
        elif mls.speaker_selector_label != "Sprecher":
            errors.append(f"MLS Deutsch selector label is {mls.speaker_selector_label!r}, expected 'Sprecher'")
        elif mls.default_speaker != "2422":
            errors.append(f"MLS Deutsch default speaker is {mls.default_speaker!r}, expected '2422'")
    except Exception as exc:
        errors.append(f"TTS package catalog verification failed: {exc}")

    try:
        background_samples, background_rate = read_pcm_wav(
            ROOT / "data" / "sounds" / "background.wav"
        )
        if background_samples.size == 0 or background_rate < 1:
            errors.append("Background WAV could not be decoded")
    except Exception as exc:
        errors.append(f"Background WAV verification failed: {exc}")

    try:
        sample = engine.generate(seed=60_001)
        if not sample.display_story or len(sample.selections) < 25 or not sample.branches:
            errors.append("Deterministic branched test generation returned incomplete output")
        terminal_sources = tuple(Path(item.source).name for item in sample.selections[-4:])
        expected_terminal = (
            "mission_free_space.ini",
            "mission_end_status.ini",
            "ship_liftoff_jumpready.ini",
            "mission_jump_prompt.ini",
        )
        if terminal_sources != expected_terminal:
            errors.append(f"Generated story does not end jump-ready: {terminal_sources!r}")
        scenes = generate_storyboard(sample, 8)
        for profile_name in expected_prompt_profiles:
            profile = prompt_manager.get(profile_name)
            if profile is None:
                continue
            document = render_storyboard_text(
                scenes,
                source="Verification",
                profile=profile,
                custom_target_name="Custom target" if profile_name == "Andere" else "",
            )
            if "AUSFÜHRBARER BILDSERIEN-AUFTRAG" not in document or "scene_01.png" not in document:
                errors.append(f"Prompt profile render failed: {profile_name}")
            package_document = render_media_package_text(
                scenes,
                full_story=sample.display_story,
                source="Verification",
                profile=profile,
                custom_target_name="Custom target" if profile_name == "Andere" else "",
                settings=MediaPackageSettings(
                    voice_name="Verification Voice",
                    voice_character="Menschlich / natürlich",
                    voice_gender="Weiblich",
                    voice_quality="Beste verfügbare Qualität",
                ),
            )
            required_package_markers = (
                "GESAMTPAKET-PRODUKTIONSAUFTRAG",
                "scene_01.wav",
                "Stimmcharakter: Menschlich / natürlich",
                "Stimmliche Wirkung: Weiblich",
                "TTS-Qualitätsziel: Beste verfügbare Qualität",
                "Video: 1024x1024, 1:1, 8 fps",
                "Videofläche: 1024 × 1024 Pixel; Seitenverhältnis 1:1",
                "Stilreferenz: style_reference.png",
                "LIEFERUMFANG DES FINALEN ERGEBNIS-ZIP",
                "SOFORT AUSFÜHREN, NICHT NUR DAS ARCHIV PRÜFEN",
                "build_story_video.py",
            )
            if not all(marker in package_document for marker in required_package_markers):
                errors.append(f"Media package render failed: {profile_name}")
    except StoryEngineError as exc:
        errors.append(f"Test generation failed: {exc}")

    print(f"Version: {APP_VERSION}")
    if errors:
        print("Verification failed:")
        for error in errors:
            print(f"  - {error}")
        return 1

    print("Verification: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
