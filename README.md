# SciFi-Generator

**Aktuelle Version: 60.14**

Der **SciFi-Generator** ist eine lokale Windows-Desktopanwendung, die zufällige Science-Fiction-Missionsberichte aus frei bearbeitbaren Textbausteinen zusammensetzt und anschließend mit einer installierten Text-to-Speech-Stimme vorliest.

Der Ablauf orientiert sich an der ursprünglichen Anwendung:

1. **Sektor-Sprung berechnen** erzeugt eine neue Geschichte.
2. **Sprung durchführen** liest die bereits berechnete Geschichte vor.

Die Story, das detaillierte Auswahlprotokoll und optionale Bild-Prompts bleiben standardmäßig ausgeblendet und werden nur bei Bedarf über **Story / Log / Prompts einblenden** geöffnet.

Interface (Standardausgabe benötigt keinerlei KI):

<img width="423" height="673" alt="interface" src="https://github.com/user-attachments/assets/bb153fc1-dbab-4449-8449-5427a413f786" />


Story Beispielausgaben (nachdem man ein Gesamt-Paket an eine LLM geschickt hat - in diesem Fall nur Bildausgaben):

<img width="1672" height="941" alt="alien1" src="https://github.com/user-attachments/assets/27ae8bcb-5de7-45af-8e02-48f7cc98eba6" />

<img width="1672" height="941" alt="story1" src="https://github.com/user-attachments/assets/355c055d-2db4-4af0-b340-b4707ecd789d" />

## Funktionen

- Zufällige Science-Fiction-Geschichten aus externen Satzteil-Dateien
- 87 vorhandene Satzteil-Dateien mit insgesamt 1.863 auswählbaren Zeilen; in v60.14 wurde jede Datei um sieben passende Varianten erweitert
- Windows-Sprachausgabe über OneCore/WinRT, SAPI und Qt TextToSpeech
- Auswahl der Stimme sowie Regelung von Geschwindigkeit und Lautstärke
- Pause, Fortsetzen und Stoppen der Sprachausgabe
- Schutz vor versehentlicher Wiederholung: Ein berechneter Sprung kann nur einmal vollständig durchgeführt werden
- Leicht irritierte TTS-Hinweise, wenn noch kein Sprung berechnet wurde oder die vorhandene Story bereits erzählt ist
- Audioexport als WAV einschließlich der aktuell eingestellten Stimme und Brückenatmosphäre
- Optionaler MP3-Export, wenn FFmpeg verfügbar ist
- Optionale, in einer Schleife abgespielte Brückenatmosphäre mit eigener Lautstärke
- Kompakte Oberfläche mit ausblendbarer Story- und Protokollansicht
- Aufgeräumter Hauptworkflow mit Gesamtpaket-Ausgabe direkt im Fokus
- Breiteres Standardfenster ohne horizontale Scrollleiste im normalen Startlayout
- Formularfelder mit Beschriftungen oberhalb beziehungsweise in klaren Spalten statt abgeschnittener Langtexte
- Primäre Produktionsaktion optisch hervorgehoben; Übergabe- und optionale Aktionen visuell nachgeordnet
- Standardmäßig geschlossene, einklappbare Bereiche für optionale Audio-, Video-, Ollama-, Generierungs- und Theme-Einstellungen
- Kurze, umbruchfähige Zusammenfassungen unter den einklappbaren Bereichsüberschriften, damit aktive Werte lesbar bleiben
- Scrollbarer Bedienbereich mit vertikaler und bei Bedarf horizontaler Scrollleiste
- Automatische, responsive UI-Skalierung für Schrift, Schaltflächen, Eingabefelder, Abstände und Scrollleisten
- Reproduzierbare Geschichten durch einen frei wählbaren Seed
- Ausführliche Generierungsprotokolle mit App-Version, Quelldatei, Zeilennummer und ausgewähltem Text
- Externe JSON-Themes mit automatischer Kontrastprüfung
- Frei bearbeitbare Generierungsreihenfolge in `sequence_legacy.json`
- Projektlokale Python-Umgebung und optionales Wheelhouse für Offline-Installationen
- Optionales Storyboard mit 6 bis 10 Schlüsselszenen und direkt nutzbaren Bild-Prompts
- Wahlweise lokale Prompt-Erzeugung oder Verfeinerung über einen laufenden Ollama-Server
- Verbindliche `style_reference.png` für hochwertige cinematische CGI-/3D-Filmstills im Gesamtpaket
- Frei wählbarer Lieferumfang des finalen Ergebnis-ZIP: nur Video oder zusätzlich Bilder, Audio, Clips und Projektdateien
- Wählbare Bildrate mit 8 fps als Standard für weitgehend statische Bildgeschichten
- Ziel-KI-Profile für ChatGPT, Grok, Gemini, Stable Diffusion und frei benennbare andere Systeme
- Ausführbarer Steuerprompt am Anfang der Ausgabe, damit eine neue KI-Sitzung tatsächlich die Bildserie erzeugt statt den Text nur zu analysieren
- Globale Serienbibel für wiederkehrendes Schiff, Welt, Alien, Stil und Seitenverhältnis
- Wahlweise **Bildserie** oder **Gesamtpaket** mit Bildern, Szenen-TTS, zeitlich angepassten Filmabschnitten, sanften Übergängen, Video- und ZIP-Anforderung
- Exakte, nicht gekürzte Narrationstexte pro Szene für eine saubere abschnittsweise Vertonung
- Offline-Fallback-Anweisung für Python/FFmpeg, falls das Zielsystem Audio, Video oder ZIP nicht direkt erzeugen kann

