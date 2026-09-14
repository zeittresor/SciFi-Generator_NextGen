# SciFi-Generator v60.27 — Story Continuity

v60.27 erweitert die v60.26-Storyengine um ein leichtgewichtiges persistentes Missionsgedächtnis. Einzelne Sprünge bleiben weiterhin in sich abgeschlossen und enden garantiert sprungbereit, können aber offene Spuren erzeugen, die erst in späteren Sprüngen wieder relevant werden.

## Persistente Handlungsfäden

Unterstützte offene Fäden sind technische Signale, unbekannte Verfolger, Raumanomalien, frühere Fremdkontakte, Folgen von Rettungsmissionen und technische Nachwirkungen am eigenen Schiff. Ein Faden erhält einen Fälligkeitspunkt und kann nach einigen Sprüngen erneut in die laufende Geschichte eingeblendet werden.

Beim Wiederauftauchen kann die Crew die Spur aktiv untersuchen, vorsichtig beobachten oder bewusst vertagen. Daraus können Auflösung, Vertiefung, eine falsche Fährte, weitere Beobachtung oder ein bewusst offener Zustand entstehen. Vertiefte Fäden können erneut in späteren Sprüngen auftauchen.

## Persistenter Missionszustand

`story_state.json` speichert nur kompakte abstrakte Zustände und keine vollständigen alten Geschichten. Enthalten sind unter anderem:

- Sprungzähler und letzte Hauptrouten
- offene Story-Hooks
- Schiffszustand für Integrität, Navigation, Sensorik, Antrieb und Energie
- Reputation aus Rettungsmissionen
- unbekannte Aufmerksamkeit durch Fremdkontakte oder Verfolger
- eine begrenzte Missionshistorie

Dieser Zustand verschiebt zukünftige Wahrscheinlichkeiten moderat. Er soll Kontinuität erzeugen, ohne aus dem Storygenerator ein Ressourcen- oder Survival-Spiel zu machen.

## Zufall und reproduzierbare Tests

Textauswahl, normale Storyzweige und Kontinuität verwenden getrennte Zufallsströme. Ein manuell gesetzter Seed bleibt absichtlich stateless und verändert `story_state.json` nicht. Damit bleiben reproduzierbare Diagnose- und Regressionstests möglich. Normale zufällige Sprünge verwenden dagegen das Missionsgedächtnis und entwickeln die fortlaufende Geschichte weiter.

## Kompatibilität

Die 200 strukturellen Routen aus v60.26 bleiben erhalten. Kontinuitäts-Nebenhandlungen werden zur Laufzeit ergänzt. Das gemeinsame Ende mit `mission_free_space.ini`, `mission_end_status.ini`, `ship_liftoff_jumpready.ini` und `mission_jump_prompt.ini` bleibt unverändert.

## Installer-Hotfix

Die erste v60.27-Testfassung enthielt bereits 232 statt 218 Satzdateien, während der Installationsprüfer noch die v60.26-Anzahl erwartete. Das führte zu einem falschen Installationsfehler. Die Prüfung erwartet nun 232 Dateien und validiert zusätzlich alle 14 neuen Kontinuitätsbibliotheken.

Der GUI-Smoke-Test startete außerdem eine asynchrone WinRT-Stimmenabfrage über PowerShell und schloss das Testfenster teilweise vor deren Ende. `WinRtTtsService.cancel()` beendet nun auch diese laufende Abfrage sauber, damit beim Installations- oder Programmende kein lebender `QProcess` zurückbleibt.

## Teststatus

Der erste reale Windows-Installationslauf bestätigte Python 3.12.9, 232 Satzdateien, 200 strukturelle Routen, 9 Themes, 5 Prompt-Profile, erfolgreichen GUI-Import und erfolgreichen `MainWindow`-Smoke-Test. Der Lauf scheiterte ausschließlich an der veralteten 218-Dateien-Sollzahl; zusätzlich wurde die QProcess-Warnung der noch laufenden WinRT-Stimmenabfrage sichtbar. Beide Ursachen wurden danach korrigiert und durch v60.27-spezifische Regressionstests abgesichert. Ein erneuter Windows-Installationslauf ist die abschließende praktische Prüfung der Hotfixes.
