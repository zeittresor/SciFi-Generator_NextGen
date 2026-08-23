from __future__ import annotations

from dataclasses import dataclass
import json

from prompt_profile_manager import PromptProfile
from storyboard_generator import StoryboardScene, build_visual_bible


@dataclass(frozen=True)
class MediaPackageSettings:
    aspect_ratio: str = "1:1"
    resolution: str = "1024x1024"
    width: int = 1024
    height: int = 1024
    fps: int = 8
    transition_seconds: float = 0.8
    output_video: str = "scifi_story.mp4"
    output_zip: str = "scifi_story_package.zip"
    voice_name: str = "Systemstandard"
    voice_id: str = ""
    voice_backend: str = "unbekannt"
    voice_backend_key: str = ""
    speech_rate: int = 0
    voice_volume: int = 100
    voice_character: str = "Menschlich / natürlich"
    voice_gender: str = "Weiblich"
    voice_quality: str = "Beste verfügbare Qualität"
    background_enabled: bool = True
    background_volume: int = 18
    background_filename: str = "background.wav"
    include_images_in_result_zip: bool = True
    include_audio_in_result_zip: bool = True
    include_clips_in_result_zip: bool = False
    include_project_files_in_result_zip: bool = True
    style_reference_filename: str = "style_reference.png"


def _format_profile_text(value: str, *, scene_count: int, settings: MediaPackageSettings) -> str:
    return value.format(
        scene_count=scene_count,
        scene_count_padded=f"{scene_count:02d}",
        aspect_ratio=settings.aspect_ratio,
        resolution=settings.resolution,
        width=settings.width,
        height=settings.height,
        fps=settings.fps,
        transition_seconds=f"{settings.transition_seconds:.2f}".rstrip("0").rstrip("."),
        output_video=settings.output_video,
        output_zip=settings.output_zip,
        voice_name=settings.voice_name,
        voice_backend=settings.voice_backend,
        speech_rate=settings.speech_rate,
        voice_volume=settings.voice_volume,
        voice_character=settings.voice_character,
        voice_gender=settings.voice_gender,
        voice_quality=settings.voice_quality,
        background_volume=settings.background_volume,
        background_filename=settings.background_filename,
        include_images=str(settings.include_images_in_result_zip).lower(),
        include_audio=str(settings.include_audio_in_result_zip).lower(),
        include_clips=str(settings.include_clips_in_result_zip).lower(),
        include_project_files=str(settings.include_project_files_in_result_zip).lower(),
        style_reference_filename=settings.style_reference_filename,
    )


def _safe_narration(scene: StoryboardScene) -> str:
    return (scene.narration_text or scene.summary).strip()


def _style_prompt_suffix(settings: MediaPackageSettings) -> str:
    return (
        f"Verwende {settings.style_reference_filename} ausschließlich als visuellen Stilanker und frühere "
        "Szenenbilder als Kontinuitätsreferenz. Das Ergebnis muss wie ein hochwertiger final gerenderter "
        "CGI-/3D-Science-Fiction-Filmstill wirken: glaubwürdige Materialien, physikalisch plausible Beleuchtung, "
        "volumetrische Atmosphäre, räumliche Tiefenstaffelung und komplexe Mikrodetails. Vermeide ausdrücklich "
        "flache 2D-Flächen, simple geometrische Formen, Vektor-/Cutout-/Low-Poly-Look, Storyboard- oder "
        "Posterästhetik, Collagen, Text, UI, Logos und Wasserzeichen."
    )


def _result_package_description(settings: MediaPackageSettings) -> str:
    items = ["fertiges Video"]
    if settings.include_images_in_result_zip:
        items.append("Szenenbilder")
    if settings.include_audio_in_result_zip:
        items.append("Szenenaudios und final_mix.wav")
    if settings.include_clips_in_result_zip:
        items.append("Einzelclips")
    if settings.include_project_files_in_result_zip:
        items.append("Story, Prompts, Manifest, Log und Build-Dateien")
    return ", ".join(items)


