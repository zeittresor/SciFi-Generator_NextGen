# Changelog

## 60.26 — 2026-09-12

- Fiktive MLS-Merknamen bleiben optional erhalten, sind bei neuen/frischen Konfigurationen nun standardmäßig ausgeschaltet.
- Bereits gespeicherte Konfigurationen und Konfigurationsprofile behalten ihre explizite Einstellung `mls_speaker_aliases`; ein bewusst aktivierter Zustand wird also nicht überschrieben.
- Beschriftung und Hilfetext der MLS-Aliasoption wurden präzisiert, damit frei erfundene Vornamen nicht als reale Identität oder verlässliche Geschlechtsangabe missverstanden werden.
- `data/mls_speaker_aliases.json` auf Formatversion 2 angehoben und mit einem eindeutigen Hinweis zur rein mnemonischen Verwendung versehen.
- Dokumentation `docs/MLS_ALIASES_v60.26.md` ergänzt.

## 60.25 — 2026-09-12

- Sprachmanager-Paketliste unterstützt jetzt Sortierung per Klick auf jeden Spaltenkopf; ein zweiter Klick kehrt die Sortierreihenfolge um.
- Besonders die Spalte **Status** kann damit installierte und verfügbare Sprachpakete unmittelbar gruppieren.
- Spaltenbreiten sind nun per Maus am Trenner frei veränderbar; der bisherige Stretch-Modus der ersten Spalte blockiert die Größenänderung nicht mehr.
- Komplette Spalten können per Drag & Drop neu angeordnet werden.
- Spaltenbreiten, Reihenfolge, Sortierspalte und Sortierrichtung werden automatisch gespeichert und in Konfigurationsprofile übernommen.
- Beim Neuaufbau der Paketliste wird Sortierung intern kurz deaktiviert und danach wiederhergestellt, damit Zeilen beim Einfügen konsistent bleiben.
- Neue Regressionstests und Dokumentation für die interaktive Sprachmanager-Tabelle.

## 60.24 — 2026-09-12

- Für alle 236 Sprecher des Piper-Modells MLS Deutsch wurden stabile, frei erfundene Vornamen als Merkhilfe ergänzt; die Zuordnung liegt extern in `data/mls_speaker_aliases.json`.
- Die Alias-Anzeige ist unter **Einstellungen → Sprachoptionen** abschaltbar; ohne Aliase bleiben Sprecherposition und originale MLS-ID sichtbar.
- Neuer Bereich **Konfigurationsprofile** zum Speichern und sofortigen Laden vollständiger Einstellungen als JSON.
- Laufende Einstellungen werden nun verzögert automatisch und atomar gespeichert, statt ausschließlich beim normalen Beenden.
- Bugfix: Der Story-Seed wird nun tatsächlich in der persistenten Konfiguration und in Konfigurationsprofilen gespeichert und wiederhergestellt.
- Bugfix: Gespeicherte OneCore-/SAPI-Stimmen werden nach ihrem asynchronen Einlesen zuverlässig wiederhergestellt; ein temporärer Fallback überschreibt die gewünschte Voice-ID nicht mehr.
- Konfigurationsimport akzeptiert zusätzlich ältere reine `settings.json`-Schnappschüsse.
- README-Bedienungstext korrigiert: Seit v60.22 sind die Optionsgruppen in den Kategorie-Tabs direkt sichtbar und nicht mehr einklappbar.
- Zusätzliche Verifikation für Aliasdatei, Profilfunktionen, Seed-Persistenz, atomisches Autosave und stabile Voice-Wiederherstellung.

## 60.23 — 2026-09-12

