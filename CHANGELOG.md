# Changelog

## 60.5 — 2026-07-18

- Added an optional storyboard / image-prompt feature with 6 to 10 key scenes per generated story.
- Added a dedicated **Bild-Prompts** tab and a hidden-by-default prompt view alongside story and generation log.
- Added local rule-based prompt generation that derives scene prompts directly from the known story structure.
- Added optional Ollama integration for refining the locally prepared prompts when a local Ollama server and model are available.
- Added Ollama model refresh, diagnostics, prompt export and graceful fallback to local prompt generation.
- Updated the German-first README and package tests to cover the new storyboard workflow.

## 60.4 — 2026-07-18

- Added explicit jump lifecycle tracking: a calculated story can be completed once and then requires a newly calculated sector jump.
- Added lightly irritated spoken notices for attempts to jump without a calculated story or to replay an already completed jump.
- Kept interrupted or failed narration retryable so a manual stop does not consume the current story.
- Added WAV audio export using the selected Windows voice, speech rate, voice volume, bridge ambience setting and background volume.
- Added asynchronous export progress with phase descriptions and cancellation.
- Added optional MP3 export when `tools/ffmpeg.exe` or an FFmpeg executable in PATH is available.
- Added native WinRT and SAPI file-synthesis paths plus automatic matching of Qt voice names to exportable Windows voices.
- Added a PCM WAV mixer that loops the configured background sound to the narration length and prevents clipping.
- Added external sentence files for the two spoken invalid-jump states.
- Updated installer verification, tests and German-first public documentation.

## 60.3 — 2026-07-17

- Added automatic responsive UI scaling when the application window is enlarged.
- Font size, buttons, input fields, sliders, checkboxes, spacing, tabs and scroll bars now scale together up to a controlled maximum.
- Small windows no longer shrink controls below their normal readable size; vertical and horizontal scrolling is used instead.
- Changed the controls container to an expanding minimum-size layout so group boxes keep their natural geometry.
- Added long-row wrapping to form layouts for voice, seed and theme fields.
- Updated every generated theme stylesheet so dimensional metrics follow the current UI scale while all colors remain external JSON values.
- Kept the README German-first with only a concise English summary at the end.

## 60.2 — 2026-07-17

- Added a dedicated scroll area for the complete control panel so widgets retain their natural height instead of being compressed.
- Vertical and horizontal scroll bars now appear automatically when the available window size or display scaling requires them.
- Increased the compact default window width slightly while allowing a smaller minimum size for narrow displays.
- Reworked the README to use German as the primary language, followed by a concise English summary.
- Added regression checks for the scrollable control layout and README language order.

## 60.1 — 2026-07-17

- Fixed the Windows installer verification failure caused by delayed expansion removing the exclamation mark from the inline `!=` comparison.
- Replaced the fragile inline Python verification command with `tools/verify_installation.py`.
- Added `version.txt` as the central version source for the application, installer and wheelhouse builder.
- Reworked the README for a general GitHub audience with public installation, usage, customization, privacy and troubleshooting information.
- Added installer-focused regression tests to prevent the original batch parsing issue from returning.

## 60.0 — 2026-07-17

- Restored the application name **SciFi-Generator** and continued the original numbering as v60.0.
- Story and generation log are hidden by default and can be toggled with a dedicated button, similar to the compact legacy window.
- Replaced hard-coded themes with external JSON files in `themes/`.
- Added the preferred themes Light, Dark, Sepia, Ocean, Matrix, Hellfire, Purple, Aurora, and Legacy Beige.
- Added automatic WCAG-style contrast validation for normal text, fields, buttons, hover states, selections, progress text, tooltips, and disabled controls.
- Added a theme diagnostics dialog and runtime theme reload.
- Expanded TTS discovery by combining Windows OneCore/WinRT voices, native Windows SAPI voices, and Qt voices.
- Added voice-source labels, voice refresh, and a TTS diagnostics dialog.
- Added asynchronous WinRT speech synthesis with pause, resume, and stop during playback.
- Updated installer, logs, settings metadata, documentation, and application title to v60.0.

## 0.1.0 — 2026-07-17

- Initial Python reconstruction from the supplied VB.NET source, generation log, screenshot and 85 sentence-fragment files.
- Preserved the original two-step workflow: calculate, then narrate.
- Added asynchronous Qt TTS, pause/stop, voice selection and independent volumes.
- Added deterministic seeds, complete versioned logs and configurable generation sequence.
- Added generic original bridge ambience; no third-party franchise audio included.
