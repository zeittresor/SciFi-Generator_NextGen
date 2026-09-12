# SciFi-Generator v60.21 — Laufzeit-Diagnose

Unter **Einstellungen → Storygenerierung** kann **Erweitertes Laufzeit-Fehlerprotokoll schreiben** aktiviert werden.

Ist die Option aktiv, legt jede Programmsitzung eine Datei nach dem Schema
`logs/runtime_diagnostics_v60.21_YYYYMMDD_HHMMSS.log` an. Das Protokoll enthält bewusst nicht den vollständigen Storytext, sondern technische Breadcrumbs, die den Weg zu einem möglichen Fehler nachvollziehbar machen, darunter:

- Auswahl und Wechsel des TTS-Backends beziehungsweise der Stimme
- Start, Pause, Ende und Abbruch der Sprachausgabe
- Piper-/WinRT-Synthesezustände
- Start und Status der Brückenatmosphäre
- Story-Erzeugung inklusive Seed und gewähltem Branch-Pfad
- Audioexport mit Zieltyp und Hintergrundsound-Status
- Python-Ausnahmen mit Traceback und den zuletzt aufgezeichneten Breadcrumbs
- Python `faulthandler`, soweit die Laufzeitumgebung dies unterstützt

Die Option ist standardmäßig aus. `logs/startup_error.log` bleibt davon unabhängig und wird weiterhin vom Launcher für Fehler erzeugt, die bereits vor dem Aufbau der GUI auftreten.

## v60.21 Stabilitätsänderungen

Für die live abgespielte Brückenatmosphäre wird `QSoundEffect` statt eines zweiten `QMediaPlayer` verwendet. Der acht Sekunden lange WAV-Track bleibt resident und wird als vollständige Endlosschleife abgespielt, während Piper/WinRT ihren separaten Narrations-Player verwenden.

Beim Abbruch einer laufenden Piper- oder WinRT-Synthese wird die QProcess-Verknüpfung jetzt **vor** `kill()`/`waitForFinished()` getrennt. Dadurch kann ein verspätetes `finished`- oder `errorOccurred`-Signal einer alten Stimme nicht mehr den Zustand einer neu ausgewählten Stimme übernehmen oder dasselbe QProcess-Objekt doppelt bereinigen.