## Schnellstart unter Windows

1. Python 3.10 oder neuer installieren und bei der Installation **Add Python to PATH** aktivieren.
2. Das Release-Archiv vollständig in einen beschreibbaren Ordner entpacken.
3. `install_windows.bat` starten.
4. Nach erfolgreicher Installation die Anwendung automatisch starten lassen oder später `start_app.bat` ausführen.

Der Installer erzeugt eine lokale `.venv`, installiert die benötigten Pakete und prüft anschließend die Programmdateien. Eine bereits vorhandene virtuelle Umgebung wird wiederverwendet.

## Bedienung

Die Oberfläche stellt den üblichen Arbeitsweg zuerst dar:

1. **Sektor-Sprung berechnen**
2. **Gesamtpaket-Auftrag erzeugen**
3. **Gesamtpaket-Übergabe-ZIP speichern** und in den gewünschten neuen KI-Chat hochladen

Selten benötigte Einstellungen sind standardmäßig eingeklappt. Dazu gehören Video- und Stimmendetails, Ollama-Verfeinerung, lokale Wiedergabe- und Audiooptionen, Generierungsdetails und weitere Einstellungen. Ein Klick auf die jeweilige Überschrift öffnet oder schließt den Bereich. Unter **Ansicht** lassen sich außerdem alle optionalen Bereiche gemeinsam ein- oder ausklappen. Die Überschrift zeigt auch im geschlossenen Zustand eine Kurzfassung der aktiven Werte, beispielsweise Auflösung, Stimmwirkung, Ollama-Modus, verwendete Stimme oder Theme. Der Aufklappzustand wird gespeichert.

Für die normale Story-Wiedergabe gilt weiterhin:

1. Unter **Stimme** eine verfügbare TTS-Stimme auswählen, sofern nicht die voreingestellte Stimme verwendet werden soll.
2. Geschwindigkeit sowie Sprach- und Hintergrundlautstärke einstellen.
3. **Sektor-Sprung berechnen** anklicken.
4. **Sprung durchführen** anklicken, um die Story vorzulesen.
5. Über **Story als Audiodatei speichern …** kann dieselbe Erzählung mit den aktuellen Lautstärkeeinstellungen exportiert werden.
6. Im Bereich **Medienausgabe / Übergabe** unter **Gewünschtes Ergebnis** zwischen **Gesamtpaket — fertiges Video mit TTS, Hintergrundsound und ZIP** und **Nur Bildserie — keine Audio- oder Videodatei** wählen. Das Gesamtpaket ist nun die Standardauswahl.
7. Das gewünschte **Zielsystem / LLM** auswählen: ChatGPT, Grok, Gemini, Stable Diffusion oder Andere.
8. Bei einem Gesamtpaket die gewünschte Videoauflösung wählen und optional die Dauer der sanften Überblendung einstellen. Die aktuell ausgewählte TTS-Stimme, Sprechgeschwindigkeit, Sprachlautstärke und Brückenatmosphäre werden in den Produktionsauftrag übernommen.
9. Über **Nur Bildserien-Prompt erzeugen** beziehungsweise **Gesamtpaket-Auftrag erzeugen** wird das entsprechende Anweisungsdokument erstellt.
10. Über **Story / Log / Prompts einblenden** kann die Story, das Auswahlprotokoll und der vollständige Produktionsauftrag angezeigt werden.

