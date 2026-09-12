# SciFi-Generator v60.24 — MLS-Merknamen und Konfigurationsprofile

## Fiktive Merknamen für MLS Deutsch

Das Piper-Modell `de_DE-mls-medium` besitzt 236 numerisch identifizierte Sprecher. Damit einzelne Stimmen leichter wiedergefunden werden können, enthält der SciFi-Generator ab v60.24 die Datei:

```text
data/mls_speaker_aliases.json
```

Sie ordnet jeder Piper-Speaker-ID einen stabilen, frei erfundenen Vornamen zu. Beispiel:

```text
Mirko — Sprecher 003 · MLS-ID 2037
```

Die Namen sind reine Merkhilfen. Sie stellen **keine Identifikation, kein Geschlecht und keinen echten Namen** der MLS-Dataset-Sprecher dar. Die Zuordnung soll in folgenden Programmversionen unverändert bleiben, damit ein einmal gemerkter Alias weiterhin dieselbe Piper-Speaker-ID bezeichnet.

Unter **Einstellungen → Sprachoptionen** kann die Anzeige mit **Fiktive Merknamen für MLS-Sprecher anzeigen** abgeschaltet werden. Dann zeigt die Liste wieder nur Sprecherposition und MLS-ID.

## Vollständige Konfigurationsprofile

Die Anwendung speichert die aktuelle Konfiguration weiterhin automatisch in `settings.json`. Ab v60.24 geschieht das zusätzlich verzögert nach Änderungen und atomar über eine temporäre Datei. Dadurch gehen Einstellungen bei einem späteren Absturz deutlich seltener verloren und eine teilweise geschriebene JSON-Datei wird vermieden.

Unter **Einstellungen → Konfigurationsprofile** stehen zwei neue Funktionen bereit:

- **Konfiguration speichern …** exportiert die vollständige aktuelle Einstellungskonfiguration als JSON-Profil.
- **Konfiguration laden …** wendet ein solches Profil sofort an und übernimmt es zugleich als aktuelle lokale Konfiguration.

Gespeichert werden unter anderem:

- Seed und Story-/Logging-Optionen
- Theme
- TTS-Backend und ausgewählte Stimme
- Piper-Sprecher bzw. Thorsten-Emotional-Stil
- Piper-Prosodie
- MLS-Merknamen ein/aus
- Sprach- und Hintergrundlautstärke sowie Geschwindigkeit
- Storyboard-/Gesamtpaket-Modus
- Videoauflösung, Bildrate und Übergänge
- gewünschter Stimmcharakter, Stimmwirkung und TTS-Qualität
- Inhalt des Ergebnis-ZIP
- Ziel-LLM und Ollama-Einstellungen

Ein Profil enthält nur Einstellungen, nicht die großen installierten TTS-Modelle selbst. Wird auf einem anderen Rechner eine im Profil ausgewählte Stimme noch nicht gefunden, bleibt die gewünschte Voice-ID für eine spätere Wiederherstellung vorgemerkt. Nach Installation bzw. Erkennung der Stimme kann sie wieder automatisch gewählt werden.

## Bugfix-Lauf v60.24

Beim zusätzlichen Regressionslauf wurde ein bereits vorhandener Einstellungsfehler gefunden: Der frei wählbare Story-Seed wurde bisher zwar in der Oberfläche gesetzt, aber nicht in `settings.json` gespeichert. Das ist ab v60.24 korrigiert.

Außerdem wurde die Wiederherstellung asynchron geladener Windows-Stimmen verbessert. OneCore-/SAPI-Stimmen werden erst nach dem Start eingelesen. Früher konnte die Oberfläche vorübergehend auf eine andere Stimme fallen und diese Auswahl beibehalten. Die gewünschte gespeicherte Voice-ID bleibt nun vorgemerkt, bis die Stimme tatsächlich verfügbar ist oder der Benutzer bewusst eine andere auswählt.


## Hinweis ab v60.26

Die fiktiven MLS-Merknamen sind bei neuen Konfigurationen standardmäßig ausgeschaltet. Bereits gespeicherte Profile behalten ihren expliziten Wert `mls_speaker_aliases`.
