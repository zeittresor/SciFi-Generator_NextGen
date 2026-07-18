from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
import re

from story_engine import GenerationResult, Selection, StoryEngine
from prompt_profile_manager import PromptProfile


@dataclass(frozen=True)
class StoryboardScene:
    index: int
    title: str
    summary: str
    prompt: str
    start_step: int
    end_step: int
    narration_text: str = ""


_CANONICAL_SCENE_ENDS: list[tuple[str, set[str], str]] = [
    (
        "Warp-Austritt und Systemname",
        {"Systembezeichnung"},
        "Weite Totale des Schiffes beim Austritt aus dem Warp, Blick auf das fremde Sternensystem.",
    ),
    (
        "Systemanalyse",
        {"system_infos.ini"},
        "Panoramablick auf das Sternensystem mit Sonnen, Planeten und begleitender Sensorscan-Ästhetik.",
    ),
    (
        "Zielplanet im Visier",
        {"planet_target_info.ini"},
        "Orbitalansicht des Zielplaneten und seines Umfelds, als würde die Crew den Anflug vorbereiten.",
    ),
    (
        "Oberflächenscan des Planeten",
        {"life_possibility.ini"},
        "Detailreicher Überblick über Landschaft, Material, Flüssigkeiten, Temperatur und Wolken des Planeten.",
    ),
    (
        "Landeanflug und Anomalie",
        {"planet_surface_scan_anti_found.ini"},
        "Dramatische Landesequenz mit Sensorwarnung und erster unnatürlicher Anomalie auf der Oberfläche.",
    ),
    (
        "Erste Alien-Sichtung",
        {"life_alien_size.ini"},
        "Erster klarer Blick auf die fremde Lebensform mit Farbe, Transparenz und Größe im Kontext der Umgebung.",
    ),
    (
        "Alien-Anatomie",
        {"life_alien_arms.ini"},
        "Ganzkörperdarstellung des Wesens mit Torso, Gliedmaßen oder Implantaten, wie in einem Sci-Fi-Bestiarium.",
    ),
    (
        "Alien-Gesicht und Augen",
        {"life_alien_eyes.ini"},
        "Nahe, verstörende Detailansicht von Gesicht, Mundpartie und Augen des Wesens.",
    ),
    (
        "Kontakt, Irritation und Rückzug",
        {"we_leaf_desc.ini"},
        "Spannungsgeladene Szene des missglückten Kontakts und des hektischen Rückzugs zum Schiff.",
    ),
    (
        "Flucht und Sprungvorbereitung",
        {"start_jumpdrive.ini"},
        "Dynamischer Abflug zurück ins All mit Umlaufbahn, Warnboje und vorbereitetem Warp-Sprung.",
    ),
]

_MERGE_MAP: dict[int, list[list[int]]] = {
    6: [[0, 1], [2, 3], [4], [5, 6, 7], [8], [9]],
    7: [[0, 1], [2], [3], [4], [5, 6, 7], [8], [9]],
    8: [[0, 1], [2], [3], [4], [5, 6], [7], [8], [9]],
    9: [[0, 1], [2], [3], [4], [5], [6], [7], [8], [9]],
    10: [[0], [1], [2], [3], [4], [5], [6], [7], [8], [9]],
}


def _normalize_text(text: str) -> str:
    text = text.replace("\u2029", " ")
    text = re.sub(r"\s+", " ", text.strip())
    return text


def _shorten(text: str, max_chars: int = 320) -> str:
    text = _normalize_text(text)
    if len(text) <= max_chars:
        return text
    shortened = text[: max_chars - 1].rsplit(" ", 1)[0].strip()
    return shortened + " …"


def _selection_narration_text(items: Iterable[Selection]) -> str:
    parts: list[str] = []
    for item in items:
        value = item.rendered_text or StoryEngine.legacy_umlaut_conversion(item.raw_text)
        if value.strip():
            parts.append(value)
    return _normalize_text("".join(parts))


def _selection_text(items: Iterable[Selection]) -> str:
    return _shorten(_selection_narration_text(items))


def _scene_prompt(index: int, title: str, summary: str, visual_hint: str, continuity_hint: str) -> str:
    style = (
        "Authentisch wirkende Science-Fiction-Szene, realistisch, cineastisch, detailreich, glaubwürdige Materialien, "
        "dramatische Beleuchtung, hochwertige Atmosphäre, klare Tiefenstaffelung, kein eingeblendeter Text, keine Wasserzeichen."
    )
    return (
        f"Szene {index}: {title}. {style} "
        f"Zeige folgende Handlung und Details: {summary}. "
        f"Bildkomposition: {visual_hint} "
        f"Kontinuität über alle Bilder hinweg: {continuity_hint}"
    )