Ein berechneter Sektor-Sprung wird nach einer vollständig abgeschlossenen Wiedergabe als durchgeführt markiert. Ein weiterer Klick auf **Sprung durchführen** startet daher nicht dieselbe Story erneut, sondern lässt die ausgewählte Stimme leicht irritiert darauf hinweisen, dass zuerst ein neuer Sprung berechnet werden muss. Wird die Wiedergabe manuell gestoppt oder schlägt sie fehl, darf der aktuelle Sprung erneut gestartet werden.

Der Bedienbereich wird nicht auf eine zu geringe Fensterhöhe zusammengestaucht. Reicht der verfügbare Platz nicht aus, erscheinen automatisch vertikale beziehungsweise horizontale Scrollleisten. Das gilt insbesondere für kleinere Displays, hohe Windows-Skalierungswerte und umfangreiche Stimmennamen.

Wird das Fenster vergrößert, skaliert die Oberfläche automatisch mit: Schrift, Schaltflächen, Eingabefelder, Regler, Abstände, Kontrollkästchen und Scrollleisten werden bis zu einer sinnvollen Obergrenze gemeinsam vergrößert. Beim Verkleinern bleiben die Elemente lesbar und werden nicht unter ihre normale Größe geschrumpft; stattdessen übernimmt der Scrollbereich.


## Storyboard / Bild-Prompts

Zusätzlich zur erzählten Story kann der SciFi-Generator auf Wunsch ein kleines Storyboard mit **6 bis 10 Schlüsselszenen** erzeugen. Diese Texte werden **nicht vorgelesen**, sondern nur im optionalen Prompt-Tab angezeigt oder bei Bedarf gespeichert.

Die **Prompt-Verfeinerung** kann auf zwei Arten erfolgen:

- **Lokal (regelbasiert):** Die App zerlegt die generierte Story anhand der bekannten Missionsabschnitte in Schlüsselszenen und erstellt dafür direkt nutzbare Bild-Prompts.
- **Ollama (lokales Modell):** Wenn auf dem System ein Ollama-Server läuft, kann ein lokales Modell die vorbereiteten Szenen zusätzlich sprachlich und zielsystemspezifisch verfeinern. Fällt Ollama aus oder ist kein Modell verfügbar, bleibt die lokale Prompt-Erzeugung weiterhin nutzbar.

Unabhängig davon wird eine **Ziel-KI** gewählt:

- **ChatGPT:** konversationeller Arbeitsauftrag, der ausdrücklich separate Bilder pro Szene verlangt und frühere Bilder als Referenz weiterverwenden lässt.
- **Grok:** Bildserien-Auftrag mit getrennten Szenen und Hinweisen für Batch-/Referenzfunktionen, soweit diese verfügbar sind.
- **Gemini:** konversationeller Serienauftrag mit fortlaufender visueller Kontinuität innerhalb derselben Bildsitzung.
- **Stable Diffusion:** Workflow-Steuerblock, einzelne Positive Prompts und ein globaler Negative Prompt. Jede Szene wird separat an das Diffusionsmodell übergeben.
- **Andere:** allgemeines Profil mit frei eintragbarem Namen der Zielanwendung.

Am Anfang der Ausgabe steht nun ein ausdrücklicher **Arbeitsauftrag zur Erzeugung der Bildserie**. Darauf folgt eine globale visuelle Serienbibel für Schiff, Sternensystem, Planetenoberfläche, Alien, Bildstil und Ausschlüsse. Erst danach folgen die nummerierten Szenenprompts. Dadurch wird beim Einfügen in einen neuen Chat klar, dass Bilder erzeugt werden sollen und nicht lediglich eine Analyse des Storyboards erwartet wird.

Die Ziel-KI-Profile liegen als extern bearbeitbare JSON-Dateien im Ordner:

```text
prompt_profiles/
```

Über **Ansicht → Prompt-Profile neu laden** können Änderungen ohne Programmanpassung übernommen werden. **Hilfe → Prompt-Profilprüfung** zeigt geladene und abgelehnte Dateien.