def _result_package_tree(settings: MediaPackageSettings) -> list[str]:
    lines = [settings.output_zip, f"├── {settings.output_video}"]
    optional: list[str] = []
    if settings.include_images_in_result_zip:
        optional.append("images/scene_01.png …")
    if settings.include_audio_in_result_zip:
        optional.extend(["audio/scene_01.wav …", "audio/final_mix.wav"])
    if settings.include_clips_in_result_zip:
        optional.append("clips/scene_01.mp4 …")
    if settings.include_project_files_in_result_zip:
        optional.extend([
            "story/full_story.txt", "prompts/storyboard_and_package_prompt.txt",
            "style_reference.png", "manifest.json", "production.log", "build_story_video.py",
        ])
    for index, item in enumerate(optional):
        branch = "└──" if index == len(optional) - 1 else "├──"
        lines.append(f"{branch} {item}")
    return lines


def build_media_manifest(
    scenes: list[StoryboardScene],
    *,
    target_name: str,
    profile: PromptProfile,
    settings: MediaPackageSettings,
) -> dict:
    return {
        "task": "produce_illustrated_audio_story_video",
        "target_ai": target_name,
        "target_profile": profile.name,
        "target_mode": profile.mode,
        "aspect_ratio": settings.aspect_ratio,
        "resolution": settings.resolution,
        "width": settings.width,
        "height": settings.height,
        "fps": settings.fps,
        "transition_seconds": settings.transition_seconds,
        "voice": {
            "name": settings.voice_name,
            "id": settings.voice_id,
            "backend": settings.voice_backend,
            "backend_key": settings.voice_backend_key,
            "rate": settings.speech_rate,
            "volume": settings.voice_volume,
            "character": settings.voice_character,
            "gender_expression": settings.voice_gender,
            "quality_target": settings.voice_quality,
            "native_chatgpt_voice_preferred": profile.profile_id == "chatgpt",
            "legacy_system_voice_allowed_for_final": settings.voice_character == "Robotisch / synthetisch",
            "fallback_policy": (
                "Prefer native target-system audio export. Otherwise use the best available high-quality natural or neural voice "
                "matching character and gender expression. Do not silently substitute eSpeak-like, robotic Linux legacy, "
                "or basic monotone system voices when a natural final voice was requested. Log every substitution."
            ),
            "forbidden_for_final": (
                [] if settings.voice_character == "Robotisch / synthetisch" else [
                    "eSpeak", "Festival", "robotic Linux TTS", "basic monotone legacy voices",
                    "clearly artificial fallback voices",
                ]
            ),
        },
        "background": {
            "enabled": settings.background_enabled,
            "filename": settings.background_filename if settings.background_enabled else "",
            "asset_path": "assets/background.wav" if settings.background_enabled else "",
            "volume": settings.background_volume if settings.background_enabled else 0,
            "must_be_mixed_into_final_audio": bool(settings.background_enabled),
            "silent_omission_is_forbidden": bool(settings.background_enabled),
        },
        "style_reference": {
            "enabled": True,
            "filename": settings.style_reference_filename,
            "role": "Primary visual style anchor only; do not copy its exact scene composition.",
            "requirements": [
                "cinematic high-end CGI / 3D film still",
                "physically plausible lighting and materials",
                "volumetric atmosphere and strong depth",
                "rich hard-surface and organic microdetail",
                "no flat geometric 2D composition",
                "no collage, panel, text, UI, logo or watermark",
            ],
        },
        "visual_quality": {
            "target": "cinematic final-rendered sci-fi film stills",
            "use_previous_scenes_as_references": True,
            "semantic_cleanup_of_story_text_for_images": True,
            "negative_style_rules": [
                "flat 2D look", "vector art", "cutout composition", "low-poly look",
                "simple geometric primitives", "storyboard sketch", "infographic", "poster layout",
                "collage or multiple panels", "visible text or interface elements",
            ],
        },
        "result_package": {
            "video_always_included": True,
            "include_images": settings.include_images_in_result_zip,
            "include_audio": settings.include_audio_in_result_zip,
            "include_clips": settings.include_clips_in_result_zip,
            "include_project_files": settings.include_project_files_in_result_zip,
            "note": "These switches control only the final returned ZIP. Images and audio still have to be produced to build the video.",
        },
        "delivery_contract": {
            "images_only_is_incomplete": True,
            "required_video": settings.output_video,
            "required_final_audio_for_production": "audio/final_mix.wav",
            "required_zip": settings.output_zip,
            "require_non_silent_audio_stream": True,
            "require_background_mix_when_enabled": bool(settings.background_enabled),
            "require_style_reference_usage": True,
        },
        "outputs": {
            "video": settings.output_video,
            "final_audio": "audio/final_mix.wav",
            "zip": settings.output_zip,
        },
        "scenes": [
            {
                "index": scene.index,
                "title": scene.title,
                "image": f"scene_{scene.index:02d}.png",
                "audio": f"scene_{scene.index:02d}.wav",
                "clip": f"scene_{scene.index:02d}.mp4",
                "narration_text": _safe_narration(scene),
                "image_prompt": f"{scene.prompt} {_style_prompt_suffix(settings)}",
                "start_step": scene.start_step,
                "end_step": scene.end_step,
            }
            for scene in scenes
        ],
    }