def _build_canonical_groups(result: GenerationResult) -> list[tuple[str, str, list[Selection]]]:
    groups: list[tuple[str, str, list[Selection]]] = []
    current_index = 0
    selections = list(result.selections)
    for title, end_labels, visual_hint in _CANONICAL_SCENE_ENDS:
        bucket: list[Selection] = []
        while current_index < len(selections):
            item = selections[current_index]
            bucket.append(item)
            current_index += 1
            if item.label in end_labels:
                break
        groups.append((title, visual_hint, bucket))
    if current_index < len(selections) and groups:
        title, visual_hint, bucket = groups[-1]
        bucket.extend(selections[current_index:])
        groups[-1] = (title, visual_hint, bucket)
    return groups


def generate_storyboard(result: GenerationResult, scene_count: int = 8) -> list[StoryboardScene]:
    scene_count = min(10, max(6, int(scene_count)))
    canonical = _build_canonical_groups(result)
    merge_map = _MERGE_MAP[scene_count]

    ship_context = "ein satirisch-ernster Retro-Sci-Fi-Ton, glaubwürdige Technik, dieselbe Crew-Perspektive und dasselbe Sternensystem"
    scenes: list[StoryboardScene] = []

    for new_index, group_indexes in enumerate(merge_map, start=1):
        merged_title = " / ".join(canonical[idx][0] for idx in group_indexes)
        merged_visual = " ".join(canonical[idx][1] for idx in group_indexes)
        merged_items: list[Selection] = []
        for idx in group_indexes:
            merged_items.extend(canonical[idx][2])
        if not merged_items:
            continue
        narration_text = _selection_narration_text(merged_items)
        summary = _shorten(narration_text)
        prompt = _scene_prompt(new_index, merged_title, summary, merged_visual, ship_context)
        scenes.append(
            StoryboardScene(
                index=new_index,
                title=merged_title,
                summary=summary,
                prompt=prompt,
                start_step=merged_items[0].index,
                end_step=merged_items[-1].index,
                narration_text=narration_text,
            )
        )
    return scenes


def _find_scene_summary(scenes: list[StoryboardScene], *keywords: str) -> str:
    for scene in scenes:
        title = scene.title.lower()
        if any(keyword.lower() in title for keyword in keywords):
            return scene.summary
    return ""


def build_visual_bible(scenes: list[StoryboardScene], aspect_ratio: str = "16:9") -> list[tuple[str, str]]:
    system = _find_scene_summary(scenes, "warp-austritt", "systemanalyse")
    world = _find_scene_summary(scenes, "oberflächenscan")
    landing = _find_scene_summary(scenes, "landeanflug")
    alien_body = _find_scene_summary(scenes, "erste alien", "alien-anatomie")
    alien_face = _find_scene_summary(scenes, "alien-gesicht")

    entries = [
        (
            "Bildstil",
            "Authentisch wirkende, realistische und cineastische Retro-Science-Fiction mit glaubwürdigen Materialien, "
            "dramatischer Beleuchtung, klarer Tiefenstaffelung und einem subtil satirisch-ernsten Ton.",
        ),
        (
            "Kameraformat",
            f"Breitbild {aspect_ratio}; jede Szene als eigenständiger Filmstill, keine Collage und kein Mehrfachpanel.",
        ),
        (
            "Raumschiff",
            "Dasselbe robuste retro-futuristische Forschungs- und Landeschiff in jeder Szene: industrielle Konstruktion, "
            "sichtbare Nutzungsspuren, glaubwürdige Triebwerke und wiedererkennbare Silhouette.",
        ),
    ]
    if system:
        entries.append(("Sternensystem", system))
    if world or landing:
        entries.append(("Planet und Oberfläche", _shorten(" ".join(part for part in (world, landing) if part), 520)))
    if alien_body or alien_face:
        entries.append(("Wiederkehrendes Alien", _shorten(" ".join(part for part in (alien_body, alien_face) if part), 520)))
    entries.extend([
        (
            "Kontinuitätsregel",
            "Ein einmal etabliertes Design für Schiff, Welt, Alien, Raumanzüge und Technik darf in späteren Szenen nicht "
            "grundlos verändert werden. Frühere Bilder sind, soweit möglich, als Referenz weiterzuverwenden.",
        ),
        (
            "Ausschlüsse",
            "Keine sichtbare Schrift, Untertitel, Logos, Wasserzeichen oder Benutzeroberflächen. Phonetische Schreibweisen "
            "aus der Story sind sinngemäß zu interpretieren und nicht als Text abzubilden.",
        ),
    ])
    return entries