Die erzeugten Bild-Prompts eignen sich als Vorlage für externe Bildgeneratoren oder für eine spätere Bildserien-/Slideshow-Funktion. Über **Bild-Prompts speichern …** können sie als TXT, Markdown oder JSON exportiert werden. Der JSON-Export enthält zusätzlich Ziel-KI, Profilmodus, Seitenverhältnis, globalen Negative Prompt und das vollständige Anweisungsdokument.

## Gesamtpaket-Prompt: Bilder, Audio und Video

Neben einer reinen Bildserie kann die App einen vollständigen **Gesamtpaket-Produktionsauftrag** erzeugen. Dieser ist dafür gedacht, in eine neue Sitzung eines geeigneten LLMs oder in einen automatisierten Medienworkflow übernommen zu werden.

Das Gesamtpaket ist ab v60.10 die Standardauswahl. Die Oberfläche bezeichnet den anderen Modus nun ausdrücklich als **Nur Bildserie — keine Audio- oder Videodatei**, damit nicht versehentlich ein reiner Bildauftrag an einen neuen Chat übergeben wird.

Ab v60.13 orientiert sich das Übergabe-ZIP an der verbesserten Handoff-Struktur: `00_START_HERE.txt`, `README_HANDOFF.txt`, Produktionsprompt, Manifest, Story, Lieferprüfung, die verbindliche `style_reference.png` und ein vollständiger `offline_fallback/`-Bereich. Die echten Dateien `build_story_video.py`, `build_video.bat`, `audio_mixer.py` und die TTS-Helfer liegen zusätzlich weiterhin im Wurzelverzeichnis, damit ein neues LLM sie nicht fälschlich als fehlend interpretiert. Fehlende Bilder, Audios und Videos sind die zu erzeugenden Ausgaben und keine Paketfehler. Eine reine Archivinspektion oder Bild-ZIP erfüllt den Auftrag nicht.

### Empfohlenes Übergabe-ZIP

Bei einem Gesamtpaket sollte nicht nur die sichtbare Prompt-TXT gespeichert werden. Der Button **Gesamtpaket-Übergabe-ZIP speichern …** erzeugt stattdessen ein vor dem Speichern vollständig validiertes Übergabearchiv mit:

- `00_START_HERE.txt` und `00_EXECUTE_THIS_TASK.txt` mit eindeutigem Produktionsauftrag
- `README_HANDOFF.txt`, `TASK.json` und `manifest.json`
- `prompts/scifi_media_package_prompt.txt` und `story/full_story.txt`
- `style_reference.png` als visueller Qualitäts- und Stilanker
- `verification/DELIVERY_CHECKLIST.txt` und `verification/validate_handoff.py`
- der tatsächlich aktivierten `assets/background.wav`
- echten Build-, Audio- und TTS-Dateien im Wurzelverzeichnis und zusätzlich unter `offline_fallback/`

Dieses ZIP sollte vollständig in den neuen Chat hochgeladen werden. Dadurch steht die Hintergrunddatei tatsächlich zur Verfügung und wird nicht nur namentlich in einem Text erwähnt.

Die Promptausgabe enthält außerdem ein verbindliches **Completion Gate**: Eine ZIP-Datei, die ausschließlich `scene_01.png` bis `scene_XX.png` enthält, gilt ausdrücklich als unvollständig. Als Erfolg zählt nur ein abspielbares Video mit hörbarer Sprachausgabe und – sofern aktiviert – eingemischter Brückenatmosphäre oder ein vollständig ausführbares Offline-Fallback-Paket.

Der Auftrag verlangt ausdrücklich:

- ein separates, visuell konsistentes Bild pro Schlüsselszene
- einen frei wählbaren Stimmcharakter: menschlich/natürlich, neutral oder robotisch/synthetisch
- eine gewünschte stimmliche Wirkung: weiblich, männlich, neutral/androgyn oder egal
- ein TTS-Qualitätsziel von schnell/standard bis zur bestmöglichen verfügbaren Qualität
- eine frei wählbare Videoauflösung und ein daraus automatisch abgeleitetes Seitenverhältnis
- eine eigene Audiodatei pro Szene mit dem **exakten Narrationstext** dieses Abschnitts
- dieselbe Stimme in allen Szenen
- eine sichtbare Szenendauer, die sich an der tatsächlichen Audiodauer orientiert
- sanfte Crossfades zwischen den Szenen
- optionale Brückenatmosphäre mit der in der App eingestellten Lautstärke
- ein chronologisch zusammengesetztes MP4-Video in der gewählten Zielauflösung und Bildrate; Standard sind 8 fps für weitgehend statische Bildgeschichten
- ein Ergebnis-ZIP mit frei wählbarem Lieferumfang: nur das fertige Video oder zusätzlich Szenenbilder, Szenenaudios inklusive `final_mix.wav`, Einzelclips und/oder Projektdateien