def render_media_package_text(
    scenes: list[StoryboardScene],
    *,
    full_story: str,
    source: str = "Lokal",
    model: str = "",
    profile: PromptProfile,
    custom_target_name: str = "",
    settings: MediaPackageSettings | None = None,
) -> str:
    settings = settings or MediaPackageSettings()
    target_name = custom_target_name.strip() if profile.profile_id == "other" and custom_target_name.strip() else profile.name
    scene_count = len(scenes)
    transition = f"{settings.transition_seconds:.2f}".rstrip("0").rstrip(".")
    background_description = (
        f"aktiv, Datei {settings.background_filename}, Lautstärke {settings.background_volume}%"
        if settings.background_enabled
        else "deaktiviert"
    )
    result_package_description = _result_package_description(settings)
    style_suffix = _style_prompt_suffix(settings)

    intro = profile.package_instruction_intro or (
        "Erstelle aus dem folgenden Storyboard eine vollständige, bilduntermalte Audiogeschichte. "
        "Erzeuge die Szenenbilder, vertone jeden Szenenabschnitt separat, passe die Bilddauer an die jeweilige "
        "Audiodauer an, verbinde alle Szenen chronologisch zu einem Video und stelle das Ergebnis zusammen mit "
        "den Einzeldateien möglichst als ZIP-Paket bereit."
    )

    lines = [
        "SCIFI-GENERATOR — GESAMTPAKET-PRODUKTIONSAUFTRAG",
        f"Zielsystem / LLM: {target_name}",
        f"Prompt-Erzeugung: {source}" + (f" ({model})" if model else ""),
        f"Anzahl Szenen: {scene_count}",
        f"Video: {settings.resolution}, {settings.aspect_ratio}, {settings.fps} fps",
        f"Übergang: sanfte Überblendung von {transition} Sekunden",
        f"TTS-Vorgabe: {settings.voice_name} [{settings.voice_backend}], Tempo {settings.speech_rate}, Lautstärke {settings.voice_volume}%",
        f"Stimmcharakter: {settings.voice_character}; stimmliche Wirkung: {settings.voice_gender}; Qualitätsziel: {settings.voice_quality}",
        f"Brückenatmosphäre: {background_description}",
        f"Stilreferenz: {settings.style_reference_filename}",
        f"Gewünschter Inhalt des finalen Ergebnis-ZIP: {result_package_description}",
        "",
        "WICHTIG — SOFORT AUSFÜHREN, NICHT NUR DAS ARCHIV PRÜFEN",
        "=" * 72,
        "Dies ist ausdrücklich kein reiner Bildserien-Auftrag und keine Bitte um eine Paketinspektion. Fehlende Output-Medien sind die zu erzeugenden Ergebnisse und kein Fehler des Übergabepakets.",
        "Das hochgeladene Übergabe-ZIP enthält bereits build_story_video.py, build_video.bat, requirements.txt, style_reference.png und die TTS-Helferskripte vollständig im Wurzelverzeichnis sowie zusätzlich unter offline_fallback/. Behaupte nicht, diese Dateien würden fehlen.",
        "Beginne mit der tatsächlichen Produktion: Erzeuge die Szenenbilder, speichere sie unter images/, erzeuge oder verwende Szenenaudio und führe anschließend die vorhandenen Build-Skripte aus, sofern die Sitzung Video und Audiomischung nicht direkt erledigen kann.",
        f"Arbeite nach der Bildgenerierung ohne erneute Rückfrage mit TTS, Audiomischung, Szenentiming, Videozusammenschnitt und Paketierung weiter, bis {settings.output_video} und {settings.output_zip} vorliegen.",
        "Nur Bilder, nur eine Dateiliste, nur eine Analyse oder nur Pseudocode erfüllen den Auftrag nicht.",
        "",
        profile.package_header_title,
        "=" * 72,
        _format_profile_text(intro, scene_count=scene_count, settings=settings),
        "",
        "VERBINDLICHER PRODUKTIONSABLAUF",
        "=" * 72,
    ]

    generic_rules = [
        "Erzeuge für jede der {scene_count} nummerierten Szenen genau ein separates, visuell konsistentes Bild im Seitenverhältnis {aspect_ratio}.",
        "Verwende style_reference.png als primären visuellen Stilanker. Sie definiert Renderqualität, Materialtiefe, Beleuchtung, atmosphärische Tiefe und CGI-/3D-Anmutung, nicht den konkreten Szeneninhalt.",
        "Jedes Szenenbild muss wie ein hochwertiger final gerenderter CGI-/3D-Science-Fiction-Filmstill wirken. Verboten sind flache 2D-Flächen, simple geometrische Formen, Vektor-/Cutout-/Low-Poly-Look, Storyboard-, Poster- oder Collage-Optik.",
        "Die Zielauflösung des finalen Videos ist exakt {resolution} Pixel. Erzeuge die Szenenbilder möglichst direkt in dieser Auflösung oder mindestens im identischen Seitenverhältnis; keine Verzerrung und kein unkontrolliertes Abschneiden wichtiger Bildinhalte.",
        "Falls Quellbilder nicht exakt zum Zielseitenverhältnis passen, passe sie durch kontrolliertes Cropping oder dezente Letterbox-/Pillarbox-Flächen an. Strecke Bilder niemals disproportional.",
        "Erzeuge für jede Szene eine eigene Audiodatei scene_XX.wav und sprich ausschließlich den dort angegebenen NARRATIONSTEXT; Zusammenfassung und Bildprompt dürfen nicht mitgesprochen werden.",
        "Verwende über alle Szenen hinweg dieselbe Stimme. Nutze bevorzugt die eigene native Sprachausgabe des Zielsystems, sofern sie Audiodateien exportieren kann; andernfalls verwende {voice_name} über {voice_backend}, mit Tempo {speech_rate} und Lautstärke {voice_volume} Prozent.",
        "Die Stimme muss die gewünschte Wirkung {voice_gender} und den Charakter {voice_character} besitzen. Das Qualitätsziel lautet {voice_quality}. Diese Vorgaben gelten auch für jede Ersatzstimme.",
        "Wenn der Charakter 'Menschlich / natürlich' gewählt wurde, nutze eine hochwertige natürliche beziehungsweise neuronale Stimme und vermeide grobe eSpeak-, monotone Roboter- oder stark metallische Ersatzstimmen. Robotische Nachbearbeitung ist nur beim ausdrücklich gewählten robotischen Charakter zulässig.",
        "Ist die bevorzugte Stimme nicht verfügbar oder widerspricht sie den gewählten Eigenschaften, wähle die bestmögliche passende Ersatzstimme. Eine Abweichung bei Stimme, Charakter oder stimmlicher Wirkung muss in manifest.json und production.log dokumentiert werden; nicht stillschweigend auf eine anders wirkende Stimme wechseln.",
        "Passe die sichtbare Dauer jeder Szene an die tatsächliche Dauer ihrer Audiodatei an. Das Bild bleibt während des zugehörigen Textabschnitts sichtbar; dezente langsame Zoom- oder Schwenkbewegungen sind zulässig.",
        "Blende beim Wechsel zur nächsten Szene sanft über. Verwende eine Crossfade-Dauer von ungefähr {transition_seconds} Sekunden und vermeide harte Bild- oder Tonsprünge.",
        "Erzeuge die Einzelclips scene_01.mp4 bis scene_{scene_count_padded}.mp4 und füge sie in der nummerierten Reihenfolge ohne vertauschte Szenen zusammen.",
        "Exportiere das fertige Video als {output_video} in {resolution}, {fps} fps, H.264-Video und AAC-Audio oder einem gleichwertig weit verbreiteten Format.",
        "Falls eine Hintergrundatmosphäre bereitgestellt wurde, verwende exakt die beigefügte Datei assets/background.wav, schleife sie leise unter der gesamten Erzählung, ohne die Stimme zu überdecken, und verwende die angegebene Lautstärke sowie sanfte Ein- und Ausblendungen. Die Atmosphäre darf nicht stillschweigend weggelassen oder durch Stille ersetzt werden.",
        "Erzeuge audio/final_mix.wav als nachweisbaren Mix aus Erzählstimme und – sofern aktiviert – assets/background.wav. Verwende anschließend genau diesen Mix als Audiospur des finalen Videos.",
        "Bevor du Erfolg meldest, prüfe, dass das finale MP4 eine hörbare, nicht-stumme Audiospur besitzt, die komplette Erzählung enthält und bei aktiviertem Hintergrundsound die Brückenatmosphäre hörbar eingemischt wurde.",
        "Packe das finale Ergebnis-ZIP exakt nach dem Abschnitt 'LIEFERUMFANG DES FINALEN ERGEBNIS-ZIP'. Das fertige Video ist immer enthalten; Bilder, Audiodateien, Clips und Projektdateien nur entsprechend der dortigen Auswahl.",
        "Die Lieferumfangsauswahl betrifft ausschließlich das finale zurückgegebene Ergebnis-ZIP. Für die Produktion müssen Szenenbilder, Szenenaudios und final_mix.wav trotzdem erzeugt werden, auch wenn sie anschließend nicht in das Ergebnis-ZIP aufgenommen werden sollen.",
        "Erzeuge keine Collage, keine sichtbare Schrift im Bild, keine Untertitel, Logos, Wasserzeichen oder Benutzeroberflächen, sofern sie nicht ausdrücklich verlangt werden.",
        "Führe den Auftrag möglichst vollständig aus, statt nur eine Analyse, Verbesserungsvorschläge oder eine erneute Zusammenfassung zu liefern. Beende die Arbeit ausdrücklich nicht nach der Erzeugung oder ZIP-Paketierung der Szenenbilder.",
        "Eine Lieferung, die ausschließlich PNG/JPG-Dateien enthält, gilt als fehlgeschlagen. Die Mindestlieferung ist entweder das fertige Video samt Audio und Gesamt-ZIP oder ein vollständig ausführbares Offline-Fallback-ZIP.",
        "Falls die Sitzung Audio oder Video nicht direkt erzeugen kann, verwende die bereits im Übergabe-ZIP enthaltenen echten Dateien build_story_video.py und build_video.bat. Erzeuge zuerst die Szenenbilder unter images/ und führe danach das Skript aus; liefere nicht bloß eine Beschreibung des Fallbacks.",
        "Das beigefügte Offline-Skript verwendet Python und FFmpeg, bevorzugt unter Windows die ausgewählte SAPI-/WinRT-Stimme, protokolliert Ersatzstimmen und mischt die beigefügte background.wav verbindlich in final_mix.wav und das MP4.",
    ]
    all_rules = list(profile.package_instruction_rules) or generic_rules
    # Ensure baseline rules remain present even when profiles add special handling.
    if profile.package_instruction_rules:
        all_rules.extend(generic_rules)
    for index, rule in enumerate(all_rules, start=1):
        lines.append(f"{index}. {_format_profile_text(rule, scene_count=scene_count, settings=settings)}")

    lines.extend(["", "GLOBALE VISUELLE SERIENBIBEL", "=" * 72])
    for label, value in build_visual_bible(scenes, settings.aspect_ratio):
        lines.append(f"{label}: {value}")

    lines.extend([
        "",
        "VERBINDLICHER VISUELLER QUALITÄTS- UND STILANKER",
        "=" * 72,
        f"Primäre Stilreferenz: {settings.style_reference_filename}",
        "Zielbild: hochwertige, final gerenderte cinematische CGI-/3D-Science-Fiction-Filmstills mit glaubwürdiger räumlicher Tiefe.",
        "Die Referenz bestimmt Qualitätsniveau, Materialtiefe, Lichtdramaturgie, Detaildichte und filmische Wirkung; ihre konkrete Szene darf nicht blind kopiert werden.",
        "Verbindlich: physikalisch plausible Beleuchtung, komplexe Hard-Surface- und organische Mikrodetails, volumetrischer Dunst oder atmosphärische Streuung, klare Vordergrund-/Mittelgrund-/Hintergrund-Staffelung und konsistenter Farbraum.",
        "Ausdrücklich verboten: flacher 2D-Look, einfache geometrische Flächen, Vektor-/Cutout-/Papier-/Icon-Look, Low-Poly, Storyboard/Skizze, Poster, Collage, Panels, sichtbare Schrift, UI, Logos und Wasserzeichen.",
        "Kontinuität: Frühere Szenenbilder aktiv als Referenz für Schiff und alle im aktuellen Story-Zweig tatsächlich vorkommenden wiederkehrenden Orte, Landschaften, Kreaturen, Pflanzen, Stationen, Ausrüstung, Materialien, Maßstäbe und Lichtstimmungen weiterverwenden. Nicht vorkommende Motive nicht hinzuerfinden.",
        "Semantische Übersetzung: Phonetisch oder grammatikalisch ungewöhnliche Storytexte für die Bildgenerierung sinngemäß bereinigen; niemals als sichtbaren Text übernehmen.",
        "",
        "AUDIO- UND TTS-QUALITÄTSREGELN",
        "=" * 72,
        ("Priorität: native ChatGPT-Stimme mit exportierbarer Audiodatei, danach hochwertige neurale/natürliche Stimme." if profile.profile_id == "chatgpt" else "Priorität: native exportierbare Stimme des Zielsystems, danach hochwertige neurale/natürliche Stimme."),
        f"Gewünschter Charakter: {settings.voice_character}; stimmliche Wirkung: {settings.voice_gender}; Qualitätsziel: {settings.voice_quality}.",
        "Natürlichkeit und Prosodie haben Vorrang vor einem bestimmten Stimmnamen. Eine hochwertige Ersatzstimme ist einer technisch verfügbaren, aber hörbar minderwertigen Legacy-Stimme vorzuziehen.",
        ("Bei natürlichem Stimmcharakter nicht als finale Stimme zulässig: eSpeak/Festival, robotische Linux-Systemstimmen, monotone Legacy-Windows-Stimmen, stark metallische oder abgehackte Prosodie." if settings.voice_character != "Robotisch / synthetisch" else "Eine bewusst robotische Stimme ist gewählt; dennoch auf klare Verständlichkeit, gleichmäßige Lautheit und saubere Audioqualität achten."),
        "Ist keine Stimme in der geforderten Qualität verfügbar, nicht stillschweigend minderwertig ersetzen: Einschränkung dokumentieren und einen austauschbaren Narrations-Workflow liefern.",
        "",
        "AUDIO- UND VIDEOREGELN",
        "=" * 72,
        f"Stimme: {settings.voice_name}",
        f"TTS-Backend/Fallback: {settings.voice_backend}",
        f"Sprechtempo: {settings.speech_rate}",
        f"Sprachlautstärke: {settings.voice_volume}%",
        f"Stimmcharakter: {settings.voice_character}",
        f"Stimmliche Wirkung: {settings.voice_gender}",
        f"TTS-Qualitätsziel: {settings.voice_quality}",
        "Ersatzstimmen-Regel: Die gewünschte Natürlichkeit und stimmliche Wirkung haben Vorrang vor einer ungeeigneten technisch verfügbaren Stimme; jede Abweichung protokollieren.",
        f"Hintergrundsound: {background_description}",
        ("Hintergrunddatei im Übergabepaket: assets/background.wav; diese Datei ist verbindlich in final_mix.wav und in die MP4-Audiospur einzumischen." if settings.background_enabled else "Hintergrunddatei: nicht erforderlich, da Hintergrundsound deaktiviert ist."),
        f"Zielauflösung: {settings.resolution} Pixel",
        f"Videofläche: {settings.width} × {settings.height} Pixel; Seitenverhältnis {settings.aspect_ratio}",
        "Skalierung: Seitenverhältnisse bewahren; keine proportionale Verzerrung. Bei abweichenden Quellen kontrolliert beschneiden oder Letterbox/Pillarbox verwenden.",
        f"Bildrate: {settings.fps} fps",
        f"Szenenübergang: Crossfade ca. {transition} s",
        "Timing: Jede visuelle Szene endet erst nach dem Ende ihrer zugehörigen Sprachausgabe; kein Textabschnitt darf abgeschnitten werden.",
        "Audio: Lautheit zwischen den Szenen angleichen, Übersteuerung vermeiden und Sprache gegenüber der Atmosphäre priorisieren.",
        "",
        "MINDESTLIEFERUNG / COMPLETION GATE",
        "=" * 72,
        f"1. {settings.output_video} existiert, ist abspielbar und enthält eine hörbare, nicht-stumme Audiospur.",
        "2. Die komplette Story ist vertont; kein NARRATIONSTEXT wurde abgeschnitten oder ausgelassen.",
        "3. audio/final_mix.wav wurde während der Produktion erzeugt und ist die tatsächlich im Video verwendete Tonmischung.",
        ("4. assets/background.wav ist im final_mix.wav und im finalen MP4 leise, aber hörbar enthalten." if settings.background_enabled else "4. Hintergrundsound war deaktiviert; es darf kein Hintergrundmix behauptet werden."),
        f"5. {settings.style_reference_filename} wurde als visueller Stilanker verwendet und die Bilder entsprechen dem final gerenderten CGI-/3D-Filmstill-Ziel.",
        f"6. {settings.output_zip} enthält exakt den ausgewählten Lieferumfang: {result_package_description}.",
        "7. Ein ZIP mit ausschließlich Bildern und ohne fertiges Video besteht die Prüfung ausdrücklich nicht.",
        "8. Ist direkte Videoerzeugung technisch unmöglich, muss stattdessen ein vollständig ausführbares Offline-Fallback-ZIP mit echten Skripten und allen verfügbaren Assets geliefert werden; Pseudocode genügt nicht.",
        "",
        "LIEFERUMFANG DES FINALEN ERGEBNIS-ZIP",
        "=" * 72,
        "Diese Auswahl betrifft nur das zurückgelieferte Ergebnis-ZIP, nicht die internen Produktionsschritte.",
        f"Fertiges Video: JA — {settings.output_video}",
        f"Szenenbilder im Ergebnis-ZIP: {'JA' if settings.include_images_in_result_zip else 'NEIN'}",
        f"Szenenaudios und final_mix.wav im Ergebnis-ZIP: {'JA' if settings.include_audio_in_result_zip else 'NEIN'}",
        f"Einzelclips im Ergebnis-ZIP: {'JA' if settings.include_clips_in_result_zip else 'NEIN'}",
        f"Story, Prompts, Manifest, Log und Build-Dateien im Ergebnis-ZIP: {'JA' if settings.include_project_files_in_result_zip else 'NEIN'}",
        "",
        "ERWARTETE PAKETSTRUKTUR",
        "=" * 72,
        *_result_package_tree(settings),
    ])

    if profile.package_output_notes:
        lines.extend(["", "ZIELSYSTEM-HINWEISE", "=" * 72])
        for note in profile.package_output_notes:
            lines.append(f"- {_format_profile_text(note, scene_count=scene_count, settings=settings)}")

    lines.extend(["", "SZENEN-PRODUKTIONSPLAN", "=" * 72, ""])
    for scene in scenes:
        lines.extend([
            f"[{scene.index:02d}] {scene.title}",
            f"Story-Schritte: {scene.start_step}-{scene.end_step}",
            f"Bilddatei: images/scene_{scene.index:02d}.png",
            f"Audiodatei: audio/scene_{scene.index:02d}.wav",
            f"Szenenclip: clips/scene_{scene.index:02d}.mp4",
            "NARRATIONSTEXT — exakt für die Sprachausgabe dieser Szene:",
            _safe_narration(scene),
            "",
        ])
        if profile.is_diffusion:
            positive_parts = [
                "photorealistic cinematic science fiction film still",
                "retro-futuristic exploration mission",
                "believable industrial technology",
                "dramatic lighting",
                "high detail",
                "clear depth layering",
                scene.prompt,
                style_suffix,
                profile.scene_suffix,
            ]
            positive_prompt = ", ".join(part.strip().rstrip(".") for part in positive_parts if part.strip())
            lines.extend(["POSITIVE PROMPT:", positive_prompt])
        else:
            lines.append("BILDGENERIERUNGS-AUFTRAG:")
            if profile.scene_prefix:
                lines.append(profile.scene_prefix)
            lines.append(f"{scene.prompt} {style_suffix}")
            if profile.scene_suffix:
                lines.append(profile.scene_suffix)
        if profile.negative_prompt:
            lines.extend(["NEGATIVE PROMPT:", profile.negative_prompt])
        lines.extend([
            "TIMING-ANWEISUNG:",
            f"Halte dieses Szenenbild beziehungsweise den daraus erzeugten subtil bewegten Clip für die vollständige Dauer von audio/scene_{scene.index:02d}.wav sichtbar. Danach sanft zur nächsten Szene überblenden.",
            "",
        ])

    manifest = build_media_manifest(scenes, target_name=target_name, profile=profile, settings=settings)
    lines.extend([
        "MANIFEST-VORLAGE",
        "=" * 72,
        json.dumps(manifest, ensure_ascii=False, indent=2),
        "",
        "VOLLSTÄNDIGE STORY — NUR ALS KONTEXT, NICHT ZUSÄTZLICH VORLESEN",
        "=" * 72,
        full_story.strip(),
        "",
        "ABSCHLUSSANWEISUNG",
        "=" * 72,
        f"Beginne mit Szene 01 und arbeite chronologisch bis Szene {scene_count:02d}. Stoppe nach den Bildern nicht, sondern fahre automatisch mit TTS, Audiomischung, Timing, Video und ZIP fort. Liefere am Ende {settings.output_video} und {settings.output_zip}. Eine reine Bild-ZIP ist ausdrücklich unvollständig. Falls direkte Audio- oder Videoerzeugung nicht möglich ist, nutze die bereits beigefügten Build-Skripte; analysiere das Paket nicht nur und behaupte nicht, die Skripte fehlten.",
    ])
    return "\n".join(lines).strip() + "\n"