- MLS Deutsch wird jetzt als echtes Piper-Mehrsprecher-Modell behandelt; alle 236 `speaker_id_map`-Einträge werden auswählbar gemacht.
- Große Mehrsprecher-Modelle verwenden eine direkt sichtbare, vertikal scrollbare Sprecherliste statt eines Such-/Texteingabefelds oder einer überlangen ComboBox.
- Die Liste zeigt fortlaufende Sprecherposition, Piper-Speaker-ID und die originale MLS-Dataset-ID; der Benutzer muss keine ID vorab kennen.
- Die MLS-Sprecherauswahl wird pro Paket gespeichert und für Live-TTS sowie WAV-/MP3-Export übernommen.
- Kleine Piper-Stilsets wie Thorsten Emotional bleiben bewusst als kompakte ComboBox erhalten.
- Doppelte Bezeichnung `MLS Deutsch (236 Sprecher) (medium / 236 Sprecher)` aufgeräumt.

## 60.22 — 2026-09-12

- Hotfix für den Startabbruch von v60.21: die Endlosschleife von `QSoundEffect` wird bindungsübergreifend als dokumentierter Loop-Wert `-2` gesetzt, statt direkt auf das in PyQt6 6.11 nicht vorhandene `QSoundEffect.Infinite` zuzugreifen.
- Der Windows-Installationsprüfer importiert die GUI nicht mehr nur, sondern erzeugt testweise auch ein vollständiges `MainWindow` und schließt es wieder. Dadurch werden Qt-API-Fehler in `__init__` bereits während der Installation erkannt.
- Die zusätzliche Einklapp-Ebene innerhalb der bereits kategorisierten Tabs wurde vollständig entfernt. Video-/Stimmenoptionen, Ergebnis-ZIP, Ollama, lokale Sprachausgabe, Brückenatmosphäre und Einstellungen erscheinen nun direkt als normale Gruppen in ihrem jeweiligen Tab.
- Veraltete `CollapsibleSection`-Widgets und zugehörige Theme-Regeln entfernt; die Tabs sind damit die einzige primäre Navigationsebene.
- Statuszusammenfassungen bleiben erhalten, ohne Bedienelemente zu verstecken.
- README, GUI-Tests und Installationsverifikation an das direkte Tab-Layout angepasst.

## 60.21 — 2026-09-12

- Live-Brückenatmosphäre von einem zweiten `QMediaPlayer` auf einen dedizierten `QSoundEffect` mit vollständiger Endlosschleife umgestellt; besonders relevant bei paralleler Piper-/WinRT-Narration.
- Race Condition beim Abbruch laufender Piper- und WinRT-Prozesse behoben: Prozessverbindungen werden vor `kill()`/`waitForFinished()` getrennt, damit verspätete Qt-Signale keinen neuen TTS-Zustand übernehmen oder doppelte Bereinigung auslösen.
- Ein Stimmenwechsel während aktiver Wiedergabe/Synthese stoppt die alte Anforderung nun kontrolliert, bevor die neue Stimme aktiviert wird.
- Neue optionale Einstellung **Erweitertes Laufzeit-Fehlerprotokoll schreiben**.
- Laufzeitdiagnose protokolliert Breadcrumbs für Stimmenwahl, TTS-Zustände, Story-Erzeugung, Hintergrundsound und Audioexport sowie Python-Tracebacks; `faulthandler` wird bei aktivierter Diagnose ebenfalls eingeschaltet.
- Neue Dokumentation `docs/RUNTIME_DIAGNOSTICS_v60.21.md`.

## 60.20 — 2026-09-12

- Fixed direct MP3 export with older FFmpeg builds. The story exporter no longer sends the unsupported `-hide_banner` option and now uses long-established `-acodec libmp3lame -ab 192k` syntax. WAV export is unchanged.
- Added Piper prosody presets under **Sprache & Audio**. `Stabil / gleichmäßig` is the new default (`noise_scale=0.45`, `noise_w=0.35`) to reduce sentence-to-sentence voice/rhythm modulation; `Natürlich` uses the model defaults and `Ausdrucksstärker` deliberately allows more variation.
- Thorsten Emotional is now represented as one installed voice plus a dedicated **Emotion / Stil** selector instead of eight separate voice entries. The eight upstream styles are Amused, Angry, Disgusted, Drunk, Neutral, Sleepy, Surprised and Whisper; the GUI presents German labels and uses Neutral by default.
- Piper style and prosody settings are used consistently for live playback and WAV/MP3 export; the selected Thorsten Emotional style is also reflected in media-package voice metadata.
- Existing v60.18/v60.19 saved Thorsten Emotional voice IDs such as `package:7` are migrated to the new dedicated style selector where possible.
- Added regression tests for the Thorsten Emotional selector, Piper stability arguments and legacy-compatible FFmpeg MP3 arguments.

