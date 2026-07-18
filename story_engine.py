from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable
import json
import random

VERSION_FILE = Path(__file__).resolve().with_name("version.txt")
try:
    APP_VERSION = VERSION_FILE.read_text(encoding="utf-8").strip()
except OSError as exc:
    raise RuntimeError(f"Version file could not be read: {VERSION_FILE}") from exc
if not APP_VERSION:
    raise RuntimeError(f"Version file is empty: {VERSION_FILE}")


@dataclass(frozen=True)
class Selection:
    index: int
    kind: str
    label: str
    source: str
    line_number: int | None
    raw_text: str
    rendered_text: str = ""


@dataclass(frozen=True)
class GenerationResult:
    seed: int
    created_at: datetime
    raw_story: str
    display_story: str
    selections: tuple[Selection, ...]

    def build_log(self, app_version: str = APP_VERSION) -> str:
        lines = [
            "SCIFI-GENERATOR — GENERATION LOG",
            f"App-Version: {app_version}",
            f"Erzeugt: {self.created_at.astimezone().isoformat(timespec='seconds')}",
            f"Seed: {self.seed}",
            f"Auswahlschritte: {len(self.selections)}",
            "",
            "AUSGEWÄHLTE SATZTEILE",
            "=" * 72,
        ]
        for item in self.selections:
            lines.append(f"[{item.index:03d}] {item.label}")
            lines.append(f"Quelle: {item.source}")
            if item.line_number is not None:
                lines.append(f"Zeile: {item.line_number}")
            lines.append(f"Text: {item.raw_text}")
            if item.rendered_text and item.rendered_text != item.raw_text:
                lines.append(f"Ausgabe: {item.rendered_text}")
            lines.append("")
        lines.extend([
            "RAW STORY (Originalschreibweise)",
            "=" * 72,
            self.raw_story,
            "",
            "DISPLAY/TTS STORY (Legacy-Umlautkonvertierung)",
            "=" * 72,
            self.display_story,
            "",
        ])
        return "\n".join(lines)


class StoryEngineError(RuntimeError):
    pass


class StoryEngine:
    def __init__(self, vars_dir: Path, sequence_file: Path):
        self.vars_dir = Path(vars_dir)
        self.sequence_file = Path(sequence_file)
        self.sequence = self._load_sequence()

    def _load_sequence(self) -> list[dict]:
        try:
            payload = json.loads(self.sequence_file.read_text(encoding="utf-8"))
            steps = payload["steps"]
        except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise StoryEngineError(f"Reihenfolge konnte nicht geladen werden: {exc}") from exc
        if not isinstance(steps, list) or not steps:
            raise StoryEngineError("Die Reihenfolge enthält keine Schritte.")
        return steps

    @staticmethod
    def legacy_umlaut_conversion(text: str) -> str:
        # Reproduces the old global VB.NET conversion intentionally. It may turn
        # words such as 'aktuell' into 'aktüll'; this is part of legacy behavior.
        for old, new in (
            ("ae", "ä"), ("ue", "ü"), ("oe", "ö"),
            ("Ae", "Ä"), ("Ue", "Ü"), ("Oe", "Ö"),
        ):
            text = text.replace(old, new)
        return text

    @staticmethod
    def _read_lines(path: Path, ignore_blank_lines: bool) -> list[tuple[int, str]]:
        data = path.read_bytes()
        decoded = None
        for encoding in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                decoded = data.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if decoded is None:
            raise StoryEngineError(f"Datei kann nicht dekodiert werden: {path}")
        lines = list(enumerate(decoded.splitlines(), start=1))
        if ignore_blank_lines:
            lines = [(number, line) for number, line in lines if line.strip()]
        if not lines:
            raise StoryEngineError(f"Keine auswählbaren Zeilen in {path.name}")
        return lines

    def expanded_step_count(self) -> int:
        return sum(max(1, int(step.get("repeat", 1))) for step in self.sequence)

    def validate_sources(self) -> list[str]:
        missing: list[str] = []
        for step in self.sequence:
            if step.get("kind") == "pick":
                filename = str(step.get("file", ""))
                if not filename or not (self.vars_dir / filename).is_file():
                    missing.append(filename or "<Dateiname fehlt>")
        return sorted(set(missing))

    def generate(
        self,
        seed: int | None = None,
        *,
        legacy_umlauts: bool = True,
        ignore_blank_lines: bool = True,
        progress: Callable[[int, int, str], None] | None = None,
    ) -> GenerationResult:
        if seed is None:
            seed = random.SystemRandom().randrange(0, 2**63)
        rng = random.Random(seed)
        saved: dict[str, str] = {}
        selections: list[Selection] = []
        fragments: list[str] = []
        total = self.expanded_step_count()
        current = 0

        for step in self.sequence:
            repeat = max(1, int(step.get("repeat", 1)))
            for repeat_index in range(repeat):
                current += 1
                kind = str(step.get("kind", "pick"))
                suffix = str(step.get("suffix", ""))
                label = str(step.get("label") or step.get("file") or step.get("name") or kind)
                if repeat > 1:
                    label = f"{label} {repeat_index + 1}/{repeat}"

                if kind == "pick":
                    filename = str(step.get("file", ""))
                    source_path = self.vars_dir / filename
                    if not source_path.is_file():
                        raise StoryEngineError(f"Satzteil-Datei fehlt: {source_path}")
                    choices = self._read_lines(source_path, ignore_blank_lines)
                    line_number, raw = rng.choice(choices)
                    save_as = step.get("save_as")
                    if save_as:
                        saved[str(save_as)] = raw
                    fragment = raw + suffix
                    fragments.append(fragment)
                    rendered_fragment = self.legacy_umlaut_conversion(fragment) if legacy_umlauts else fragment
                    selections.append(
                        Selection(
                            current, kind, label, f"data/vars/{filename}", line_number, raw, rendered_fragment
                        )
                    )
                    progress_name = filename
                elif kind == "value":
                    name = str(step.get("name", ""))
                    if name not in saved:
                        raise StoryEngineError(f"Gespeicherter Wert ist nicht verfügbar: {name}")
                    raw = saved[name]
                    fragment = raw + suffix
                    fragments.append(fragment)
                    rendered_fragment = self.legacy_umlaut_conversion(fragment) if legacy_umlauts else fragment
                    selections.append(
                        Selection(current, kind, label, f"<gespeichert:{name}>", None, raw, rendered_fragment)
                    )
                    progress_name = name
                else:
                    raise StoryEngineError(f"Unbekannter Schritttyp: {kind}")

                if progress:
                    progress(current, total, progress_name)

        raw_story = "".join(fragments).strip()
        display_story = self.legacy_umlaut_conversion(raw_story) if legacy_umlauts else raw_story
        return GenerationResult(
            seed=seed,
            created_at=datetime.now().astimezone(),
            raw_story=raw_story,
            display_story=display_story,
            selections=tuple(selections),
        )

    def random_line(self, filename: str, seed: int | None = None, *, ignore_blank_lines: bool = True) -> str:
        path = self.vars_dir / filename
        if not path.is_file():
            raise StoryEngineError(f"Satzteil-Datei fehlt: {path}")
        rng = random.Random(seed) if seed is not None else random.SystemRandom()
        return rng.choice(self._read_lines(path, ignore_blank_lines))[1]
