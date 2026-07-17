from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from story_engine import APP_VERSION, StoryEngine, StoryEngineError  # noqa: E402
from theme_manager import ThemeManager  # noqa: E402


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

    required_files = (
        ROOT / "app.py",
        ROOT / "data" / "sounds" / "background.wav",
        ROOT / "tools" / "list_winrt_voices.ps1",
        ROOT / "tools" / "synthesize_winrt.ps1",
    )
    for path in required_files:
        if not path.is_file():
            errors.append(f"Required file is missing: {path.relative_to(ROOT)}")

    try:
        sample = engine.generate(seed=60_001)
        if not sample.display_story or len(sample.selections) < 80:
            errors.append("Deterministic test generation returned incomplete output")
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
