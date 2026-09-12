# MLS-Sprecher-Aliase in v60.26

Die fiktiven Merknamen für das Piper-Modell **MLS Deutsch** bleiben als optionale Bedienhilfe erhalten, sind bei einer frischen Konfiguration ab v60.26 jedoch standardmäßig ausgeschaltet.

Grund: Ein frei erfundener Vorname kann beim Anhören eine Geschlechtszuordnung suggerieren, obwohl der Alias nicht die Identität des Dataset-Sprechers bezeichnet. Ohne Alias zeigt die Liste nur die robuste technische Zuordnung `Sprecher NNN — MLS-ID …`.

Die Einstellung wird weiterhin in `settings.json` und in exportierten Konfigurationsprofilen gespeichert. Wer die Merknamen bewusst aktiviert hat, behält diese Auswahl beim Laden seiner Konfiguration.

Die öffentliche MLS-Metadatei dokumentiert für die deutschen Sprecher zwar ein F/M-Feld. Die Piper-Modellkonfiguration selbst enthält dagegen nur die 236 Speaker-IDs. v60.26 verwendet die fiktiven Namen daher weiterhin **nicht** als Geschlechtsinformation.
