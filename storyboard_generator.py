from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
import re

from story_engine import GenerationResult, Selection, StoryEngine


@dataclass(frozen=True)
class StoryboardScene:
    index: int
    title: str
    summary: str
    prompt: str
    start_step: int
    end_step: int


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


def _selection_text(items: Iterable[Selection]) -> str:
    parts = [StoryEngine.legacy_umlaut_conversion(item.raw_text) for item in items if item.raw_text.strip()]
    return _shorten(" ".join(parts))


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
        summary = _selection_text(merged_items)
        prompt = _scene_prompt(new_index, merged_title, summary, merged_visual, ship_context)
        scenes.append(
            StoryboardScene(
                index=new_index,
                title=merged_title,
                summary=summary,
                prompt=prompt,
                start_step=merged_items[0].index,
                end_step=merged_items[-1].index,
            )
        )
    return scenes


def render_storyboard_text(scenes: list[StoryboardScene], *, source: str = "Lokal", model: str = "") -> str:
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
