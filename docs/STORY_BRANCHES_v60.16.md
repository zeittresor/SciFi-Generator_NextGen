# SciFi-Generator v60.16 — verzweigte Story-Struktur

Jede Geschichte beginnt mit der Ankunft in einem neuen Sternensystem. Der Mittelteil wird aus gewichteten und verschachtelten Branches erzeugt. Unabhaengig von der Route endet jede Geschichte wieder in freiem Raum, in stabilem Zustand und mit vorbereitetem naechsten Sektorsprung.

## Hauptfamilien

1. Planetare Begegnung mit intelligenter Fremdlebensform
2. Planet ohne intelligente Aliens: Naturgewalten, destruktive Flora oder Fauna
3. Kein besuchbarer Planet: Truemmerfeld, Raumstation, Sperrgebiet oder Weltraumphaenomen
4. Verlassener Ort: Oberflaechenanlage oder orbitale Struktur
5. Unbekannter Notruf/Rettungssignal: havariertes Schiff, Rettungskapsel oder Notfallboje
6. Technischer Zwischenfall am eigenen Schiff: Navigation, Antrieb oder Energieversorgung

Mehrere Familien besitzen zusaetzliche Wendepunkte. Nach dem eigentlichen Missionsereignis kann ausserdem ein spaeter `post_mission_twist` auftreten. Die aktuelle Sequenz besitzt 200 strukturell erreichbare Route-Kombinationen.

## Gemeinsames Ende

Jeder strukturelle Pfad endet zwingend mit:

```text
mission_free_space.ini
mission_end_status.ini
ship_liftoff_jumpready.ini
mission_jump_prompt.ini
```

`StoryEngine.validate_terminal_invariant()` prueft diese Eigenschaft ohne Zufallsgenerierung ueber saemtliche strukturellen Pfade.

## Satzteilbibliothek

- 218 INI-Dateien
- 4.306 nicht leere, pro Datei eindeutige Auswahlzeilen
- 59 neue v60.16-Branch-Dateien mit je 7 Grundvarianten = 413 Zeilen
- anschliessend 7 weitere Varianten fuer jede der 218 Dateien = 1.526 dokumentierte Erweiterungen vor sprachlichen Reparaturen

Maschinenlesbare Nachweise:

- `data/branch_fragments_v60.16.json`
- `data/fragment_expansion_v60.16.json`
- `data/fragment_repairs_v60.16.json`

## Reproduzierbarkeit

Branch-Auswahl und Fragment-Auswahl verwenden getrennte, aus demselben Seed abgeleitete Zufallsstroeme. Das Erweitern einer INI-Datei soll dadurch nicht automatisch die uebergeordnete Storyroute eines Seeds veraendern.

## Sprachliche Reparaturen

`data/fragment_repairs_v60.16.json` dokumentiert 298 historische Satzteilzeilen, die waehrend der Kombinationspruefung bewusst ersetzt oder entfernt wurden. Dazu gehoert auch eine vereinheitlichte Grammatik fuer Temperaturbereiche, damit jede zulaessige Kombination aus Beschreibung, Zahlenwerten und Verbindungsfragment syntaktisch zusammenpasst.
