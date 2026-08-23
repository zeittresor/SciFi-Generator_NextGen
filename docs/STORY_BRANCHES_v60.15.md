# Story-Zweige in SciFi-Generator v60.15

## Grundprinzip

Jede Geschichte besitzt weiterhin denselben Rahmen:

1. Das Schiff beendet einen Sektor-Sprung und erreicht ein neues Sternensystem.
2. Sternzeit, Systemname, Sonnen, Planeten und erste Besonderheiten werden zufällig beschrieben.
3. Danach wählt die Engine einen gewichteten Hauptzweig.
4. Innerhalb einzelner Hauptzweige folgen weitere Unterzweige.
5. Der konkrete Zwischenablauf wird ausschließlich aus den jeweils zu diesem Zweig gehörenden Satzteil-Dateien zusammengesetzt.
6. Am Ende befindet sich das Schiff wieder in einer stabilen Lage, dokumentiert die Ereignisse und gibt den nächsten Sektor-Sprung frei.

Damit bleibt der Wiedererkennungswert der ursprünglichen Anwendung erhalten, während das interessante Mittelstück von Sprung zu Sprung strukturell völlig anders sein kann.

## Aktuelle Hauptzweige

Die vier Hauptzweige besitzen standardmäßig jeweils Gewicht `25`.

### 1. Planetare Begegnung mit intelligenter Fremdlebensform

Der klassische ursprüngliche Ablauf bleibt als vollständiger Zweig erhalten:

`Systemankunft → Zielplanet → Oberflächenscan → Landung → Alien-Sichtung → Anatomie → Verhalten/Kontakt → Rückzug → Orbit → nächster Sprung`

Die bisherigen Alien-, Planeten- und Reaktionsdateien bleiben dafür verwendbar.

### 2. Planet ohne intelligente Aliens

Nach Zielplanet, Oberflächenscan und Landung wählt die Engine einen Unterzweig:

- `natural_forces` — Naturgewalten ohne Lebensformkontakt, Gewicht 34
- `destructive_flora` — nicht intelligente, aber destruktive Flora, Gewicht 33
- `destructive_fauna` — nicht intelligente oder territoriale Fauna, Gewicht 33

Dieser Zweig verwendet keine `life_alien_*`-Anatomiedateien. Flora und Fauna werden ausdrücklich als nicht intelligente lokale Lebensformen behandelt.

### 3. Kein besuchbarer Planet

Ein planetarer Landeversuch entfällt vollständig. Das Schiff untersucht stattdessen ein Ereignis im freien Systemraum:

- `debris_field` — Trümmer- und Wrackfeld
- `unknown_station` — unbekannte aktive oder teilaktive Raumstation
- `restricted_zone` — gesperrter, automatisch verteidigter Raumsektor
- `space_phenomenon` — physikalisches Weltraumphänomen

Alle vier Unterzweige besitzen Gewicht `25`. In diesen Routen werden weder Planetenlandung noch Alien-Anatomie oder planetarer Rückstart verwendet.

### 4. Verlassener Ort ohne aktive Bewohner

Die Engine wählt mit gleicher Gewichtung:

- `surface_ruins` — verlassene Oberflächenanlage, Siedlung, alter Raumhafen oder Ruinenkomplex
- `orbital_ruins` — verlassenes Schiff, Raumstation, Ring oder orbitaler Industriekomplex

Die Orte dürfen Spuren früherer Bewohner, alte Logs, demontierte Technik und ungeklärte Restfunktionen enthalten, aber keine aktive Bewohnerbegegnung erzwingen.

## Sequenzformat v2

`sequence_legacy.json` unterstützt ab v60.15 zusätzlich zwei strukturierende Schritttypen.

### `scene`

Ein `scene`-Schritt erzeugt selbst keinen gesprochenen Text. Er setzt Titel und visuellen Hinweis für die nachfolgenden Satzteile. Dadurch kann das Storyboard die tatsächliche Route verwenden, statt feste Alien-Szenen vorauszusetzen.

Beispiel:

```json
{
  "kind": "scene",
  "id": "discovery",
  "title": "Destruktive Flora entdeckt",
  "visual_hint": "Nicht intelligente fremde Vegetation rund um den Landeplatz."
}
```

### `branch`

Ein `branch`-Schritt wählt genau eine `choice`. Choices können wiederum weitere `branch`-Schritte enthalten.

```json
{
  "kind": "branch",
  "id": "planetary_hazard",
  "label": "Planetarer Ereignistyp",
  "choices": [
    {"id": "natural_forces", "weight": 34, "steps": []},
    {"id": "destructive_flora", "weight": 33, "steps": []},
    {"id": "destructive_fauna", "weight": 33, "steps": []}
  ]
}
```

Die Gewichte müssen nicht zusammen 100 ergeben; sie werden relativ zueinander ausgewertet.

## Reproduzierbarkeit

Satzteilauswahl und Branch-Auswahl verwenden zwei getrennte, aus demselben Story-Seed abgeleitete Zufallsströme. Das ist absichtlich so gebaut: Wird später beispielsweise `flora_attack.ini` um weitere Zeilen ergänzt, soll dadurch nicht plötzlich derselbe Seed in einen vollkommen anderen Hauptzweig springen.

Der Generierungslog enthält deshalb zusätzlich den vollständigen Story-Pfad, beispielsweise:

```text
Story-Zweig: Planet ohne intelligente Aliens — Natur, Flora oder Fauna > Destruktive nicht intelligente Flora
```

## Satzteilbibliothek

v60.15 ergänzt 72 neue `.ini`-Dateien. Jede neue Datei enthält genau sieben Alternativen, zusammen 504 neue Satzteile.

Gesamtumfang nach v60.15:

- 159 `.ini`-Dateien
- 2.367 nicht leere auswählbare Satzteile
- 10 aktuell konkret erreichbare Story-Pfade

Die neuen Satzteile sind vollständig in `data/branch_fragments_v60.15.json` dokumentiert.

## Erweiterung um weitere Story-Zweige

Neue Routen sollten weiterhin dem Rahmen folgen:

`Systemankunft → Entdeckung/Entscheidung → Ereignis/Erkundung → Eskalation oder Erkenntnis → sicherer Abschluss → nächster Sektor-Sprung`

Dabei sollte jeder neue erzählte Teilabschnitt wieder aus einer eigenen Satzteil-Datei bestehen. `scene`-Marker sorgen parallel dafür, dass Storyboard, Bildserie und Gesamtpaket dieselbe narrative Abzweigung verstehen.