## 60.19 — 2026-09-12

- Hotfix: `pyqtSlot` wird in `app.py` jetzt korrekt aus `PyQt6.QtCore` importiert. In v60.18 führte der fehlende Import bereits beim Laden des Moduls zu einem `NameError`, noch bevor das Hauptfenster oder die normale Protokollierung gestartet werden konnte.
- Neuer robuster `launcher.py`: Startfehler beim Import oder bei der GUI-Initialisierung werden unabhängig von der eigentlichen Anwendung nach `logs/startup_error.log` geschrieben.
- `start_app.bat` und der Auto-Start des Installers verwenden den Diagnose-Launcher. Der manuelle Start zeigt bei einem Fehler zusätzlich den Pfad zur Logdatei an.
- Installationsprüfung und Regressionstests prüfen nun explizit auf den zuvor übersehenen PyQt-Decorator-Import.
- Keine Story-, TTS-Paket- oder Medienfunktionen aus v60.18 wurden entfernt.

## 60.18 — 2026-09-12

- Added a dedicated **Sprachmanager** category for downloadable/local reusable TTS complete packages.
- Added Piper as a fourth local playback backend alongside Windows OneCore/WinRT, SAPI and Qt TextToSpeech.
- Added ten curated German Piper package definitions: Eva K, Karlsson, Kerstin, MLS, Pavoque, Ramona, Thorsten low/medium/high and Thorsten Emotional.
- Piper packages automatically provide the standalone runtime, runtime libraries/espeak-ng data, ONNX model and matching JSON configuration below `tts_packages/`; no system-wide Piper installation is required.
- Added reuse-before-download discovery for existing Piper runtimes, runtime archives and exact matching model/config files in the application/project tree and common user download/document locations.
- Shared one Piper runtime between multiple voice packages and kept the runtime/cache when an individual voice is removed.
- Stored managed runtime/model paths relative to the portable application directory so installed packages survive moving the complete SciFi-Generator folder.
- Added checksum/size verification for voice models/configurations and hardened ZIP/TAR extraction against path traversal and TAR links.
- Added Piper playback with speed control, pause/resume, bridge ambience and Piper-based WAV/MP3 export including narration-volume mixing.
- Added Windows x86_64 and Linux x86_64/aarch64 runtime definitions to the TTS package catalog while keeping the dependency-free console frontend unchanged.
- Added a direct **Weitere Stimmen …** button from Speech & Audio and a View-menu shortcut to the Voice Manager.
- Escaped literal ampersands in Qt tabs/buttons/actions, removing the unintended mnemonic underlines previously visible in `Sprache & Audio` and `Story & Trace`.
- Added TTS package-manager regression tests, including fully offline reuse installation, portable-folder relocation and malicious archive traversal checks.

## 60.17 — 2026-09-10

- Replaced the desktop GUI toolkit from PySide6 with PyQt6 while keeping the cross-platform standard-library console frontend independent of any Qt package.
- Rebuilt the main window around five task-oriented category tabs: Mission, Medienpaket, Sprache & Audio, Story & Trace, and Einstellungen.
- Removed the old side-by-side expandable control-panel workflow; story, trace and production prompt now live in a dedicated analysis workspace with nested tabs.
- Added a persistent application header, version badge and bottom status/progress strip so navigation no longer hides execution state.
- Moved the primary story workflow into a focused Mission page and separated media production, local speech/audio and configuration from it.
- Kept rarely used video, result-ZIP and Ollama settings collapsible inside the Media Package page and preserved their saved state.
- Added migration logic so Audio and Settings pages are expanded once when upgrading from the older collapsible-panel layout.
- Changed the fresh-install default theme to Aurora and expanded external theme styling for application headers, cards, category tabs, badges and status strips.
- Changed category pages to vertical scrolling without normal horizontal scrolling and retained responsive font/layout scaling.
- Updated Windows dependencies, documentation and regression checks from PySide6 to PyQt6.