Die Vorgaben der aktuell ausgewählten TTS-Stimme, des Backends, der Sprechgeschwindigkeit sowie der Sprach- und Hintergrundlautstärke werden automatisch in das Dokument eingetragen. Zusätzlich lassen sich für das Gesamtpaket **Stimmcharakter**, **stimmliche Wirkung** und **TTS-Qualität** getrennt festlegen. Standardmäßig fordert die App eine möglichst natürliche weiblich wirkende Stimme in bestmöglicher Qualität an.

### Lieferumfang des finalen Ergebnis-ZIP

Im einklappbaren Bereich **Lieferumfang des Ergebnis-ZIP** wird festgelegt, welche Dateien das Zielsystem nach Abschluss zurückgeben soll. Das fertige `scifi_story.mp4` ist immer enthalten. Optional können hinzugefügt werden:

- Szenenbilder unter `images/`
- Szenenaudios und `audio/final_mix.wav`
- Einzelclips unter `clips/`
- Story, Prompts, Manifest, Produktionslog und Build-Dateien

Wer nur das fertige Video benötigt, deaktiviert alle optionalen Einträge. Diese Auswahl betrifft ausschließlich das finale Ergebnis-ZIP. Die Szenenbilder und Audiodateien müssen für die eigentliche Videoproduktion trotzdem erzeugt werden und dürfen erst beim Packen des Ergebnis-ZIP weggelassen werden.

### Videoauflösungen und Seitenverhältnisse

Als Standard ist **1024 × 1024 Pixel im Format 1:1** eingestellt. Das eignet sich für kompakte, quadratische Ausgaben und reduziert gegenüber Full HD oder 4K den Rechen- und Speicherbedarf. Zusätzlich stehen folgende Profile zur Verfügung:

- 512 × 512 — 1:1, kompakt
- 1024 × 1024 — 1:1, Standard
- 1280 × 720 — HD, 16:9
- 1280 × 768 — WXGA, 5:3
- 1920 × 1080 — Full HD, 16:9
- 2560 × 1440 — QHD, 16:9
- 3840 × 2160 — 4K UHD, 16:9
- benutzerdefinierte Breite und Höhe von 256 bis 8192 Pixel

Das Seitenverhältnis wird automatisch aus Breite und Höhe berechnet und in den Gesamtpaket-Prompt sowie `manifest.json` übernommen. Der Produktionsauftrag verbietet proportionale Verzerrungen. Abweichende Quellbilder sollen kontrolliert zugeschnitten oder mit Letterbox beziehungsweise Pillarbox angepasst werden.

Die Bildrate ist separat wählbar. **8 fps** sind der Standard, weil die erzeugten Videos überwiegend aus statischen Bildern mit sanften Überblendungen bestehen. Zusätzlich stehen 12, 24, 30 und 60 fps zur Verfügung.

Die eingebettete `style_reference.png` ist ein Qualitäts- und Stilanker, keine zu kopierende konkrete Szene. Der Produktionsauftrag verlangt final gerenderte cinematische CGI-/3D-Filmstills mit glaubwürdigen Materialien, physikalisch plausibler Beleuchtung, volumetrischer Atmosphäre, klarer räumlicher Tiefenstaffelung und komplexen Mikrodetails. Flache 2D-, Vektor-, Cutout-, Low-Poly-, Poster-, Collage- oder Storyboard-Optik ist ausdrücklich ausgeschlossen.

Bei der Einstellung **Menschlich / natürlich** verbietet der Produktionsauftrag ausdrücklich grobe eSpeak-, monotone Roboter- oder stark metallische Ersatzstimmen. Ist die bevorzugte Stimme nicht verfügbar, soll stattdessen die bestmögliche Stimme gewählt werden, die zu Charakter und gewünschter stimmlicher Wirkung passt. Jede Ersetzung muss in `manifest.json` und `production.log` dokumentiert werden. Eine bewusst synthetische Stimme wird nur verwendet, wenn **Robotisch / synthetisch** ausgewählt wurde. Systemanweisungen, Zusammenfassungen und Bildprompts dürfen ausdrücklich **nicht** mitgesprochen werden.

