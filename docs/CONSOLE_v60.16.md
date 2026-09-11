# SciFi-Generator v60.16 — Console / CLI

Die Konsolenversion benutzt nur die Python-Standardbibliothek und `story_engine.py`. Sie ist fuer automatisierte Tests, Linux-Systeme, SSH-Sitzungen und die Fehlersuche in Satzteil-Kombinationen gedacht.

## Schnellstart

Windows:

```text
start_console.bat --seed 57
start_console.bat --seed 57 --trace
```

Linux / macOS:

```text
./run_console.sh --seed 57
./run_console.sh --seed 57 --trace
```

Direkt:

```text
python3 scifi_console.py [Optionen]
```

## Wichtige Optionen

- `--seed N`: reproduzierbarer Seed.
- `--count N`: mehrere Geschichten; zusammen mit `--seed` werden fortlaufende Seeds verwendet.
- `--trace`: Storyroute und jede Fragmentauswahl mit Datei und Zeilennummer ausgeben.
- `--json`: maschinenlesbare Ausgabe; mit `--trace` inklusive aller Auswahlmetadaten.
- `--raw`: Originalschreibweise der Satzteile statt der historischen Display/TTS-Umlautumsetzung.
- `--no-legacy-umlauts`: historische ae/ue/oe-Anzeigeumsetzung deaktivieren.
- `--output DATEI`: Ausgabe in eine UTF-8-Datei schreiben.
- `--list-routes`: alle strukturell erreichbaren Branch-Routen auflisten.
- `--validate`: Quelldateien und gemeinsames Sprungbereitschafts-Ende pruefen.

## Trace-Beispiel

```text
--- TRACE: STORY ROUTE ---
B01 | mission_route | distress_signal | Unbekannter Notruf oder Rettungssignal | weight=15
B02 | distress_source | damaged_vessel | Havariertes Schiff | weight=36
B03 | post_mission_twist | delayed_signal | Verspaetetes Signal vom Einsatzgebiet | weight=20

--- TRACE: FRAGMENTS IN OUTPUT ORDER ---
001 | data/vars/sternzeit_name.ini:4 | Sternzeit | ...
002 | data/vars/sternzeit_digits.ini:1 | Sternzeit-Ziffer | ...
...
```

So kann eine sprachlich unpassende Stelle bis auf die konkrete INI-Datei und Quellzeile zurueckverfolgt werden.

## Massentest

```text
python3 tools/audit_stories.py --count 10000 --require-all-routes
```

Der Audit prueft fehlende Quellen, das gemeinsame Storyende, grobe Satzzeichen-/Abstandsartefakte, versehentliche Wortdopplungen, wiederholte Standardklauseln und Routendeckung.