## 60.16 — 2026-09-10

- Added a standard-library-only command-line frontend (`scifi_console.py`) for Windows, Linux and macOS; pure story generation no longer requires PyQt6, TTS, NumPy or FFmpeg.
- Added CLI options for deterministic seeds, multi-story generation, raw/display output, JSON, output files, structural validation and full route enumeration.
- Added `--trace`, which records the chosen branch path and every selected fragment in exact output order with source filename and original line number for debugging awkward transitions.
- Added `start_console.bat`, executable `run_console.sh` and a dependency-free `requirements_console.txt`.
- Expanded the branching storyline with distress/rescue missions, ship-system malfunctions, branch-specific mid-mission detours and a late post-mission twist before the final jump position.
- Increased the sequence to six main mission families and 200 structurally reachable branch routes while retaining deterministic seed-derived routing.
- Added an explicit terminal invariant shared by every route: `mission_free_space.ini` → `mission_end_status.ini` → `ship_liftoff_jumpready.ini` → `mission_jump_prompt.ini`. Every storyline therefore returns to free space and a stable jump-ready state.
- Added 59 new sentence-fragment files for the new branches, each with seven initial alternatives (413 branch-specific lines).
- Expanded all 218 sentence-fragment files by another seven documented alternatives each (1,526 additions before quality repairs); the final library contains 4,306 non-empty unique selectable lines.
- Added combination repairs for grammatically incompatible fragment families, duplicate-name avoidance, punctuation cleanup and repeated-stock-clause avoidance while preserving intentional phonetic TTS spellings. The repair manifest documents 298 historical lines that were intentionally rewritten or removed.
- Normalized the temperature-description chain to a shared lower/upper-bound grammar frame so every temperature prefix can safely combine with every following connector and value.
- Added machine-readable v60.16 expansion/repair manifests plus a cross-platform mass-story audit tool.
- Mass-tested 10,000 deterministic stories with all 200 routes observed and no structural/text sanity findings; expanded automated regression coverage for the CLI, trace output, terminal invariant and sentence-library integrity.

## 60.15 — 2026-08-22

- Replaced the formerly linear mission sequence with a deterministic weighted branching engine while preserving the original alien route as one complete branch.
- Added four equal-weight main mission families and ten currently reachable concrete paths: alien encounter; natural forces, destructive flora or fauna; debris field, unknown station, restricted zone or space phenomenon; abandoned surface or orbital location.
- Added sequence-format-v2 `branch` and `scene` steps. Nested branch choices are data-driven in `sequence_legacy.json` and can be extended or reweighted without changing the Python engine.
- Added an independent seed-derived branch RNG, so a route stays reproducible even when sentence files later gain or lose alternatives.
- Added branch decisions and the complete branch path to the generation log.
- Added branch-aware storyboard boundaries and visual-bible generation so total-package prompts only describe planets, aliens, flora, fauna, stations, ruins or phenomena that actually occur in the selected story.
- Added 72 new sentence-fragment INI files, each with exactly seven alternatives: 504 new lines. The complete library now contains 159 INI files and 2,367 non-empty selectable fragments.
- Added `data/branch_fragments_v60.15.json` and `docs/STORY_BRANCHES_v60.15.md`; preserved the previous linear sequence as `sequence_legacy_v60.14.json`.
- Expanded regression coverage for all ten routes, deterministic branch selection, branch-specific source isolation and ten storyboard boundaries per route.

## 60.14 — 2026-07-29

