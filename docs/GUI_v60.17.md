# SciFi-Generator v60.17 — PyQt6 GUI

v60.17 replaces the former PySide6 desktop frontend with PyQt6 and restructures the interface around tasks rather than a long vertical option stack.

## Category tabs

1. **Mission** — generate a sector-jump story, execute/narrate the jump and move directly to Story & Trace or Media Package.
2. **Medienpaket** — choose image-series vs total-package output, target LLM, scene count, video/voice settings, result-ZIP contents and optional Ollama refinement.
3. **Sprache & Audio** — installed voice selection, speaking rate, narration volume, playback controls, WAV/MP3 export and bridge ambience.
4. **Story & Trace** — nested tabs for the story itself, the exact branch/source/line trace, and the generated production prompt.
5. **Einstellungen** — seed, legacy text handling, logging, theme selection and file shortcuts.

A persistent bottom strip shows progress and current status regardless of the selected category. Category pages scroll vertically when needed and avoid horizontal scrolling in the normal layout.

## Themes

The existing JSON theme system remains external and editable. New object styles cover the application header, version/step badges, information cards, selected tabs and the status strip. **Aurora** is used as the default on a fresh installation; all previous themes remain available.

## Compatibility

The GUI requirements now use `PyQt6>=6.7,<7`. Windows SAPI and OneCore/WinRT integration are retained. The standalone `scifi_console.py` still depends only on Python 3.10+ standard-library functionality and therefore does not require PyQt6 under Windows, Linux or macOS.
