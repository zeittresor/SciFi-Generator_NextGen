from __future__ import annotations

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

    required_files = (
        ROOT / "app.py",
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
        ROOT / "data" / "vars" / "jump_missing_story.ini",
        ROOT / "data" / "vars" / "jump_story_already_used.ini",
    )
    for path in required_files:
        if not path.is_file():
            errors.append(f"Required file is missing: {path.relative_to(ROOT)}")

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
        if not sample.display_story or len(sample.selections) < 80:
            errors.append("Deterministic test generation returned incomplete output")
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
                "Video: 1024x1024, 1:1",
                "Videofläche: 1024 × 1024 Pixel; Seitenverhältnis 1:1",
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