- Expanded every one of the 87 existing sentence-fragment INI files by exactly seven context-appropriate alternatives.
- Added 609 new selectable fragment lines, increasing the non-empty fragment library from 1,254 to 1,863 lines.
- Preserved all existing lines and intentional phonetic spellings used for legacy Windows TTS pronunciation.
- Added `data/fragment_expansion_v60.14.json` as a machine-readable record of every new line.
- Added `docs/SENTENCE_FRAGMENT_EXPANSION_v60.14.md` with per-file before/after counts.
- Added regression tests that verify all 87 files contain their seven documented additions.

## 60.13 — 2026-07-19

- Reworked the total-package handoff to follow the improved package style with `00_START_HERE.txt`, `README_HANDOFF.txt`, a root-level `style_reference.png`, verification files and a complete `offline_fallback/` tree.
- Added the cinematic CGI/3D style reference as a mandatory visual quality anchor and strengthened prompts against flat 2D, vector, cutout, low-poly, poster, collage and storyboard output.
- Kept executable build, audio and TTS files both at the ZIP root and under `offline_fallback/` so target LLMs cannot incorrectly report that the required scripts are missing.
- Added configurable final result-ZIP contents: always include the finished video, optionally include scene images, scene audio/final mix, individual clips and project/build files.
- Updated the offline build script so the final result ZIP follows the selected delivery contents while still generating all intermediates required to build the video.
- Added selectable video frame rates with 8 fps as the default for mostly static illustrated stories.
- Strengthened natural/neural voice quality rules, style-reference validation, manifest metadata, delivery checklists and handoff archive verification.
- Updated German-first documentation, installer verification and automated tests.

## 60.12 — 2026-07-19

- Rebuilt the total-package handoff ZIP as an executable production handoff rather than a prompt-only archive.
- Added the root-level files `00_EXECUTE_THIS_TASK.txt`, `01_PRODUCTION_PROMPT.txt`, `TASK.json`, `build_story_video.py`, `build_video.bat` and `requirements.txt`.
- Added complete WinRT and SAPI voice-list and synthesis helpers to every handoff ZIP.
- Added a real offline builder that accepts generated scene images, creates or reuses per-scene narration, mixes the embedded bridge ambience into `final_mix.wav`, builds scene clips, applies crossfades, verifies the MP4 audio stream and creates the final ZIP.
- Added hard post-write archive validation; the app deletes and rejects a handoff ZIP if any required file, scene declaration or background asset is missing.
- Added machine-readable `TASK.json` with `mode=execute_now` and an explicit contract that missing output media are expected production results, not archive defects.
- Strengthened the ChatGPT production instruction to prohibit analysis-only responses and false reports that the bundled build scripts are missing.
- Added the selected Windows voice ID and backend key to the media manifest for reliable offline TTS selection.
- Reworked the compact interface with a wider default window, vertically arranged primary choices, readable status cards, shorter collapsible headers and separate wrapping summaries.
- Added visual emphasis for the primary package-generation action and clearer hierarchy for optional controls.
- Expanded regression tests and installer verification for the executable handoff assets.

## 60.11 — 2026-07-19

- Reorganized the control panel around the primary workflow: calculate story, create complete media-package instruction, then save the handoff ZIP.
- Moved the media-package workflow above secondary playback and configuration controls.
- Added reusable collapsible sections for optional settings.
- Video resolution, voice preferences and transitions are now grouped under a closed-by-default optional media section.
- Ollama prompt refinement is now a separate closed-by-default optional section.
- Local voice selection, playback controls, audio export and bridge ambience are grouped into a closed-by-default audio section.
- Generation details and general settings/themes are also collapsible and closed by default.
- Collapsed headers display concise summaries of active values such as resolution, voice character, Ollama mode, selected voice, ambience and theme.
- Expansion states are persisted in `settings.json`.
- Kept vertical and horizontal scrolling for small windows and display scaling.
- Added regression coverage for the collapsible interface.

## 60.10 — 2026-07-19