def _format_profile_text(value: str, *, scene_count: int, aspect_ratio: str) -> str:
    return value.format(
        scene_count=scene_count,
        scene_count_padded=f"{scene_count:02d}",
        aspect_ratio=aspect_ratio,
    )


def _stable_diffusion_positive(scene: StoryboardScene, profile: PromptProfile) -> str:
    parts = [
        "photorealistic cinematic science fiction film still",
        "retro-futuristic exploration mission",
        "believable industrial technology",
        "dramatic lighting",
        "high detail",
        "clear depth layering",
        scene.prompt,
    ]
    if profile.scene_suffix:
        parts.append(profile.scene_suffix)
    return ", ".join(part.strip().rstrip(".") for part in parts if part.strip())


def render_storyboard_text(
    scenes: list[StoryboardScene],
    *,
    source: str = "Lokal",
    model: str = "",
    profile: PromptProfile | None = None,
    custom_target_name: str = "",
    aspect_ratio: str = "16:9",
) -> str:
    if profile is None:
        lines = [
            "SCIFI-GENERATOR — BILD-PROMPTS / STORYBOARD",
            f"Quelle: {source}" + (f" ({model})" if model else ""),
            f"Anzahl Szenen: {len(scenes)}",
            "",
        ]
        for scene in scenes:
            lines.append(f"[{scene.index:02d}] {scene.title}")
            lines.append(f"Schritte: {scene.start_step}-{scene.end_step}")
            lines.append(f"Zusammenfassung: {scene.summary}")
            lines.append("Prompt:")
            lines.append(scene.prompt)
            lines.append("")
        return "\n".join(lines).strip() + "\n"

    target_name = custom_target_name.strip() if profile.profile_id == "other" and custom_target_name.strip() else profile.name
    scene_count = len(scenes)
    lines = [
        "SCIFI-GENERATOR — AUSFÜHRBARER BILDSERIEN-AUFTRAG",
        f"Ziel-KI: {target_name}",
        f"Prompt-Erzeugung: {source}" + (f" ({model})" if model else ""),
        f"Anzahl Szenen: {scene_count}",
        f"Seitenverhältnis: {aspect_ratio}",
        "",
        profile.header_title,
        "=" * 72,
        _format_profile_text(profile.instruction_intro, scene_count=scene_count, aspect_ratio=aspect_ratio),
        "",
        "VERBINDLICHE REGELN",
    ]
    for index, rule in enumerate(profile.instruction_rules, start=1):
        lines.append(f"{index}. {_format_profile_text(rule, scene_count=scene_count, aspect_ratio=aspect_ratio)}")

    lines.extend(["", "GLOBALE VISUELLE SERIENBIBEL", "=" * 72])
    for label, value in build_visual_bible(scenes, aspect_ratio):
        lines.append(f"{label}: {value}")

    if profile.negative_prompt:
        lines.extend(["", "GLOBAL NEGATIVE PROMPT", "=" * 72, profile.negative_prompt])

    if profile.output_notes:
        lines.extend(["", "ZIELSYSTEM-HINWEISE", "=" * 72])
        for note in profile.output_notes:
            lines.append(f"- {_format_profile_text(note, scene_count=scene_count, aspect_ratio=aspect_ratio)}")

    lines.extend(["", "STORYBOARD-SZENEN", "=" * 72, ""])
    for scene in scenes:
        lines.append(f"[{scene.index:02d}] {scene.title}")
        lines.append(f"Dateiname: scene_{scene.index:02d}.png")
        lines.append(f"Schritte: {scene.start_step}-{scene.end_step}")
        lines.append(f"Zusammenfassung: {scene.summary}")
        if profile.is_diffusion:
            lines.append(f"{profile.scene_prefix or 'POSITIVE PROMPT'}:")
            lines.append(_stable_diffusion_positive(scene, profile))
            if profile.negative_prompt:
                lines.append("NEGATIVE PROMPT:")
                lines.append(profile.negative_prompt)
        else:
            lines.append("BILDGENERIERUNGS-AUFTRAG:")
            if profile.scene_prefix:
                lines.append(profile.scene_prefix)
            lines.append(scene.prompt)
            if profile.scene_suffix:
                lines.append(profile.scene_suffix)
        lines.append("")
    return "\n".join(lines).strip() + "\n"
