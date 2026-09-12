# SciFi-Generator v60.22 — direkte Tab-Struktur

Die sechs Hauptkategorien bleiben **Mission**, **Medienpaket**, **Sprache & Audio**, **Sprachmanager**, **Story & Trace** und **Einstellungen**.

Ab v60.22 gibt es innerhalb dieser Tabs keine zusätzliche Auf-/Zuklapp-Navigation mehr. Einstellungen werden direkt in normalen `QGroupBox`-Bereichen angezeigt. Dadurch muss der Benutzer nicht erst einen Tab öffnen und anschließend innerhalb desselben Tabs weitere Bereiche aufklappen.

## Medienpaket

Direkt sichtbar sind je nach gewählter Ausgabeart:

- Ziel und Ausgabe
- Video, Stimme und Übergänge
- Lieferumfang des Ergebnis-ZIP
- Prompt-Verfeinerung mit Ollama
- Produktionsaktionen

Bei **Nur Bildserie** werden lediglich die für ein Video-Gesamtpaket sachlich irrelevanten Gruppen ausgeblendet; dies ist keine Einklappfunktion.

## Sprache & Audio

Direkt sichtbar sind:

- lokale Sprachausgabe und Stimmenwahl
- Piper-Optionen, sofern tatsächlich eine Piper-Stimme gewählt wurde
- Wiedergabe- und Audioexportsteuerung
- Brückenatmosphäre

Der Piper-Bereich ist kontextabhängig und erscheint nur bei Piper, weil seine Optionen für Windows-/Qt-Stimmen nicht anwendbar sind.

## v60.21-Startfehler

PyQt6 6.11 stellt `QSoundEffect.Infinite` nicht als direktes Klassenattribut bereit. v60.22 verwendet für `setLoopCount()` den dokumentierten Qt-Wert `-2` über eine kompatible Hilfsfunktion. Zusätzlich konstruiert der Windows-Installationsprüfer testweise ein `MainWindow`, damit vergleichbare Fehler künftig vor dem Auto-Start erkannt werden.
