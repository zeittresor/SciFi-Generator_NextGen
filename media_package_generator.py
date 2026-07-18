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
    fps: int = 30
    transition_seconds: float = 0.8
    output_video: str = "scifi_story.mp4"
    output_zip: str = "scifi_story_package.zip"
    voice_name: str = "Systemstandard"
    voice_backend: str = "unbekannt"
    speech_rate: int = 0
    voice_volume: int = 100
    voice_character: str = "Menschlich / natürlich"
    voice_gender: str = "Weiblich"
    voice_quality: str = "Beste verfügbare Qualität"
    background_enabled: bool = True
    background_volume: int = 18
    background_filename: str = "background.wav"


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
    )


def _safe_narration(scene: StoryboardScene) -> str:
    return (scene.narration_text or scene.summary).strip()


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
            "backend": settings.voice_backend,
            "rate": settings.speech_rate,
            "volume": settings.voice_volume,
            "character": settings.voice_character,
            "gender_expression": settings.voice_gender,
            "quality_target": settings.voice_quality,
            "fallback_policy": "Use the closest available voice matching character, gender expression and quality; log every substitution.",
        },
        "background": {
            "enabled": settings.background_enabled,
            "filename": settings.background_filename if settings.background_enabled else "",
            "volume": settings.background_volume if settings.background_enabled else 0,
        },
        "outputs": {
            "video": settings.output_video,
            "final_audio": "final_mix.wav",
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
                "image_prompt": scene.prompt,
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
        "Falls eine Hintergrundatmosphäre bereitgestellt wurde, schleife sie leise unter der gesamten Erzählung, ohne die Stimme zu überdecken. Verwende die angegebene Lautstärke und sanfte Ein- und Ausblendungen.",
        "Stelle nach Möglichkeit ein ZIP-Paket {output_zip} bereit. Es soll mindestens das fertige Video, alle Szenenbilder, alle Szenenaudios, die Einzelclips, die verwendeten Prompts und eine manifest.json enthalten.",
        "Erzeuge keine Collage, keine sichtbare Schrift im Bild, keine Untertitel, Logos, Wasserzeichen oder Benutzeroberflächen, sofern sie nicht ausdrücklich verlangt werden.",
        "Führe den Auftrag möglichst vollständig aus, statt nur eine Analyse, Verbesserungsvorschläge oder eine erneute Zusammenfassung zu liefern.",
        "Falls die Sitzung Bilder, TTS, Videos oder ZIP-Dateien nicht direkt erzeugen kann, erstelle stattdessen ein vollständiges offline ausführbares Produktionspaket mit build_story_video.py, build_video.bat, requirements.txt, manifest.json und klarer Ordnerstruktur.",
        "Das Offline-Skript soll Python und FFmpeg verwenden, unter Windows die ausgewählte SAPI-/WinRT-Stimme bevorzugen, bei Nichterreichbarkeit sauber auf die Systemstimme zurückfallen und sichtbaren Gesamt- sowie Phasenfortschritt, Status, Laufzeit, Logdatei und Abbruchmöglichkeit bieten.",
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
        f"Zielauflösung: {settings.resolution} Pixel",
        f"Videofläche: {settings.width} × {settings.height} Pixel; Seitenverhältnis {settings.aspect_ratio}",
        "Skalierung: Seitenverhältnisse bewahren; keine proportionale Verzerrung. Bei abweichenden Quellen kontrolliert beschneiden oder Letterbox/Pillarbox verwenden.",
        f"Bildrate: {settings.fps} fps",
        f"Szenenübergang: Crossfade ca. {transition} s",
        "Timing: Jede visuelle Szene endet erst nach dem Ende ihrer zugehörigen Sprachausgabe; kein Textabschnitt darf abgeschnitten werden.",
        "Audio: Lautheit zwischen den Szenen angleichen, Übersteuerung vermeiden und Sprache gegenüber der Atmosphäre priorisieren.",
        "",
        "ERWARTETE PAKETSTRUKTUR",
        "=" * 72,
        f"{settings.output_zip}",
        f"├── {settings.output_video}",
        "├── images/scene_01.png …",
        "├── audio/scene_01.wav …",
        "├── audio/final_mix.wav",
        "├── clips/scene_01.mp4 …",
        "├── story/full_story.txt",
        "├── prompts/storyboard_and_package_prompt.txt",
        "├── assets/background.wav       (falls Hintergrundsound verwendet wird)",
        "├── manifest.json",
        "├── build_story_video.py        (falls ein Offline-Fallback nötig ist)",
        "├── build_video.bat              (falls ein Offline-Fallback nötig ist)",
        "├── requirements.txt             (falls ein Offline-Fallback nötig ist)",
        "└── production.log",
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
                profile.scene_suffix,
            ]
            positive_prompt = ", ".join(part.strip().rstrip(".") for part in positive_parts if part.strip())
            lines.extend(["POSITIVE PROMPT:", positive_prompt])
        else:
            lines.append("BILDGENERIERUNGS-AUFTRAG:")
            if profile.scene_prefix:
                lines.append(profile.scene_prefix)
            lines.append(scene.prompt)
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
        f"Beginne mit Szene 01 und arbeite chronologisch bis Szene {scene_count:02d}. Liefere am Ende {settings.output_video} und möglichst {settings.output_zip}. Falls direkte Dateierzeugung nicht möglich ist, liefere stattdessen das vollständig ausführbare Offline-Produktionspaket, nicht nur Pseudocode.",
    ])
    return "\n".join(lines).strip() + "\n"
