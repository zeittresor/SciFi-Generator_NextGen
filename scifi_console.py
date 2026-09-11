from __future__ import annotations

"""Cross-platform command-line frontend for the SciFi-Generator story engine.

This module intentionally depends only on Python's standard library plus
``story_engine.py``. It can therefore generate and trace stories on Windows,
Linux and macOS without PyQt6, TTS components, NumPy or FFmpeg.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import TextIO

from story_engine import APP_VERSION, GenerationResult, StoryEngine, StoryEngineError

ROOT = Path(__file__).resolve().parent
VARS_DIR = ROOT / "data" / "vars"
SEQUENCE_FILE = ROOT / "sequence_legacy.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scifi-console",
        description=(
            "Generate sector-jump stories without the graphical interface. "
            "Without options exactly one generated story is written to stdout."
        ),
    )
    parser.add_argument("--version", action="version", version=f"SciFi-Generator {APP_VERSION}")
    parser.add_argument("--seed", type=int, help="use a deterministic random seed")
    parser.add_argument("--count", type=int, default=1, metavar="N", help="generate N stories (default: 1)")
    parser.add_argument(
        "--trace",
        action="store_true",
        help=(
            "append the selected branch route and every sentence fragment in output order, "
            "including source file and source line"
        ),
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument(
        "--raw",
        action="store_true",
        help="print original fragment spelling instead of the display/TTS form",
    )
    parser.add_argument(
        "--no-legacy-umlauts",
        action="store_true",
        help="disable the historical ae/ue/oe display conversion",
    )
    parser.add_argument("--output", type=Path, metavar="FILE", help="write output to FILE instead of stdout")
    parser.add_argument(
        "--validate",
        action="store_true",
        help="validate sentence sources and the common jump-ready story ending, then exit",
    )
    parser.add_argument(
        "--list-routes",
        action="store_true",
        help="list every structurally reachable branch route, then exit",
    )
    return parser


def result_to_dict(result: GenerationResult, *, raw: bool, trace: bool) -> dict:
    payload: dict = {
        "version": APP_VERSION,
        "seed": result.seed,
        "story": result.raw_story if raw else result.display_story,
        "branch_path": [
            {
                "branch_id": item.branch_id,
                "branch_label": item.label,
                "choice_id": item.choice_id,
                "choice_label": item.choice_label,
                "weight": item.weight,
            }
            for item in result.branches
        ],
    }
    if trace:
        payload["selections"] = [
            {
                "index": item.index,
                "scene_id": item.scene_id,
                "scene_title": item.scene_title,
                "label": item.label,
                "source": item.source,
                "line": item.line_number,
                "raw_text": item.raw_text,
                "rendered_text": item.rendered_text,
            }
            for item in result.selections
        ]
    return payload


def write_text_result(
    stream: TextIO,
    result: GenerationResult,
    *,
    raw: bool,
    trace: bool,
    ordinal: int,
    count: int,
) -> None:
    if count > 1:
        stream.write(f"=== STORY {ordinal}/{count} | seed={result.seed} ===\n")
    stream.write((result.raw_story if raw else result.display_story).strip() + "\n")
    if trace:
        stream.write("\n--- TRACE: STORY ROUTE ---\n")
        if result.branches:
            for item in result.branches:
                stream.write(
                    f"B{item.index:02d} | {item.branch_id} | {item.choice_id} | "
                    f"{item.choice_label} | weight={item.weight:g}\n"
                )
        else:
            stream.write("(linear / legacy)\n")
        stream.write("\n--- TRACE: FRAGMENTS IN OUTPUT ORDER ---\n")
        for item in result.selections:
            line = "-" if item.line_number is None else str(item.line_number)
            stream.write(
                f"{item.index:03d} | {item.source}:{line} | {item.label} | {item.raw_text}\n"
            )
        stream.write("--- END TRACE ---\n")
    if count > 1 and ordinal != count:
        stream.write("\n")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.count < 1:
        print("error: --count must be at least 1", file=sys.stderr)
        return 2

    try:
        engine = StoryEngine(VARS_DIR, SEQUENCE_FILE)
        if args.validate:
            missing = engine.validate_sources()
            terminal_errors = engine.validate_terminal_invariant()
            if missing or terminal_errors:
                for name in missing:
                    print(f"MISSING SOURCE: {name}", file=sys.stderr)
                for message in terminal_errors:
                    print(f"TERMINAL INVARIANT: {message}", file=sys.stderr)
                return 1
            print(
                f"OK — SciFi-Generator {APP_VERSION}: "
                f"{len(list(VARS_DIR.glob('*.ini')))} sentence files; "
                "all branch paths return to the common jump-ready ending."
            )
            return 0

        if args.list_routes:
            routes = engine.enumerate_branch_routes()
            if args.json:
                json.dump(routes, sys.stdout, ensure_ascii=False, indent=2)
                sys.stdout.write("\n")
            else:
                for index, route in enumerate(routes, start=1):
                    print(f"{index:03d} | " + " > ".join(route))
                print(f"\n{len(routes)} reachable branch routes")
            return 0

        results: list[GenerationResult] = []
        for offset in range(args.count):
            seed = None if args.seed is None else args.seed + offset
            results.append(
                engine.generate(
                    seed=seed,
                    legacy_umlauts=not args.no_legacy_umlauts,
                )
            )

        stream: TextIO
        should_close = False
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            stream = args.output.open("w", encoding="utf-8", newline="\n")
            should_close = True
        else:
            stream = sys.stdout

        try:
            if args.json:
                payload = [result_to_dict(r, raw=args.raw, trace=args.trace) for r in results]
                json.dump(payload[0] if len(payload) == 1 else payload, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            else:
                for idx, result in enumerate(results, start=1):
                    write_text_result(
                        stream,
                        result,
                        raw=args.raw,
                        trace=args.trace,
                        ordinal=idx,
                        count=len(results),
                    )
        finally:
            if should_close:
                stream.close()
        return 0
    except (StoryEngineError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"SciFi-Generator console error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
