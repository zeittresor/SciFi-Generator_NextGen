from __future__ import annotations

import argparse
import html
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# We deliberately search only directories whose names strongly suggest that they
# contain reusable package artifacts. The directory tree itself is traversed so a
# project at D:\xxx\yyy\zzz can reuse caches anywhere below D:\xxx, but arbitrary
# files elsewhere in that tree are never inspected as package candidates.
WHEEL_DIR_NAMES = {
    "wheelhouse",
    "wheelhouses",
    "wheel",
    "wheels",
    "wheel-cache",
    "wheel_cache",
    "pip",
    "pip-cache",
    "pip_cache",
    "cache",
    ".cache",
    "packages",
    "package-cache",
    "package_cache",
    "deps",
    "dependencies",
    "downloads",
    "download",
    "artifacts",
    "dist",
}

PRUNE_DIR_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "__pycache__",
}


def default_tree_search_root(project_root: Path) -> Path:
    r"""Return the bounded parent-tree root used for dependency reuse.

    For a project at D:\xxx\yyy\zzz this intentionally returns D:\xxx. If the
    project is too close to a filesystem root, we stop at its immediate parent
    instead of recursively scanning an entire drive.
    """
    override = os.environ.get("SCIFI_WHEEL_SEARCH_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()

    parents = list(project_root.resolve().parents)
    candidate = parents[1] if len(parents) >= 2 else project_root.resolve().parent
    if candidate.parent == candidate:  # Never recurse through an entire drive/root.
        candidate = project_root.resolve().parent
    return candidate


def _wheel_files_below(directory: Path) -> set[Path]:
    found: set[Path] = set()
    try:
        for current, dirnames, filenames in os.walk(directory, topdown=True):
            dirnames[:] = [
                name for name in dirnames
                if name.casefold() not in PRUNE_DIR_NAMES
            ]
            current_path = Path(current)
            for filename in filenames:
                if filename.casefold().endswith(".whl"):
                    found.add((current_path / filename).resolve())
    except OSError:
        pass
    return found


def discover_local_wheels(project_root: Path) -> tuple[Path, list[Path]]:
    search_root = default_tree_search_root(project_root)
    wheels: set[Path] = set()
    scanned_artifact_dirs: set[Path] = set()

    def scan_artifact_dir(path: Path) -> None:
        try:
            resolved = path.resolve()
        except OSError:
            return
        if resolved in scanned_artifact_dirs or not resolved.is_dir():
            return
        scanned_artifact_dirs.add(resolved)
        wheels.update(_wheel_files_below(resolved))

    # Fast, explicit project-local locations first.
    for name in ("wheelhouse", "wheels", ".cache", "cache", "packages", "deps", "dependencies"):
        scan_artifact_dir(project_root / name)

    # Search the bounded project family tree, but only enter artifact/cache
    # directories for actual wheel-file inspection.
    if search_root.is_dir():
        try:
            for current, dirnames, _filenames in os.walk(search_root, topdown=True):
                current_path = Path(current)
                kept: list[str] = []
                for dirname in dirnames:
                    folded = dirname.casefold()
                    candidate = current_path / dirname
                    try:
                        if candidate.resolve() == (project_root / ".venv").resolve():
                            continue
                    except OSError:
                        continue
                    if folded in PRUNE_DIR_NAMES:
                        continue
                    if folded in WHEEL_DIR_NAMES or folded.startswith("wheelhouse"):
                        scan_artifact_dir(candidate)
                        # scan_artifact_dir recursively handles this subtree; avoid
                        # traversing it a second time in the outer directory walk.
                        continue
                    kept.append(dirname)
                dirnames[:] = kept
        except OSError:
            pass

    # Common per-user package/download caches are useful even when they live on a
    # different drive than the project.
    home = Path.home()
    common_locations = [
        home / "Downloads",
        home / ".cache" / "pip" / "wheels",
    ]
    local_app_data = os.environ.get("LOCALAPPDATA")
    app_data = os.environ.get("APPDATA")
    temp = os.environ.get("TEMP") or os.environ.get("TMP")
    if local_app_data:
        common_locations.append(Path(local_app_data) / "pip" / "Cache" / "wheels")
    if app_data:
        common_locations.append(Path(app_data) / "pip" / "Cache" / "wheels")
    if temp:
        common_locations.extend([Path(temp) / "wheelhouse", Path(temp) / "wheels"])
    for location in common_locations:
        scan_artifact_dir(location)

    return search_root, sorted(wheels, key=lambda path: str(path).casefold())


def write_find_links_index(wheels: list[Path], index_path: Path) -> None:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["<!doctype html>", "<meta charset=\"utf-8\">", "<title>Local wheel reuse</title>"]
    for wheel in wheels:
        uri = html.escape(wheel.as_uri(), quote=True)
        label = html.escape(wheel.name)
        lines.append(f'<a href="{uri}">{label}</a><br>')
    index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def requirement_lines(path: Path) -> list[str]:
    result: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        # Keep environment markers intact; only remove a conventional whitespace
        # comment so the requirement can be passed as one pip argument.
        if " #" in line:
            line = line.split(" #", 1)[0].rstrip()
        if line:
            result.append(line)
    return result


def _run_quiet(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def install(requirements: Path) -> int:
    python = sys.executable
    project_root = ROOT
    search_root, wheels = discover_local_wheels(project_root)
    print(f"[INFO] Local wheel search root: {search_root}")

    if not wheels:
        print("[INFO] No reusable wheel files found in known local cache/dependency locations.")
        return subprocess.call([python, "-m", "pip", "install", "-r", str(requirements)])

    index_path = project_root / "logs" / "local_wheels_index.html"
    write_find_links_index(wheels, index_path)
    parent_dirs = len({wheel.parent for wheel in wheels})
    print(f"[INFO] Found {len(wheels)} local wheel file(s) across {parent_dirs} directory/directories.")
    print("[INFO] Trying local wheels before contacting the configured Python package index...")

    # Install each top-level requirement from a suitable local wheel without its
    # dependencies first. This lets us retain a compatible cached PyQt6/Numpy/etc.
    # even if only one transitive dependency still has to be downloaded later.
    reused: list[str] = []
    for requirement in requirement_lines(requirements):
        result = _run_quiet([
            python,
            "-m",
            "pip",
            "install",
            "--no-index",
            "--find-links",
            str(index_path),
            "--no-deps",
            requirement,
        ])
        if result.returncode == 0:
            reused.append(requirement)
            print(f"[LOCAL] Reused compatible wheel for: {requirement}")

    # Now see whether all transitive dependencies can also be satisfied entirely
    # from the accumulated local wheel pool.
    offline = _run_quiet([
        python,
        "-m",
        "pip",
        "install",
        "--no-index",
        "--find-links",
        str(index_path),
        "-r",
        str(requirements),
    ])
    if offline.returncode == 0:
        print("[OK] Dependencies satisfied entirely from existing/local wheel files; package index not used.")
        return 0

    if reused:
        print(f"[INFO] Reused {len(reused)} top-level requirement(s) locally; resolving only missing/incompatible packages online.")
    else:
        print("[INFO] Local wheels were found, but none could satisfy the top-level requirements on this Python/platform combination.")
    return subprocess.call([python, "-m", "pip", "install", "-r", str(requirements)])


def main() -> int:
    parser = argparse.ArgumentParser(description="Install SciFi-Generator dependencies with local-wheel reuse first.")
    parser.add_argument(
        "--requirements",
        type=Path,
        default=ROOT / "requirements.txt",
        help="requirements file to install",
    )
    args = parser.parse_args()
    requirements = args.requirements.resolve()
    if not requirements.is_file():
        print(f"[ERROR] Requirements file not found: {requirements}")
        return 2
    return install(requirements)


if __name__ == "__main__":
    raise SystemExit(main())
