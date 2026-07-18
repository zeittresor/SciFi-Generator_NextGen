from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json


@dataclass(frozen=True)
class PromptProfile:
    profile_id: str
    name: str
    mode: str
    header_title: str
    instruction_intro: str
    instruction_rules: tuple[str, ...]
    scene_prefix: str
    scene_suffix: str
    negative_prompt: str
    output_notes: tuple[str, ...]
    package_header_title: str
    package_instruction_intro: str
    package_instruction_rules: tuple[str, ...]
    package_output_notes: tuple[str, ...]
    source: Path

    @property
    def is_diffusion(self) -> bool:
        return self.mode == "diffusion"

    @property
    def is_conversational(self) -> bool:
        return self.mode == "conversational"


class PromptProfileManager:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.profiles: dict[str, PromptProfile] = {}
        self.errors: list[str] = []

    def load(self) -> None:
        self.profiles.clear()
        self.errors.clear()
        if not self.directory.is_dir():
            self.errors.append(f"Prompt-Profilordner fehlt: {self.directory}")
            return
        for path in sorted(self.directory.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                profile = self._parse_profile(payload, path)
            except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError, KeyError) as exc:
                self.errors.append(f"{path.name}: {exc}")
                continue
            if profile.name in self.profiles:
                self.errors.append(f"{path.name}: Profilname doppelt: {profile.name}")
                continue
            self.profiles[profile.name] = profile

    @staticmethod
    def _parse_profile(payload: dict, path: Path) -> PromptProfile:
        if not isinstance(payload, dict):
            raise TypeError("Wurzel muss ein JSON-Objekt sein")
        profile_id = str(payload["id"]).strip()
        name = str(payload["name"]).strip()
        mode = str(payload.get("mode", "conversational")).strip().lower()
        if mode not in {"conversational", "diffusion", "generic"}:
            raise ValueError(f"Unbekannter Modus: {mode}")
        if not profile_id or not name:
            raise ValueError("id und name dürfen nicht leer sein")
        rules = payload.get("instruction_rules", [])
        notes = payload.get("output_notes", [])
        package_rules = payload.get("package_instruction_rules", [])
        package_notes = payload.get("package_output_notes", [])
        if not isinstance(rules, list) or not all(isinstance(item, str) for item in rules):
            raise TypeError("instruction_rules muss eine Textliste sein")
        if not isinstance(notes, list) or not all(isinstance(item, str) for item in notes):
            raise TypeError("output_notes muss eine Textliste sein")
        if not isinstance(package_rules, list) or not all(isinstance(item, str) for item in package_rules):
            raise TypeError("package_instruction_rules muss eine Textliste sein")
        if not isinstance(package_notes, list) or not all(isinstance(item, str) for item in package_notes):
            raise TypeError("package_output_notes muss eine Textliste sein")
        return PromptProfile(
            profile_id=profile_id,
            name=name,
            mode=mode,
            header_title=str(payload.get("header_title", "AUFGABE FÜR DIE BILDSYNTHESE")).strip(),
            instruction_intro=str(payload.get("instruction_intro", "")).strip(),
            instruction_rules=tuple(item.strip() for item in rules if item.strip()),
            scene_prefix=str(payload.get("scene_prefix", "")).strip(),
            scene_suffix=str(payload.get("scene_suffix", "")).strip(),
            negative_prompt=str(payload.get("negative_prompt", "")).strip(),
            output_notes=tuple(item.strip() for item in notes if item.strip()),
            package_header_title=str(
                payload.get("package_header_title", "GESAMTAUFTRAG FÜR EINE ILLUSTRIERTE AUDIOGESCHICHTE")
            ).strip(),
            package_instruction_intro=str(payload.get("package_instruction_intro", "")).strip(),
            package_instruction_rules=tuple(item.strip() for item in package_rules if item.strip()),
            package_output_notes=tuple(item.strip() for item in package_notes if item.strip()),
            source=path,
        )

    def names(self) -> list[str]:
        return list(self.profiles.keys())

    def get(self, name: str) -> PromptProfile | None:
        return self.profiles.get(name)
