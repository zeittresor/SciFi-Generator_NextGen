# Piper-Erzählfluss und Tonhöhe — v60.28

## Ausgangsproblem

Die Piper-CLI behandelt jede über `stdin` übergebene Textzeile als eigene Äußerung. Der SciFi-Generator übergibt die Story traditionell mit den Zeilenumbrüchen der einzelnen Satz-/Storybausteine. Dadurch startet Piper Prosodie, Grundtonlage und Rhythmus an vielen Abschnittsgrenzen neu.

Das Verhalten kann lebendig und teilweise unterhaltsam wirken, bei längeren Erzählungen aber auch durch hörbare Wechsel von Tonlage und Tempo stören. Das vom Nutzer bereitgestellte Audiobeispiel zeigte messbare Sprünge der mittleren Grundfrequenz zwischen mehreren Storyblöcken.

## Neue Einstellungen

Unter **Sprache & Audio → Piper-Optionen** stehen ab v60.28 zwei zusätzliche Einstellungen bereit:

### Syntheseart

- **Abschnittsweise — lebendiger / wechselnder**
  - entspricht dem bisherigen Verhalten;
  - Story-Zeilengrenzen bleiben erhalten;
  - Piper setzt die Prosodie je Storyblock neu an.

- **Gesamtstory in einem Fluss — gleichmäßiger**
  - interne Zeilenumbrüche werden nur für die Synthese zu Leerzeichen umgewandelt;
  - der sichtbare Storytext wird nicht verändert;
  - Piper erhält die Story als eine zusammenhängende Eingabe.

### Tonhöhe

- Bereich: **−6 bis +6 Halbtöne**;
- `0` entspricht der Originaltonhöhe des Modells;
- die vorhandene Sprechgeschwindigkeit bleibt eine separate Einstellung;
- die Tonhöhe wird nach der Piper-Synthese mit FFmpeg verändert;
- `asetrate` verschiebt die Tonhöhe, `atempo` gleicht die dabei entstehende Daueränderung wieder aus.

Ist FFmpeg weder unter `tools/ffmpeg.exe` noch im `PATH` verfügbar, bleibt die Tonhöhenregelung deaktiviert. Die normale Piper-Synthese funktioniert weiterhin.

## Geltungsbereich

Die Einstellungen gelten sowohl für:

- direktes Vorlesen innerhalb der Anwendung;
- WAV-Export;
- MP3-Export.

Sie werden in `settings.json` und in exportierten Konfigurationsprofilen gespeichert:

- `piper_synthesis_mode`
- `piper_pitch_semitones`

## Kompatibilität

Der Standard bleibt absichtlich **abschnittsweise mit Originaltonhöhe**, damit bestehende Nutzerkonfigurationen und der bisherige Klang unverändert bleiben, bis der neue Modus bewusst gewählt wird.
