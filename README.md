# SciFi-Generator

**Aktuelle Version: 60.3**

Der **SciFi-Generator** ist eine lokale Windows-Desktopanwendung, die zufällige Science-Fiction-Missionsberichte aus frei bearbeitbaren Textbausteinen zusammensetzt und anschließend mit einer installierten Text-to-Speech-Stimme vorliest.

Der Ablauf orientiert sich an der ursprünglichen Anwendung:

1. **Sektor-Sprung berechnen** erzeugt eine neue Geschichte.
2. **Sprung durchführen** liest die bereits berechnete Geschichte vor.

Die Story und das detaillierte Auswahlprotokoll bleiben standardmäßig ausgeblendet und werden nur bei Bedarf über **Story / Log einblenden** geöffnet.

<img width="507" height="927" alt="hjfgdksk" src="https://github.com/user-attachments/assets/c573e80d-865f-47f2-8218-5ab91bdea81e" />

## Funktionen

- Zufällige Science-Fiction-Geschichten aus externen Satzteil-Dateien
- Windows-Sprachausgabe über OneCore/WinRT, SAPI und Qt TextToSpeech
- Auswahl der Stimme sowie Regelung von Geschwindigkeit und Lautstärke
- Pause, Fortsetzen und Stoppen der Sprachausgabe
- Optionale, in einer Schleife abgespielte Brückenatmosphäre mit eigener Lautstärke
- Kompakte Oberfläche mit ausblendbarer Story- und Protokollansicht
- Scrollbarer Bedienbereich mit vertikaler und bei Bedarf horizontaler Scrollleiste
- Automatische, responsive UI-Skalierung für Schrift, Schaltflächen, Eingabefelder, Abstände und Scrollleisten
- Reproduzierbare Geschichten durch einen frei wählbaren Seed
- Ausführliche Generierungsprotokolle mit App-Version, Quelldatei, Zeilennummer und ausgewähltem Text
- Externe JSON-Themes mit automatischer Kontrastprüfung
- Frei bearbeitbare Generierungsreihenfolge in `sequence_legacy.json`
- Projektlokale Python-Umgebung und optionales Wheelhouse für Offline-Installationen

## Schnellstart unter Windows

1. Python 3.10 oder neuer installieren und bei der Installation **Add Python to PATH** aktivieren.
2. Das Release-Archiv vollständig in einen beschreibbaren Ordner entpacken.
3. `install_windows.bat` starten.
4. Nach erfolgreicher Installation die Anwendung automatisch starten lassen oder später `start_app.bat` ausführen.

Der Installer erzeugt eine lokale `.venv`, installiert die benötigten Pakete und prüft anschließend die Programmdateien. Eine bereits vorhandene virtuelle Umgebung wird wiederverwendet.

## Bedienung

1. Unter **Stimme** eine verfügbare TTS-Stimme auswählen.
2. Geschwindigkeit sowie Sprach- und Hintergrundlautstärke einstellen.
3. **Sektor-Sprung berechnen** anklicken.
4. **Sprung durchführen** anklicken, um die Story vorzulesen.
5. Über **Story / Log einblenden** kann die Geschichte angesehen, bearbeitet oder gespeichert und das Auswahlprotokoll geprüft werden.

Der Bedienbereich wird nicht auf eine zu geringe Fensterhöhe zusammengestaucht. Reicht der verfügbare Platz nicht aus, erscheinen automatisch vertikale beziehungsweise horizontale Scrollleisten. Das gilt insbesondere für kleinere Displays, hohe Windows-Skalierungswerte und umfangreiche Stimmennamen.

Wird das Fenster vergrößert, skaliert die Oberfläche automatisch mit: Schrift, Schaltflächen, Eingabefelder, Regler, Abstände, Kontrollkästchen und Scrollleisten werden bis zu einer sinnvollen Obergrenze gemeinsam vergrößert. Beim Verkleinern bleiben die Elemente lesbar und werden nicht unter ihre normale Größe geschrumpft; stattdessen übernimmt der Scrollbereich.

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

**SciFi-Generator v60.3** is a local Windows application that assembles randomized science-fiction mission reports from editable text fragments and narrates them with an installed TTS voice. The original two-step workflow is preserved: **Sektor-Sprung berechnen** generates a story, and **Sprung durchführen** reads it aloud.

The application supports Windows OneCore/WinRT, SAPI and Qt voices, optional bridge ambience, reproducible seeds, detailed generation logs, external contrast-checked JSON themes, a scrollable control panel and responsive UI scaling. Install Python 3.10 or newer, extract the archive and run `install_windows.bat`.
