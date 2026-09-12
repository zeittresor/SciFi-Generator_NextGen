# SciFi-Generator v60.20 — TTS complete packages

## Goal

The **Sprachmanager** installs additional local voices without requiring the user to install Piper or a model manually. Each catalog entry is treated as a complete usable package: the manager ensures that the native Piper runtime, its libraries and `espeak-ng-data`, the ONNX voice model and the matching JSON configuration are present below `tts_packages/`.

The main **Sprache & Audio** selector only exposes voices that are currently usable. Catalog entries that have not been installed remain visible only in the Sprachmanager.

## Included German Piper catalog

v60.20 contains package definitions for:

- Eva K — x-low
- Karlsson — low
- Kerstin — low
- MLS Deutsch — medium, 236-speaker model
- Pavoque — low
- Ramona — low
- Thorsten — low
- Thorsten — medium
- Thorsten — high
- Thorsten Emotional — medium, eight named styles/emotions

For ordinary small multi-speaker models, speaker IDs may still be represented as separate entries. **Thorsten Emotional is handled specially in v60.20:** it appears as one voice entry and exposes its eight styles through a dedicated **Emotion / Stil** selector in the Speech & Audio tab. The default style is `neutral` (speaker ID 4). Very large speaker maps such as MLS are deliberately represented by one normal selector entry using the model's default speaker so the combo box does not gain hundreds of items.

Thorsten Emotional exposes these upstream speaker/style IDs: `amused=0`, `angry=1`, `disgusted=2`, `drunk=3`, `neutral=4`, `sleepy=5`, `surprised=6`, `whisper=7`. The GUI displays German labels while Piper receives the unchanged numeric speaker ID.

## Portable runtime

The catalog currently uses the last standalone binary release from the original `rhasspy/piper` line (`2023.11.14-2`) on:

- Windows x86_64
- Linux x86_64
- Linux aarch64

This runtime is used because it is available as a complete native archive and therefore satisfies the application's no-extra-installation goal. Development of Piper has moved to `OHF-Voice/piper1-gpl`; the SciFi-Generator catalog is external so a future portable build or another local TTS engine can be added without redesigning the voice selector.

## Reuse before download

Before downloading, the manager scans for matching files in:

1. the SciFi-Generator directory,
2. its parent/project tree,
3. the user's Downloads directory,
4. the user's Documents directory,
5. the internal `tts_packages/_cache`.

A reusable runtime is accepted only when the Piper executable and `espeak-ng-data` are found together. Model and configuration files must match the exact size/checksum metadata from the package catalog. Matching files are copied into the managed package tree instead of being downloaded again.

The shared runtime is stored only once below `tts_packages/_engines`; multiple voices reuse it. Removing one voice therefore removes only that model package, not the runtime or download cache.

## Portability and security

`package.json` and `engine.json` store paths relative to the application directory where possible. Moving a completely configured SciFi-Generator folder therefore does not inherently invalidate installed voices.

Downloaded model/config files are verified against catalog checksums. ZIP and TAR members are checked before extraction to reject `..` path traversal and symbolic/hard links in TAR archives.

## Playback and export

Piper is started directly as a local process. Story text is sent through standard input and Piper writes a temporary WAV file. The normal Qt media player then handles play/pause and optional bridge ambience.

v60.20 adds three Piper prosody presets. **Stable** explicitly lowers `noise_scale` and `noise_w` to reduce stochastic timbre/rhythm changes between sentences; **Natural** lets the voice model use its configured values; **Expressive** increases variation. The same selected parameters are used for live playback and file export.

The same installed package can be used by **Story als Audiodatei speichern …**. Piper synthesis is available on supported Windows and Linux hosts; narration volume and the bridge background are mixed by the application's audio mixer before WAV/MP3 output. Direct MP3 encoding uses conservative FFmpeg syntax for compatibility with older Windows builds that do not support newer cosmetic command-line options.

## Catalog customization

`tts_package_catalog.json` is deliberately external. New package entries require an engine definition plus model/config URLs, checksums, sizes and source/license metadata. A package does not appear in the main voice selector until all required local files validate successfully.
