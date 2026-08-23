from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable
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
    scene_id: str = ""
    scene_title: str = ""
    visual_hint: str = ""


@dataclass(frozen=True)
class BranchDecision:
    index: int
    branch_id: str
    label: str
    choice_id: str
    choice_label: str
    weight: float


@dataclass(frozen=True)
class GenerationResult:
    seed: int
    created_at: datetime
    raw_story: str
    display_story: str
    selections: tuple[Selection, ...]
    branches: tuple[BranchDecision, ...] = ()

    @property
    def branch_path(self) -> str:
        return " > ".join(item.choice_label for item in self.branches)

    def build_log(self, app_version: str = APP_VERSION) -> str:
        lines = [
            "SCIFI-GENERATOR — GENERATION LOG",
            f"App-Version: {app_version}",
            f"Erzeugt: {self.created_at.astimezone().isoformat(timespec='seconds')}",
            f"Seed: {self.seed}",
            f"Auswahlschritte: {len(self.selections)}",
            f"Story-Zweig: {self.branch_path or 'linear / legacy'}",
            "",
        ]
        if self.branches:
            lines.extend(["STORY-ZWEIGE", "=" * 72])
            for item in self.branches:
                lines.append(
                    f"[{item.index:02d}] {item.label}: {item.choice_label} "
                    f"(ID={item.choice_id}, Gewicht={item.weight:g})"
                )
            lines.append("")
        lines.extend(["AUSGEWÄHLTE SATZTEILE", "=" * 72])
        for item in self.selections:
            lines.append(f"[{item.index:03d}] {item.label}")
            lines.append(f"Quelle: {item.source}")
            if item.scene_title:
                lines.append(f"Szene: {item.scene_title} ({item.scene_id})")
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
    """Sentence-fragment story generator with optional weighted story branches.

    Sequence format v2 adds two non-narrated step types:
      * scene: changes storyboard metadata for following picks/values.
      * branch: chooses one weighted choice and recursively executes its steps.

    Branch choices use a RNG stream derived from the story seed but independent
    from sentence selection. This keeps branch routing deterministic without
    coupling it to the number of lines inside any particular .ini file.
    """

    BRANCH_RNG_XOR = 0x5C1F1C0DE

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
        self._validate_step_structure(steps)
        return steps

    def _validate_step_structure(self, steps: list[dict]) -> None:
        for step in steps:
            if not isinstance(step, dict):
                raise StoryEngineError("Ein Sequenzschritt ist kein Objekt.")
            kind = str(step.get("kind", "pick"))
            if kind == "branch":
                choices = step.get("choices")
                if not isinstance(choices, list) or not choices:
                    raise StoryEngineError("Ein Story-Zweig enthält keine choices.")
                for choice in choices:
                    if not isinstance(choice, dict) or not isinstance(choice.get("steps"), list):
                        raise StoryEngineError("Ein Story-Zweig enthält eine ungültige choice.")
                    self._validate_step_structure(choice["steps"])
            elif kind not in {"pick", "value", "scene"}:
                raise StoryEngineError(f"Unbekannter Schritttyp in Sequenz: {kind}")

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

    @staticmethod
    def _weighted_choice(rng: random.Random, choices: list[dict]) -> dict:
        weighted: list[tuple[dict, float]] = []
        total = 0.0
        for choice in choices:
            try:
                weight = float(choice.get("weight", 1.0))
            except (TypeError, ValueError):
                weight = 1.0
            if weight <= 0:
                continue
            total += weight
            weighted.append((choice, weight))
        if not weighted or total <= 0:
            raise StoryEngineError("Ein Story-Zweig besitzt keine positive Gewichtung.")
        needle = rng.random() * total
        cursor = 0.0
        for choice, weight in weighted:
            cursor += weight
            if needle < cursor:
                return choice
        return weighted[-1][0]

    def _expand_plan(
        self,
        steps: list[dict],
        branch_rng: random.Random,
        decisions: list[BranchDecision],
    ) -> list[dict]:
        flattened: list[dict] = []
        for step in steps:
            if str(step.get("kind", "pick")) != "branch":
                flattened.append(step)
                continue
            choices = step.get("choices", [])
            choice = self._weighted_choice(branch_rng, choices)
            try:
                weight = float(choice.get("weight", 1.0))
            except (TypeError, ValueError):
                weight = 1.0
            decisions.append(
                BranchDecision(
                    index=len(decisions) + 1,
                    branch_id=str(step.get("id") or step.get("save_as") or f"branch_{len(decisions)+1}"),
                    label=str(step.get("label") or "Story-Zweig"),
                    choice_id=str(choice.get("id") or f"choice_{len(decisions)+1}"),
                    choice_label=str(choice.get("label") or choice.get("id") or "Unbenannt"),
                    weight=weight,
                )
            )
            flattened.extend(self._expand_plan(choice["steps"], branch_rng, decisions))
        return flattened

    @staticmethod
    def _count_narrative_steps(steps: list[dict]) -> int:
        total = 0
        for step in steps:
            if str(step.get("kind", "pick")) in {"pick", "value"}:
                total += max(1, int(step.get("repeat", 1)))
        return total

    def expanded_step_count(self) -> int:
        """Return the longest possible narrative path for diagnostics/progress estimates."""
        def count(steps: list[dict]) -> int:
            total = 0
            for step in steps:
                kind = str(step.get("kind", "pick"))
                if kind in {"pick", "value"}:
                    total += max(1, int(step.get("repeat", 1)))
                elif kind == "branch":
                    choices = step.get("choices", [])
                    total += max((count(choice.get("steps", [])) for choice in choices), default=0)
            return total
        return count(self.sequence)

    def validate_sources(self) -> list[str]:
        missing: list[str] = []

        def visit(steps: list[dict]) -> None:
            for step in steps:
                kind = str(step.get("kind", "pick"))
                if kind == "pick":
                    filename = str(step.get("file", ""))
                    if not filename or not (self.vars_dir / filename).is_file():
                        missing.append(filename or "<Dateiname fehlt>")
                elif kind == "branch":
                    for choice in step.get("choices", []):
                        visit(choice.get("steps", []))

        visit(self.sequence)
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
        text_rng = random.Random(seed)
        branch_rng = random.Random(seed ^ self.BRANCH_RNG_XOR)
        saved: dict[str, str] = {}
        selections: list[Selection] = []
        fragments: list[str] = []
        decisions: list[BranchDecision] = []
        plan = self._expand_plan(self.sequence, branch_rng, decisions)
        total = self._count_narrative_steps(plan)
        current = 0
        scene_id = ""
        scene_title = ""
        visual_hint = ""

        for step in plan:
            kind = str(step.get("kind", "pick"))
            if kind == "scene":
                scene_id = str(step.get("id") or "")
                scene_title = str(step.get("title") or scene_id or "Szene")
                visual_hint = str(step.get("visual_hint") or "")
                continue

            repeat = max(1, int(step.get("repeat", 1)))
            for repeat_index in range(repeat):
                current += 1
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
                    line_number, raw = text_rng.choice(choices)
                    save_as = step.get("save_as")
                    if save_as:
                        saved[str(save_as)] = raw
                    fragment = raw + suffix
                    fragments.append(fragment)
                    rendered_fragment = self.legacy_umlaut_conversion(fragment) if legacy_umlauts else fragment
                    selections.append(
                        Selection(
                            current, kind, label, f"data/vars/{filename}", line_number, raw, rendered_fragment,
                            scene_id, scene_title, visual_hint,
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
                        Selection(
                            current, kind, label, f"<gespeichert:{name}>", None, raw, rendered_fragment,
                            scene_id, scene_title, visual_hint,
                        )
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
            branches=tuple(decisions),
        )

    def random_line(self, filename: str, seed: int | None = None, *, ignore_blank_lines: bool = True) -> str:
        path = self.vars_dir / filename
        if not path.is_file():
            raise StoryEngineError(f"Satzteil-Datei fehlt: {path}")
        rng = random.Random(seed) if seed is not None else random.SystemRandom()
        return rng.choice(self._read_lines(path, ignore_blank_lines))[1]
