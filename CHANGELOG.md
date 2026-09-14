# Changelog

## v60.27 — Persistente Handlungsfäden über mehrere Sprünge

- Neues leichtgewichtiges Story-Gedächtnis (`story_continuity.py` / `story_state.json`) für fortlaufende Auswirkungen früherer Sprünge.
- Offene Handlungsfäden für Signale, Verfolger, Anomalien, Fremdkontakte, Rettungsfolgen und technische Nachwirkungen.
- Alte Fäden können nach späteren Sprüngen wieder auftauchen und sich auflösen, vertiefen, als falsche Fährte enden, auf Beobachtung bleiben oder bewusst offen bleiben.
- Persistenter abstrakter Schiffszustand für Integrität, Navigation, Sensorik, Antrieb und Energie.
- Reputation und unbekannte Aufmerksamkeit beeinflussen zukünftige Missionswahrscheinlichkeiten.
- Dynamische Gewichtung der sechs Hauptrouten und Dämpfung unmittelbar wiederholter Hauptrouten.
- Eigener Kontinuitäts-Zufallsstrom getrennt von Text- und Branch-RNG.
- Manuell gesetzte Seeds bleiben stateless und reproduzierbar; normale Zufallssprünge verwenden das Story-Gedächtnis.
- 14 neue `continuity_*.ini`-Satzbibliotheken mit je acht Varianten.
- Neue Unit-Tests für Persistenz, Callback-Handlungsfäden und dynamische Gewichte.
- Installer-Verifikation auf 232 Satzdateien aktualisiert; die bisherige v60.26-Prüfung auf 218 Dateien verursachte bei v60.27 einen falschen Installationsfehler.
- Installer-Verifikation prüft nun auch das Kontinuitätsmodul und alle 14 neuen Kontinuitäts-Satzdateien.
- WinRT-Stimmenabfrage wird beim Abbruch/Programmende sauber beendet, damit kein laufender `powershell.exe`-`QProcess` mehr beim GUI-Smoke-Test zerstört wird.
- Regressionstests für Satzdatei-Anzahl und WinRT-Prozess-Cleanup ergänzt.

## Frühere Änderungen

Die vollständige Historie bis einschließlich v60.26 ist im Git-Verlauf dieser Datei erhalten. Diese Arbeitsfassung ergänzt den v60.27-Abschnitt vor der bisherigen Historie.
