from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable
import json
import random

from story_continuity import ContinuityPlan, StoryContinuity

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
    continuity_jump: int = 0
    continuity_hook: str = ""
    continuity_outcome: str = ""
    continuity_open_hooks: int = 0
    continuity_ship_min: int = 100
    continuity_note: str = ""

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
        ]
        if self.continuity_jump:
            lines.extend([
                f"Kontinuitaets-Sprung: {self.continuity_jump}",
                f"Aufgegriffener Faden: {self.continuity_hook or 'keiner in diesem Sprung'}",
                f"Zwischenergebnis: {self.continuity_outcome or '-'}",
                f"Offene Handlungsfaeden danach: {self.continuity_open_hooks}",
                f"Schiffszustand Minimum: {self.continuity_ship_min}%",
            ])
        if self.continuity_note:
            lines.append(f"Kontinuitaets-Hinweis: {self.continuity_note}")
        lines.append("")
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
            "RAW STORY (Originalschreibweise)", "=" * 72, self.raw_story, "",
            "DISPLAY/TTS STORY (Legacy-Umlautkonvertierung)", "=" * 72, self.display_story, "",
        ])
        return "\n".join(lines)


class StoryEngineError(RuntimeError):
    pass


class StoryEngine:
    """Sentence-fragment generator with weighted branches and multi-jump continuity.

    Text selection, normal branch routing and continuity use independent RNG streams.
    Supplying an explicit seed keeps the historical deterministic/diagnostic mode and
    does not read or write campaign state unless ``use_continuity=True`` is requested.
    A normal random jump (seed=None) automatically participates in continuity.
    """

    BRANCH_RNG_XOR = 0x5C1F1C0DE
    REPETITIVE_CLAUSE_MARKERS = (
        "die Beobachtung wird zur Sicherheit im Missionslog festgehalten",
        "der Rueckweg bleibt dabei jederzeit offen",
        "die Sensoren bestaetigen diese Einordnung",
        "die Kontrollmessung liefert vergleichbare Werte",
        "alle kritischen Werte bleiben unter Beobachtung",
    )

    def __init__(self, vars_dir: Path, sequence_file: Path, continuity_path: Path | None = None):
        self.vars_dir = Path(vars_dir)
        self.sequence_file = Path(sequence_file)
        self.sequence = self._load_sequence()
        self.continuity = StoryContinuity(
            Path(continuity_path) if continuity_path is not None
            else self.sequence_file.resolve().parent / "story_state.json"
        )

    def reset_continuity(self) -> None:
        self.continuity.reset()

    def continuity_state(self) -> dict:
        return self.continuity.load()

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
    def _choice_weight(choice: dict, multiplier: float = 1.0) -> float:
        try:
            weight = float(choice.get("weight", 1.0))
        except (TypeError, ValueError):
            weight = 1.0
        return max(0.0, weight * max(0.0, multiplier))

    @classmethod
    def _weighted_choice(cls, rng: random.Random, choices: list[dict], multipliers: dict[str, float] | None = None) -> dict:
        weighted: list[tuple[dict, float]] = []
        total = 0.0
        multipliers = multipliers or {}
        for choice in choices:
            choice_id = str(choice.get("id") or "")
            weight = cls._choice_weight(choice, multipliers.get(choice_id, 1.0))
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
        branch_biases: dict[str, dict[str, float]] | None = None,
    ) -> list[dict]:
        flattened: list[dict] = []
        branch_biases = branch_biases or {}
        for step in steps:
            if str(step.get("kind", "pick")) != "branch":
                flattened.append(step)
                continue
            branch_id = str(step.get("id") or step.get("save_as") or f"branch_{len(decisions)+1}")
            choices = step.get("choices", [])
            multipliers = branch_biases.get(branch_id, {})
            choice = self._weighted_choice(branch_rng, choices, multipliers)
            choice_id = str(choice.get("id") or f"choice_{len(decisions)+1}")
            weight = self._choice_weight(choice, multipliers.get(choice_id, 1.0))
            decisions.append(BranchDecision(
                index=len(decisions) + 1,
                branch_id=branch_id,
                label=str(step.get("label") or "Story-Zweig"),
                choice_id=choice_id,
                choice_label=str(choice.get("label") or choice_id or "Unbenannt"),
                weight=weight,
            ))
            flattened.extend(self._expand_plan(choice["steps"], branch_rng, decisions, branch_biases))
        return flattened

    @staticmethod
    def _count_narrative_steps(steps: list[dict]) -> int:
        total = 0
        for step in steps:
            if str(step.get("kind", "pick")) in {"pick", "value"}:
                total += max(1, int(step.get("repeat", 1)))
        return total

    def expanded_step_count(self) -> int:
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

    def enumerate_branch_routes(self) -> list[list[str]]:
        def combine(steps: list[dict]) -> list[list[str]]:
            routes: list[list[str]] = [[]]
            for step in steps:
                if str(step.get("kind", "pick")) != "branch":
                    continue
                branch_routes: list[list[str]] = []
                for choice in step.get("choices", []):
                    label = str(choice.get("label") or choice.get("id") or "Unbenannt")
                    nested = combine(choice.get("steps", [])) or [[]]
                    branch_routes.extend([[label, *tail] for tail in nested])
                if not branch_routes:
                    branch_routes = [[]]
                routes = [left + right for left in routes for right in branch_routes]
            return routes
        return combine(self.sequence)

    def _enumerate_source_paths(self, steps: list[dict]) -> list[list[str]]:
        paths: list[list[str]] = [[]]
        for step in steps:
            kind = str(step.get("kind", "pick"))
            if kind == "pick":
                token = str(step.get("file", ""))
                paths = [path + [token] for path in paths]
            elif kind == "value":
                token = f"<value:{step.get('name', '')}>"
                paths = [path + [token] for path in paths]
            elif kind == "branch":
                alternatives: list[list[str]] = []
                for choice in step.get("choices", []):
                    alternatives.extend(self._enumerate_source_paths(choice.get("steps", [])))
                paths = [left + right for left in paths for right in alternatives]
        return paths

    def validate_terminal_invariant(self) -> list[str]:
        expected = [
            "mission_free_space.ini", "mission_end_status.ini",
            "ship_liftoff_jumpready.ini", "mission_jump_prompt.ini",
        ]
        errors: list[str] = []
        paths = self._enumerate_source_paths(self.sequence)
        if not paths:
            return ["Die Sequenz besitzt keinen erzaehlbaren Pfad."]
        for index, path in enumerate(paths, start=1):
            if path[-len(expected):] != expected:
                errors.append(f"Pfad {index} endet mit {path[-len(expected):]!r} statt {expected!r}")
        return errors

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
        # Continuity fragments are runtime-injected and therefore not present in sequence JSON.
        for filename in StoryContinuity.RETURN_FILES.values():
            if not (self.vars_dir / filename).is_file():
                missing.append(filename)
        for filename in (
            "continuity_response_investigate.ini", "continuity_response_cautious.ini", "continuity_response_defer.ini",
            "continuity_outcome_resolved.ini", "continuity_outcome_deepens.ini", "continuity_outcome_false_lead.ini",
            "continuity_outcome_watchlist.ini", "continuity_outcome_deferred.ini",
        ):
            if not (self.vars_dir / filename).is_file():
                missing.append(filename)
        return sorted(set(missing))

    @staticmethod
    def _join_fragment(raw: str, suffix: str) -> str:
        base = raw.strip()
        tail = suffix
        if tail.startswith(".") and base.endswith((".", "!", "?")):
            tail = tail[1:]
        if tail.startswith(",") and base.endswith((",", ";", ":")):
            tail = tail[1:]
        return base + tail

    @staticmethod
    def _inject_continuity_steps(plan: list[dict], continuity_plan: ContinuityPlan | None) -> list[dict]:
        if continuity_plan is None:
            return plan
        insertion = len(plan)
        # The first route-specific target scene occurs immediately after the common
        # system analysis. Insert the callback there so it feels like a side plot,
        # not a replacement for the newly generated mission.
        for index, step in enumerate(plan):
            if str(step.get("kind", "")) == "scene" and str(step.get("id", "")) == "target":
                insertion = index
                break
        return [*plan[:insertion], *continuity_plan.steps, *plan[insertion:]]

    def generate(
        self,
        seed: int | None = None,
        *,
        legacy_umlauts: bool = True,
        ignore_blank_lines: bool = True,
        progress: Callable[[int, int, str], None] | None = None,
        use_continuity: bool | None = None,
    ) -> GenerationResult:
        explicit_seed = seed is not None
        if seed is None:
            seed = random.SystemRandom().randrange(0, 2**63)
        if use_continuity is None:
            use_continuity = not explicit_seed

        text_rng = random.Random(seed)
        branch_rng = random.Random(seed ^ self.BRANCH_RNG_XOR)
        saved: dict[str, str] = {}
        selections: list[Selection] = []
        used_repetitive_markers: set[str] = set()
        used_raw_by_source: dict[str, set[str]] = {}
        fragments: list[str] = []
        decisions: list[BranchDecision] = []

        continuity_session = self.continuity.begin_jump(seed) if use_continuity else None
        continuity_plan = self.continuity.plan_callback(continuity_session) if continuity_session else None
        branch_biases: dict[str, dict[str, float]] = {}
        if continuity_session:
            branch_biases["mission_route"] = self.continuity.route_weight_biases(continuity_session)

        plan = self._expand_plan(self.sequence, branch_rng, decisions, branch_biases)
        plan = self._inject_continuity_steps(plan, continuity_plan)
        if continuity_plan:
            decisions.append(BranchDecision(
                index=len(decisions) + 1,
                branch_id="continuity_hook",
                label="Wiederkehrender Handlungsfaden",
                choice_id=f"{continuity_plan.kind}:{continuity_plan.hook_id}",
                choice_label=continuity_plan.kind_label,
                weight=100.0,
            ))
            decisions.append(BranchDecision(
                index=len(decisions) + 1,
                branch_id="continuity_response",
                label="Reaktion auf den wiederkehrenden Handlungsfaden",
                choice_id=continuity_plan.response_id,
                choice_label=continuity_plan.response_label,
                weight=continuity_plan.response_weight,
            ))
            decisions.append(BranchDecision(
                index=len(decisions) + 1,
                branch_id="continuity_outcome",
                label="Folge des wiederkehrenden Handlungsfadens",
                choice_id=continuity_plan.outcome_id,
                choice_label=continuity_plan.outcome_label,
                weight=continuity_plan.outcome_weight,
            ))

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
                    exclude_saved = step.get("exclude_saved", [])
                    if isinstance(exclude_saved, str):
                        exclude_saved = [exclude_saved]
                    excluded_values = {
                        saved[name].strip().casefold() for name in exclude_saved if name in saved
                    }
                    if excluded_values:
                        filtered = [choice for choice in choices if choice[1].strip().casefold() not in excluded_values]
                        if filtered:
                            choices = filtered

                    if step.get("avoid_repeat"):
                        previous = used_raw_by_source.get(filename, set())
                        if previous:
                            fresh = [candidate for candidate in choices if candidate[1].strip().casefold() not in previous]
                            if fresh:
                                choices = fresh

                    if used_repetitive_markers:
                        def has_used_marker(candidate: tuple[int, str]) -> bool:
                            folded = candidate[1].casefold()
                            return any(marker.casefold() in folded for marker in used_repetitive_markers)
                        varied = [candidate for candidate in choices if not has_used_marker(candidate)]
                        if varied:
                            choices = varied

                    line_number, raw = text_rng.choice(choices)
                    used_raw_by_source.setdefault(filename, set()).add(raw.strip().casefold())
                    raw_folded = raw.casefold()
                    for marker in self.REPETITIVE_CLAUSE_MARKERS:
                        if marker.casefold() in raw_folded:
                            used_repetitive_markers.add(marker)
                    save_as = step.get("save_as")
                    if save_as:
                        saved[str(save_as)] = raw.strip()
                    fragment = self._join_fragment(raw, suffix)
                    fragments.append(fragment)
                    rendered_fragment = self.legacy_umlaut_conversion(fragment) if legacy_umlauts else fragment
                    selections.append(Selection(
                        current, kind, label, f"data/vars/{filename}", line_number, raw, rendered_fragment,
                        scene_id, scene_title, visual_hint,
                    ))
                    progress_name = filename
                elif kind == "value":
                    name = str(step.get("name", ""))
                    if name not in saved:
                        raise StoryEngineError(f"Gespeicherter Wert ist nicht verfügbar: {name}")
                    raw = saved[name]
                    fragment = self._join_fragment(raw, suffix)
                    fragments.append(fragment)
                    rendered_fragment = self.legacy_umlaut_conversion(fragment) if legacy_umlauts else fragment
                    selections.append(Selection(
                        current, kind, label, f"<gespeichert:{name}>", None, raw, rendered_fragment,
                        scene_id, scene_title, visual_hint,
                    ))
                    progress_name = name
                else:
                    raise StoryEngineError(f"Unbekannter Schritttyp: {kind}")

                if progress:
                    progress(current, total, progress_name)

        raw_story = "".join(fragments).strip()
        display_story = self.legacy_umlaut_conversion(raw_story) if legacy_umlauts else raw_story

        continuity_state: dict | None = None
        continuity_note = ""
        if continuity_session:
            try:
                continuity_state = self.continuity.finish_jump(continuity_session, decisions, continuity_plan)
            except OSError as exc:
                continuity_note = f"Story-Gedaechtnis konnte nicht gespeichert werden: {exc}"

        ship_min = 100
        open_hooks = 0
        jump_index = 0
        if continuity_state:
            jump_index = int(continuity_state.get("jump_index", 0))
            open_hooks = len(continuity_state.get("open_hooks", []))
            ship = continuity_state.get("ship_state", {})
            ship_min = min((int(value) for value in ship.values()), default=100)
        elif continuity_session:
            jump_index = continuity_session.jump_index

        return GenerationResult(
            seed=seed,
            created_at=datetime.now().astimezone(),
            raw_story=raw_story,
            display_story=display_story,
            selections=tuple(selections),
            branches=tuple(decisions),
            continuity_jump=jump_index,
            continuity_hook=continuity_plan.hook_id if continuity_plan else "",
            continuity_outcome=continuity_plan.outcome_id if continuity_plan else "",
            continuity_open_hooks=open_hooks,
            continuity_ship_min=ship_min,
            continuity_note=continuity_note,
        )

    def random_line(self, filename: str, seed: int | None = None, *, ignore_blank_lines: bool = True) -> str:
        path = self.vars_dir / filename
        if not path.is_file():
            raise StoryEngineError(f"Satzteil-Datei fehlt: {path}")
        rng = random.Random(seed) if seed is not None else random.SystemRandom()
        return rng.choice(self._read_lines(path, ignore_blank_lines))[1]
