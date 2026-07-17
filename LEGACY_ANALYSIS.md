# Legacy reconstruction notes

## Confirmed original workflow

- The old `Button2_Click` handler generated the story by calling, in order: `sternzeit`, `systemerreicht`, `planetenbeschreibung`, `planetlanding`, `aliengefunden`, `alienbehandlung`, `liftoff`, and `weghier`.
- The old `Button1_Click` handler optionally started `data/sounds/background.wav`, selected one line from `jumpdrive_activated.ini`, and then narrated the generated story.
- The old SAPI call was synchronous and therefore froze the Windows Forms interface during narration.
- The first random system-name fragment was stored and reused as the first part of the planet name.
- `gensil()` did not add its selections to the old log. The Python reconstruction logs these hidden syllable selections as well.

## Deliberately preserved behavior

- Every non-empty source line remains an independent random option.
- Sentence fragments are not grammatically repaired.
- Source spelling designed for Windows TTS is retained.
- The optional global `ae/ue/oe` conversion reproduces the legacy display/TTS style, including odd results such as `aktuell` becoming `aktüll`.
- Punctuation suffixes follow the old code and may therefore produce doubled full stops when a selected line already ends with punctuation.

## Intentional improvements

- Narration is asynchronous and the UI stays responsive.
- A generated story remains available after playback and can be replayed, but the Story/Log panel is hidden by default and opened only on request.
- Pause, resume, stop, combined OneCore/WinRT + native SAPI + Qt voice selection, separate volumes, and deterministic seeds are available.
- Blank-only lines are ignored by default because two legacy files contain trailing whitespace-only entries; the option can be disabled for exact bug compatibility.
- Logs include the app version, timestamp, seed, source path, source line number, raw story, and converted display/TTS story.
- No franchise audio is bundled. The included WAV is an original generic ambience and can be replaced.

## Legacy features not included in version 60.1

The original source also contained special executable-sidecar modes (`.ini`, `.ine`, `.snd`, `.slo`). These were unrelated to the two-button story workflow and are not part of the first reconstruction.