- Changed the default storyboard output to the complete video/TTS/background/ZIP package instead of the image-only mode.
- Renamed the image-only option to make it explicit that it produces no narration, background mix or video.
- Added a recommended total-package handoff ZIP containing the production prompt, full story, manifest, delivery checklist and the actual configured `background.wav`.
- Added internal total-package prompt validation to prevent an image-series document from being saved as a complete media-production request.
- Added a hard completion gate: an archive containing only scene images is explicitly incomplete.
- Strengthened prompts to continue automatically after image generation with TTS, audio mixing, scene timing, video assembly and ZIP creation.
- Added mandatory final-audio verification, including a non-silent MP4 audio stream and audible background ambience when enabled.
- Warned users that a plain TXT prompt cannot embed the background audio and recommends the handoff ZIP instead.
- Added handoff-package regression tests and updated the German-first public documentation.

## 60.9 — 2026-07-19

- Added configurable final-video resolutions for total media-package prompts.
- Changed the default package resolution to 1024 × 1024 with a 1:1 aspect ratio.
- Added presets for 512 × 512, 1024 × 1024, 1280 × 720, 1280 × 768, 1920 × 1080, 2560 × 1440 and 3840 × 2160.
- Added custom width and height fields from 256 to 8192 pixels.
- Added automatic aspect-ratio calculation and a live format description in the GUI.
- Added explicit width, height, resolution and aspect-ratio fields to media-package manifests.
- Added production rules preventing disproportionate stretching and requiring controlled crop, letterbox or pillarbox handling.
- Persisted the selected resolution profile and custom dimensions in settings.json.
- Updated examples, README, package validation and automated tests.

## 60.8 — 2026-07-19

- Added total-package voice-character selection: human/natural, neutral or robotic/synthetic.
- Added selectable feminine, masculine, neutral/androgynous or unrestricted voice presentation.
- Added a TTS quality target with best-available, high-quality and standard/fast options.
- Added explicit production rules that prevent low-quality eSpeak/robotic fallbacks when a natural voice is requested.
- Added compatibility-based fallback handling: unavailable or unsuitable preferred voices must be replaced by the closest matching voice and every substitution must be recorded in the manifest and production log.
- Extended media-package manifests, saved settings, generated prompts, examples, tests and German-first documentation with the new voice requirements.

## 60.7 — 2026-07-18

- Added a selectable output type for either a pure image series or a complete illustrated-audio-story production package.
- Added target-specific total-package instructions for ChatGPT, Grok, Gemini, Stable Diffusion and custom systems.
- Added exact per-scene narration text, separate image/audio/clip filenames, audio-driven visual timing and configurable crossfade duration.
- Added video requirements for 1920×1080, 30 fps, H.264/AAC output and an ordered scene assembly workflow.
- Added ZIP-package requirements covering final video, images, scene audio, clips, prompts, manifest and production log.
- Added an explicit offline fallback requesting a complete Python/FFmpeg build package with Windows SAPI/WinRT TTS, progress reporting, logging and cancellation.
- Extended JSON export, prompt profiles, installation verification, examples, tests and German-first documentation.

## 60.6 — 2026-07-18

- Added a required target-AI selector for ChatGPT, Grok, Gemini, Stable Diffusion and a freely named Other system.
- Added external JSON prompt profiles in `prompt_profiles/`, including reload and diagnostics actions.
- Added an explicit image-series execution instruction at the beginning of every storyboard export so a fresh chat is told to generate images instead of merely analysing the text.
- Added a global visual series bible covering ship, system, planet, alien, style, aspect ratio, continuity and excluded elements.
- Added target-specific scene wrappers and workflow guidance. Stable Diffusion output now uses separate positive prompts plus a global negative prompt and warns that scenes must be submitted individually.
- Added target-aware Ollama refinement; diffusion targets request compact English positive prompts while conversational targets receive natural-language generation instructions.
- Extended TXT/Markdown and JSON exports with target AI, target mode, aspect ratio and the complete executable instruction document.
- Updated installer verification, public documentation and tests for all five external prompt profiles.

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
