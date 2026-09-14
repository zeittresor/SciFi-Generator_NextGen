from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
import json
import os
import random
import tempfile


SCHEMA_VERSION = 1
CONTINUITY_RNG_XOR = 0xC0171A17E
HOOK_RNG_XOR = 0xA11CE5EED
MAX_OPEN_HOOKS = 8
MAX_HISTORY = 40


@dataclass(frozen=True)
class ContinuitySession:
    state: dict
    jump_index: int
    seed: int


@dataclass(frozen=True)
class ContinuityPlan:
    hook_id: str
    kind: str
    kind_label: str
    origin: str
    created_jump: int
    response_id: str
    response_label: str
    response_weight: float
    outcome_id: str
    outcome_label: str
    outcome_weight: float
    steps: tuple[dict, ...]


class StoryContinuity:
    """Small persistent campaign memory for otherwise self-contained missions.

    The memory intentionally stores abstract story facts instead of generated prose.
    That keeps it compact, forward-compatible and useful for deterministic branch
    weighting. Explicit diagnostic seeds can bypass this class entirely in the
    story engine, while normal random jumps form a lightweight ongoing campaign.
    """

    RETURN_FILES = {
        "signal": "continuity_signal_return.ini",
        "pursuit": "continuity_pursuit_return.ini",
        "anomaly": "continuity_anomaly_return.ini",
        "contact": "continuity_contact_return.ini",
        "rescue": "continuity_rescue_return.ini",
        "ship": "continuity_ship_return.ini",
    }

    KIND_LABELS = {
        "signal": "Frueheres Signal meldet sich erneut",
        "pursuit": "Frueherer Verfolger oder Kontakt taucht wieder auf",
        "anomaly": "Bekannte Anomalie zeigt ein neues Echo",
        "contact": "Spur einer frueheren Fremdbegegnung",
        "rescue": "Rueckwirkung einer frueheren Rettungsmission",
        "ship": "Technische Nachwirkung eines frueheren Defekts",
    }

    RESPONSE_CHOICES = (
        ("investigate", "Spur aktiv untersuchen", 46.0),
        ("cautious", "Passiv beobachten und Abstand halten", 34.0),
        ("defer", "Vorerst markieren und spaeter weiterverfolgen", 20.0),
    )

    INVESTIGATE_OUTCOMES = (
        ("resolved", "Der alte Handlungsfaden kann vorerst geschlossen werden", 32.0),
        ("deepens", "Die Spur wird konkreter und fuehrt noch tiefer", 48.0),
        ("false_lead", "Die Verbindung erweist sich als falsche Faehrte", 20.0),
    )

    def __init__(self, path: Path):
        self.path = Path(path)

    @staticmethod
    def default_state() -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "jump_index": 0,
            "next_hook_id": 1,
            "recent_routes": [],
            "open_hooks": [],
            "ship_state": {
                "integrity": 100,
                "navigation": 100,
                "sensors": 100,
                "propulsion": 100,
                "power": 100,
            },
            "reputation": 0,
            "unknown_attention": 0,
            "history": [],
        }

    def load(self) -> dict:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return self.default_state()
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
            # A damaged memory must never stop story generation. Keep the broken
            # file untouched and continue from a clean in-memory state.
            return self.default_state()
        return self._normalise(payload)

    def _normalise(self, payload: object) -> dict:
        base = self.default_state()
        if not isinstance(payload, dict):
            return base
        base["jump_index"] = max(0, self._int(payload.get("jump_index"), 0))
        base["next_hook_id"] = max(1, self._int(payload.get("next_hook_id"), 1))
        base["reputation"] = self._bounded_int(payload.get("reputation"), -100, 100, 0)
        base["unknown_attention"] = self._bounded_int(payload.get("unknown_attention"), 0, 100, 0)

        recent = payload.get("recent_routes", [])
        if isinstance(recent, list):
            base["recent_routes"] = [str(item) for item in recent if str(item).strip()][-6:]

        ship = payload.get("ship_state", {})
        if isinstance(ship, dict):
            for key in base["ship_state"]:
                base["ship_state"][key] = self._bounded_int(ship.get(key), 0, 100, 100)

        hooks = payload.get("open_hooks", [])
        if isinstance(hooks, list):
            clean_hooks = []
            for item in hooks:
                if not isinstance(item, dict):
                    continue
                kind = str(item.get("kind", ""))
                if kind not in self.RETURN_FILES:
                    continue
                clean_hooks.append({
                    "id": str(item.get("id") or ""),
                    "kind": kind,
                    "origin": str(item.get("origin") or "unknown"),
                    "created_jump": max(0, self._int(item.get("created_jump"), 0)),
                    "due_jump": max(1, self._int(item.get("due_jump"), 1)),
                    "expires_jump": max(2, self._int(item.get("expires_jump"), 12)),
                    "stage": max(1, self._int(item.get("stage"), 1)),
                    "strength": max(0.1, min(3.0, self._float(item.get("strength"), 1.0))),
                    "last_outcome": str(item.get("last_outcome") or "opened"),
                })
            base["open_hooks"] = clean_hooks[-MAX_OPEN_HOOKS:]

        history = payload.get("history", [])
        if isinstance(history, list):
            base["history"] = [item for item in history if isinstance(item, dict)][-MAX_HISTORY:]
        return base

    @staticmethod
    def _int(value: object, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _float(value: object, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @classmethod
    def _bounded_int(cls, value: object, low: int, high: int, default: int) -> int:
        return max(low, min(high, cls._int(value, default)))

    def begin_jump(self, seed: int) -> ContinuitySession:
        state = self.load()
        jump_index = int(state.get("jump_index", 0)) + 1
        # Slow passive recovery. Damage therefore matters for a number of jumps,
        # but cannot accumulate forever from harmless old incidents.
        ship = state["ship_state"]
        for key in ship:
            ship[key] = min(100, int(ship[key]) + 1)
        state["unknown_attention"] = max(0, int(state.get("unknown_attention", 0)) - 1)
        state["open_hooks"] = [
            hook for hook in state.get("open_hooks", [])
            if int(hook.get("expires_jump", jump_index + 1)) >= jump_index
        ]
        return ContinuitySession(state=state, jump_index=jump_index, seed=seed)

    def route_weight_biases(self, session: ContinuitySession) -> dict[str, float]:
        """Return weight multipliers for the top-level mission_route choices."""
        state = session.state
        result = {
            "alien_encounter": 1.0,
            "planet_nature": 1.0,
            "space_only": 1.0,
            "abandoned_site": 1.0,
            "distress_signal": 1.0,
            "ship_malfunction": 1.0,
        }

        recent = list(state.get("recent_routes", []))
        if recent:
            result[recent[-1]] = result.get(recent[-1], 1.0) * 0.58
        if len(recent) >= 2:
            result[recent[-2]] = result.get(recent[-2], 1.0) * 0.82

        ship = state.get("ship_state", {})
        weakest = min((int(value) for value in ship.values()), default=100)
        if weakest < 92:
            result["ship_malfunction"] *= min(1.9, 1.0 + (92 - weakest) / 35.0)

        attention = int(state.get("unknown_attention", 0))
        if attention > 10:
            factor = min(1.55, 1.0 + attention / 140.0)
            result["alien_encounter"] *= factor
            result["space_only"] *= min(1.35, factor)

        reputation = int(state.get("reputation", 0))
        if reputation > 0:
            result["distress_signal"] *= min(1.45, 1.0 + reputation / 120.0)
        elif reputation < 0:
            result["distress_signal"] *= max(0.72, 1.0 + reputation / 180.0)
        return result

    @staticmethod
    def _weighted_tuple(rng: random.Random, items: Iterable[tuple[str, str, float]]) -> tuple[str, str, float]:
        choices = list(items)
        total = sum(max(0.0, item[2]) for item in choices)
        if total <= 0:
            return choices[0]
        needle = rng.random() * total
        cursor = 0.0
        for item in choices:
            cursor += max(0.0, item[2])
            if needle < cursor:
                return item
        return choices[-1]

    def plan_callback(self, session: ContinuitySession) -> ContinuityPlan | None:
        due = [
            hook for hook in session.state.get("open_hooks", [])
            if int(hook.get("due_jump", 1)) <= session.jump_index
        ]
        if not due:
            return None

        rng = random.Random(session.seed ^ CONTINUITY_RNG_XOR ^ (session.jump_index << 11))
        strongest_stage = max(int(hook.get("stage", 1)) for hook in due)
        trigger_chance = min(0.92, 0.58 + 0.08 * max(0, strongest_stage - 1))
        if rng.random() > trigger_chance:
            return None

        weighted = []
        for hook in due:
            age = max(0, session.jump_index - int(hook.get("created_jump", 0)))
            weight = float(hook.get("strength", 1.0)) * (1.0 + min(age, 8) * 0.05)
            weighted.append((str(hook.get("id")), str(hook.get("id")), weight))
        hook_id, _, _ = self._weighted_tuple(rng, weighted)
        hook = next(item for item in due if str(item.get("id")) == hook_id)

        response_id, response_label, response_weight = self._weighted_tuple(rng, self.RESPONSE_CHOICES)
        if response_id == "investigate":
            outcome_id, outcome_label, outcome_weight = self._weighted_tuple(rng, self.INVESTIGATE_OUTCOMES)
        elif response_id == "cautious":
            outcome_id, outcome_label, outcome_weight = "watchlist", "Die Spur bleibt unter Beobachtung", 100.0
        else:
            outcome_id, outcome_label, outcome_weight = "deferred", "Der Handlungsfaden bleibt bewusst offen", 100.0

        kind = str(hook["kind"])
        steps: list[dict] = [
            {
                "kind": "scene",
                "id": "continuity_return",
                "title": self.KIND_LABELS[kind],
                "visual_hint": "Ein klar erkennbarer Rueckbezug auf ein Ereignis aus einer frueheren Mission; gleiche Signatur oder technische Merkmale, aber neue Umgebung.",
            },
            {
                "kind": "pick",
                "file": self.RETURN_FILES[kind],
                "suffix": ". ",
                "label": self.KIND_LABELS[kind],
            },
            {
                "kind": "pick",
                "file": f"continuity_response_{response_id}.ini",
                "suffix": ". ",
                "label": "Reaktion auf wiederkehrenden Handlungsfaden",
            },
            {
                "kind": "pick",
                "file": f"continuity_outcome_{outcome_id}.ini",
                "suffix": ". ",
                "label": "Zwischenergebnis des wiederkehrenden Handlungsfadens",
            },
        ]
        return ContinuityPlan(
            hook_id=str(hook["id"]),
            kind=kind,
            kind_label=self.KIND_LABELS[kind],
            origin=str(hook.get("origin", "unknown")),
            created_jump=int(hook.get("created_jump", 0)),
            response_id=response_id,
            response_label=response_label,
            response_weight=response_weight,
            outcome_id=outcome_id,
            outcome_label=outcome_label,
            outcome_weight=outcome_weight,
            steps=tuple(steps),
        )

    @staticmethod
    def _decision_map(decisions: Iterable[object]) -> tuple[dict[str, str], list[str]]:
        by_branch: dict[str, str] = {}
        all_choice_ids: list[str] = []
        for item in decisions:
            branch_id = str(getattr(item, "branch_id", ""))
            choice_id = str(getattr(item, "choice_id", ""))
            if branch_id:
                by_branch[branch_id] = choice_id
            if choice_id:
                all_choice_ids.append(choice_id)
        return by_branch, all_choice_ids

    def finish_jump(
        self,
        session: ContinuitySession,
        decisions: Iterable[object],
        plan: ContinuityPlan | None,
    ) -> dict:
        state = session.state
        by_branch, all_choices = self._decision_map(decisions)
        rng = random.Random(session.seed ^ HOOK_RNG_XOR ^ (session.jump_index << 7))

        if plan is not None:
            target = next((hook for hook in state["open_hooks"] if str(hook.get("id")) == plan.hook_id), None)
            if target is not None:
                target["last_outcome"] = plan.outcome_id
                if plan.outcome_id in {"resolved", "false_lead"}:
                    state["open_hooks"] = [hook for hook in state["open_hooks"] if hook is not target]
                elif plan.outcome_id == "deepens":
                    target["stage"] = int(target.get("stage", 1)) + 1
                    target["strength"] = min(3.0, float(target.get("strength", 1.0)) + 0.28)
                    target["due_jump"] = session.jump_index + rng.randint(2, 4)
                    target["expires_jump"] = max(int(target.get("expires_jump", 0)), session.jump_index + 10)
                elif plan.outcome_id == "watchlist":
                    target["strength"] = min(3.0, float(target.get("strength", 1.0)) + 0.08)
                    target["due_jump"] = session.jump_index + rng.randint(2, 5)
                else:  # deferred
                    target["strength"] = max(0.2, float(target.get("strength", 1.0)) - 0.08)
                    target["due_jump"] = session.jump_index + rng.randint(3, 6)

        route = by_branch.get("mission_route", "")
        if route:
            recent = list(state.get("recent_routes", []))
            recent.append(route)
            state["recent_routes"] = recent[-6:]

        # Persistent abstract state. These values are deliberately modest: they
        # bias future stories rather than turning the generator into a survival game.
        ship = state["ship_state"]
        if route == "ship_malfunction":
            subsystem = rng.choice(list(ship.keys()))
            ship[subsystem] = max(55, int(ship[subsystem]) - rng.randint(5, 11))
        if "secondary_fault" in all_choices:
            subsystem = rng.choice(list(ship.keys()))
            ship[subsystem] = max(50, int(ship[subsystem]) - rng.randint(3, 7))
        if "external_interference" in all_choices:
            ship["sensors"] = max(55, int(ship["sensors"]) - rng.randint(2, 6))
            ship["navigation"] = max(55, int(ship["navigation"]) - rng.randint(1, 4))

        if route == "distress_signal":
            state["reputation"] = min(100, int(state.get("reputation", 0)) + rng.randint(2, 5))
        if route == "alien_encounter":
            state["unknown_attention"] = min(100, int(state.get("unknown_attention", 0)) + rng.randint(3, 8))
        if "brief_pursuit" in all_choices:
            state["unknown_attention"] = min(100, int(state.get("unknown_attention", 0)) + rng.randint(6, 12))

        kinds_to_open: list[tuple[str, str, float]] = []
        if "delayed_signal" in all_choices or "late_signal" in all_choices or "archive_wakes" in all_choices:
            kinds_to_open.append(("signal", route or "late_signal", 1.25))
        if "brief_pursuit" in all_choices:
            kinds_to_open.append(("pursuit", route or "brief_pursuit", 1.45))
        if "navigation_anomaly" in all_choices:
            kinds_to_open.append(("anomaly", route or "navigation_anomaly", 1.25))

        # Main-route hooks make continuity possible even when the generic late
        # twist is quiet. Probabilities are intentionally below 1.0 to preserve
        # the feeling that not every mission must become a saga.
        if route == "alien_encounter" and rng.random() < 0.48:
            kinds_to_open.append(("contact", route, 1.0))
        elif route == "distress_signal" and rng.random() < 0.58:
            kinds_to_open.append(("rescue", route, 1.0))
        elif route == "abandoned_site" and rng.random() < 0.42:
            kinds_to_open.append((rng.choice(["signal", "anomaly"]), route, 0.95))
        elif route == "space_only" and rng.random() < 0.38:
            kinds_to_open.append((rng.choice(["anomaly", "pursuit", "signal"]), route, 0.9))
        elif route == "planet_nature" and rng.random() < 0.25:
            kinds_to_open.append(("anomaly", route, 0.75))
        elif route == "ship_malfunction" and rng.random() < 0.62:
            kinds_to_open.append(("ship", route, 1.05))

        opened_now: list[str] = []
        for kind, origin, strength in kinds_to_open:
            duplicate = any(
                hook.get("kind") == kind
                and hook.get("origin") == origin
                and session.jump_index - int(hook.get("created_jump", 0)) <= 2
                for hook in state["open_hooks"]
            )
            if duplicate:
                continue
            hook_id = f"H{int(state.get('next_hook_id', 1)):04d}"
            state["next_hook_id"] = int(state.get("next_hook_id", 1)) + 1
            due = session.jump_index + rng.randint(1, 4)
            state["open_hooks"].append({
                "id": hook_id,
                "kind": kind,
                "origin": origin,
                "created_jump": session.jump_index,
                "due_jump": due,
                "expires_jump": due + rng.randint(7, 14),
                "stage": 1,
                "strength": strength,
                "last_outcome": "opened",
            })
            opened_now.append(hook_id)

        state["open_hooks"] = state["open_hooks"][-MAX_OPEN_HOOKS:]
        state["jump_index"] = session.jump_index
        state["history"].append({
            "jump": session.jump_index,
            "seed": session.seed,
            "route": route,
            "callback_hook": plan.hook_id if plan else "",
            "callback_outcome": plan.outcome_id if plan else "",
            "opened_hooks": opened_now,
            "ship_min": min(int(value) for value in ship.values()),
            "reputation": int(state.get("reputation", 0)),
            "unknown_attention": int(state.get("unknown_attention", 0)),
        })
        state["history"] = state["history"][-MAX_HISTORY:]
        self.save(state)
        return state

    def save(self, state: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        # Atomic replacement prevents a half-written memory after a crash.
        fd, temporary = tempfile.mkstemp(prefix=self.path.name + ".", suffix=".tmp", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            try:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            except OSError:
                pass

    def reset(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