Kann das Zielsystem die Medien nicht direkt erzeugen, soll es die bereits im Übergabe-ZIP enthaltenen Dateien `build_story_video.py` und `build_video.bat` verwenden. Das Skript verarbeitet die erzeugten Szenenbilder, erzeugt oder übernimmt Szenen-TTS, mischt die echte `assets/background.wav`, erstellt `audio/final_mix.wav`, Einzelclips, Überblendungen, das finale MP4 und anschließend das Ergebnis-ZIP. Es zeigt Phasenfortschritt, schreibt `production.log` und lässt sich abbrechen. Für Stable Diffusion wird deutlich gemacht, dass das Bildmodell die Einzelbilder liefert, während der beigefügte Runner TTS, Timing, Übergänge, Videoschnitt und ZIP übernimmt.

## Audioexport

Mit **Story als Audiodatei speichern …** wird die aktuelle Erzählung unabhängig von der Echtzeitwiedergabe als Datei erzeugt. Der Export verwendet:

- den zur Story gehörenden Aktivierungssatz des Sprungantriebs
- die ausgewählte Windows-Stimme
- die eingestellte Sprechgeschwindigkeit
- die eingestellte Sprachlautstärke
- den aktivierten Hintergrundsound und dessen aktuelle Lautstärke

WAV-Dateien werden direkt durch die Anwendung erzeugt. Der Vorgang läuft in einem separaten Arbeitsthread, zeigt den aktuellen Verarbeitungsschritt und kann abgebrochen werden. Die Brückenatmosphäre wird automatisch bis zum Ende der Sprachausgabe wiederholt und mit der Stimme gemischt.

MP3 erscheint zusätzlich im Speicherdialog, wenn entweder `tools/ffmpeg.exe` vorhanden ist oder `ffmpeg` über die Windows-PATH-Variable gefunden wird. FFmpeg wird aus Lizenz- und Paketgrößengründen nicht mitgeliefert.

Für den Dateiexport werden Windows-OneCore/WinRT- oder SAPI-Stimmen verwendet. Ist in der Oberfläche eine Qt-Stimme ausgewählt, versucht die Anwendung eine gleichnamige Windows-Stimme zuzuordnen. Ist das nicht möglich, fordert sie zur Auswahl einer exportierbaren Windows-Stimme auf.

## Eigene Textbausteine

Die Satzteile befinden sich als einfache Textdateien im Ordner:

```text
data/vars/
```

Jede nicht leere Zeile kann bei der Generierung zufällig ausgewählt werden. Reihenfolge, Wiederholungen und Trennzeichen der einzelnen Bausteine werden in folgender Datei festgelegt:

```text
sequence_legacy.json
```

Einige Wörter sind absichtlich phonetisch oder ungewöhnlich geschrieben, damit bestimmte Windows-TTS-Stimmen sie besser aussprechen. Solche Schreibweisen sollten nur geändert werden, wenn die Aussprache anschließend mit der gewünschten Stimme getestet wurde.


### Erweiterung der Satzteilbibliothek in v60.14

Alle 87 vorhandenen Satzteil-Dateien wurden jeweils um genau sieben neue Varianten erweitert. Dadurch kamen **609 neue Zeilen** hinzu; die Bibliothek umfasst nun **1.863 nicht leere Satzteile**. Die bisherigen Zeilen und absichtlich phonetischen Schreibweisen wurden nicht verändert. Eine vollständige Übersicht befindet sich unter `docs/SENTENCE_FRAGMENT_EXPANSION_v60.14.md`; die hinzugefügten Zeilen sind zusätzlich maschinenlesbar in `data/fragment_expansion_v60.14.json` dokumentiert.

## Themes

Alle Themes liegen als eigenständige JSON-Dateien im Ordner `themes/` und können unabhängig vom Programmcode bearbeitet oder ergänzt werden.

Enthalten sind:

- Light
- Dark
- Sepia
- Ocean
- Matrix
- Hellfire
- Purple
- Aurora
- Legacy Beige

Vor der Aktivierung prüft die Anwendung unter anderem den Kontrast von Fenstertext, Eingabefeldern, Schaltflächen, Hover-Zuständen, markiertem Text, Fortschrittsanzeigen, Tooltips und deaktivierten Bedienelementen. Ein Theme mit unzureichendem Kontrast wird nicht geladen und erscheint in der Theme-Diagnose.

