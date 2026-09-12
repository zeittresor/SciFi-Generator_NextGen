# SciFi-Generator v60.23 — Piper-Mehrsprecher-Auswahl

## MLS Deutsch

Das Piper-Modell `de_DE-mls-medium` enthält 236 Sprecher. Seine Modellkonfiguration stellt sie über `speaker_id_map` bereit. Die Schlüssel sind MLS-Dataset-IDs, keine sprechenden Personennamen.

Im Tab **Sprache & Audio** erscheint deshalb bei Auswahl von **MLS Deutsch** unter **Piper-Optionen** eine vertikal scrollbare Liste. Beispiel:

```text
Sprecher 001 — MLS-ID 2422
Sprecher 002 — MLS-ID 4536
Sprecher 003 — MLS-ID 2037
...
Sprecher 236 — MLS-ID ...
```

Die Liste ist absichtlich browse-orientiert und nicht als Suchfeld ausgeführt: Man muss keine der Dataset-IDs vorher kennen. Die aktive Auswahl wird in `settings.json` pro Piper-Paket gespeichert. Piper erhält beim Syntheseaufruf die zugehörige numerische `--speaker`-ID.

## Kleine Stilsets

Für kleine, semantisch benannte Sets wie Thorsten Emotional (acht Stile) bleibt eine ComboBox sinnvoll und wird deshalb weiterhin verwendet.
