from __future__ import annotations

"""Mass-generate stories and run deterministic structural/text sanity checks.

The audit intentionally uses only the Python standard library and story_engine.py,
so it can also be run on Linux without the GUI dependencies.
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from story_engine import APP_VERSION, StoryEngine  # noqa: E402

VARS = ROOT / "data" / "vars"
SEQUENCE = ROOT / "sequence_legacy.json"
EXPECTED_TERMINAL = (
    "mission_free_space.ini",
    "mission_end_status.ini",
    "ship_liftoff_jumpready.ini",
    "mission_jump_prompt.ini",
)

BAD_PUNCTUATION = re.compile(r"\.\.|\.,|,\.|,,| {3,}")
DUPLICATED_WORD = re.compile(r"\b([A-Za-zÄÖÜäöüß]{4,})\s+\1\b", re.IGNORECASE)


def _source_name(source: str) -> str:
    return source.replace("\\", "/").rsplit("/", 1)[-1]


def audit(count: int, start_seed: int = 0, require_all_routes: bool = False) -> tuple[list[str], dict[str, int]]:
    engine = StoryEngine(VARS, SEQUENCE)
    errors: list[str] = []
    route_signatures: set[tuple[tuple[str, str], ...]] = set()

    missing = engine.validate_sources()
    if missing:
        errors.append("Missing sentence sources: " + ", ".join(missing))
    errors.extend(f"Terminal structure: {message}" for message in engine.validate_terminal_invariant())

    for seed in range(start_seed, start_seed + count):
        result = engine.generate(seed=seed, legacy_umlauts=False)
        story = result.raw_story
        route_signatures.add(tuple((item.branch_id, item.choice_id) for item in result.branches))

        match = BAD_PUNCTUATION.search(story)
        if match:
            errors.append(f"seed {seed}: punctuation/spacing artifact {match.group(0)!r}")

        for marker in engine.REPETITIVE_CLAUSE_MARKERS:
            if story.count(marker) > 1:
                errors.append(f"seed {seed}: repeated stock clause {marker!r}")

        # Look inside individual selected fragments rather than the complete story.
        # Repeated star-time tokens (e.g. 'hah hah') are intentionally possible,
        # while duplicated normal words inside one source line almost always signal
        # a bad expansion/rewrite.
        for selection in result.selections:
            text = selection.rendered_text or selection.raw_text
            duplicate = DUPLICATED_WORD.search(text)
            if duplicate:
                errors.append(
                    f"seed {seed}: duplicated word {duplicate.group(0)!r} in "
                    f"{selection.source}:{selection.line_number}"
                )
                break

        source_tail = tuple(_source_name(item.source) for item in result.selections[-4:])
        if source_tail != EXPECTED_TERMINAL:
            errors.append(
                f"seed {seed}: terminal sources {source_tail!r}, expected {EXPECTED_TERMINAL!r}"
            )

        # The common final status is deliberately explicit, not inferred merely
        # from a branch-specific departure sentence.
        if _source_name(result.selections[-4].source) != "mission_free_space.ini":
            errors.append(f"seed {seed}: no explicit free-space terminal fragment")

        if len(errors) >= 100:
            errors.append("Audit stopped after 100 findings.")
            break

    structural_routes = len(engine.enumerate_branch_routes())
    if require_all_routes and len(route_signatures) != structural_routes:
        errors.append(
            f"Route coverage incomplete: observed {len(route_signatures)} of {structural_routes} structural routes"
        )

    stats = {
        "stories": count,
        "start_seed": start_seed,
        "observed_routes": len(route_signatures),
        "structural_routes": structural_routes,
        "sentence_files": len(list(VARS.glob("*.ini"))),
    }
    return errors, stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mass-audit SciFi-Generator stories.")
    parser.add_argument("--count", type=int, default=10_000, help="number of consecutive seeds to generate")
    parser.add_argument("--start-seed", type=int, default=0, help="first deterministic seed")
    parser.add_argument(
        "--require-all-routes",
        action="store_true",
        help="fail unless the generated seed range reaches every structural branch route",
    )
    args = parser.parse_args(argv)
    if args.count < 1:
        parser.error("--count must be at least 1")

    errors, stats = audit(args.count, args.start_seed, args.require_all_routes)
    print(f"SciFi-Generator story audit v{APP_VERSION}")
    print(f"Stories generated: {stats['stories']} (seeds {stats['start_seed']}..{stats['start_seed'] + stats['stories'] - 1})")
    print(f"Sentence files: {stats['sentence_files']}")
    print(f"Observed branch routes: {stats['observed_routes']} / {stats['structural_routes']}")
    if errors:
        print("Audit: FAILED")
        for item in errors:
            print(f"  - {item}")
        return 1
    print("Audit: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