## Text-to-Speech-Stimmen

Der SciFi-Generator kombiniert Stimmen aus mehreren Quellen:

- Windows OneCore/WinRT
- klassische Windows-SAPI
- Qt TextToSpeech

Welche Stimmen verfügbar sind, hängt von der Windows-Version, den installierten Sprachpaketen und der Registrierung der jeweiligen Stimme ab. Unter **Hilfe → TTS-Stimmendiagnose** wird angezeigt, welche Stimme von welchem Backend erkannt wurde und ob bei der Erkennung Fehler aufgetreten sind.

## Hintergrundsound

Die mitgelieferte, generische Sci-Fi-Atmosphäre liegt unter:

```text
data/sounds/background.wav
```

Sie kann durch eine andere rechtmäßig verwendbare WAV-Datei mit demselben Namen ersetzt werden. Das Projekt enthält keine Audioaufnahmen aus Fernsehserien oder Filmen.

Bei einem Gesamtpaket wird die Datei nur dann zuverlässig von einem neuen Chat verwendet, wenn das empfohlene Übergabe-ZIP hochgeladen wird. Eine allein kopierte Textdatei enthält den Ton nicht. Der Produktionsauftrag verlangt deshalb zusätzlich `audio/final_mix.wav`, eine nicht-stumme MP4-Audiospur und eine ausdrückliche Prüfung, dass `assets/background.wav` bei aktivierter Brückenatmosphäre tatsächlich hörbar eingemischt wurde.

## Offline-Installation

Mit `build_wheelhouse.bat` können die benötigten Python-Pakete einmalig bei bestehender Internetverbindung in den Ordner `wheelhouse/` geladen werden. Danach kann der Installer diese Pakete lokal verwenden, ohne erneut einen Paketindex abzufragen.

## Systemanforderungen

- Windows 10 oder Windows 11
- Python 3.10 oder neuer
- PySide6 6.x
- mindestens eine nutzbare Windows- oder Qt-TTS-Stimme

## Fehlerdiagnose

- `run_tests.bat` führt die enthaltenen Tests aus.
- **Hilfe → TTS-Stimmendiagnose** zeigt erkannte Stimmen und Backend-Fehler.
- **Hilfe → Theme-Prüfung** zeigt gültige und abgelehnte Theme-Dateien.
- **Hilfe → Prompt-Profilprüfung** zeigt die externen Ziel-KI-Profile und eventuelle Ladefehler.
- `install_windows.bat` kann erneut ausgeführt werden, um die lokale Umgebung zu reparieren oder zu aktualisieren.
- Die App-Version wird zentral aus `version.txt` gelesen und erscheint auch in den Generierungsprotokollen.

## Datenschutz

Die Story-Generierung und Sprachausgabe erfolgen lokal. Geschichten, Satzbausteine und Sprachinhalte werden nicht durch die Anwendung hochgeladen. Eine Internetverbindung wird nur benötigt, wenn Python-Abhängigkeiten heruntergeladen werden müssen und kein lokales Wheelhouse vorhanden ist.

## Projektinformationen

Originalautor und ursprüngliche Textbestände: **zeittresor**  
Originalquelle und Updates: [github.com/zeittresor](https://github.com/zeittresor)

Für das Gesamtpaket wurde noch keine endgültige Weiterverteilungslizenz festgelegt. Vor einer Weitergabe veränderter Builds oder der enthaltenen Textbestände bitte `LICENSE_NOT_SET.txt` beachten.

---

## English summary

**SciFi-Generator v60.14** is a local Windows application that assembles randomized science-fiction mission reports from editable text fragments and narrates them with installed TTS voices. The original two-step workflow is preserved: generate a sector jump, then narrate it.

The application supports OneCore/WinRT, SAPI and Qt voices, WAV/optional MP3 export, reproducible seeds, logs, external themes, storyboards and complete media-production handoffs for ChatGPT, Grok, Gemini, Stable Diffusion or custom systems. Total-package handoffs include a strict execute-now instruction, a cinematic CGI/3D style-reference image, background audio, manifests, validation files and real Python/FFmpeg fallback scripts. Video resolution and frame rate are configurable; 1024×1024 and 8 fps are the defaults. The returned result ZIP can contain only the final video or additionally scene images, scene audio/final mix, clips and project files. Install Python 3.10 or newer, extract the archive and run `install_windows.bat`.
