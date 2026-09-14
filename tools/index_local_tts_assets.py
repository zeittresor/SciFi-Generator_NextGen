from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import tarfile
import zipfile
from pathlib import Path

from install_dependencies import default_tree_search_root

ROOT = Path(__file__).resolve().parents[1]

TTS_ASSET_DIR_NAMES = {
    "tts_packages",
    "tts",
    "piper",
    "piper-voices",
    "piper_voices",
    "models",
    "model",
    "voice-models",
    "voice_models",
    "voices",
    "voice",
    "speech",
    "speech-models",
    "speech_models",
    "onnx",
    "huggingface",
    "hub",
    "cache",
    ".cache",
    "downloads",
    "download",
    "packages",
    "deps",
    "dependencies",
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
    "logs",
}


def platform_key() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if machine in {"amd64", "x86_64", "x64"}:
        arch = "x86_64"
    elif machine in {"arm64", "aarch64"}:
        arch = "aarch64"
    else:
        arch = machine or "unknown"
    if system.startswith("win"):
        system = "windows"
    return f"{system}-{arch}"


def hash_file(path: Path, algorithm: str = "md5") -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_valid(path: Path, expected_md5: str = "", expected_size: int = 0) -> bool:
    try:
        if not path.is_file():
            return False
        if expected_size and path.stat().st_size != expected_size:
            return False
        if expected_md5 and hash_file(path, "md5").lower() != expected_md5.lower():
            return False
        return True
    except OSError:
        return False


def runtime_complete(executable: Path) -> bool:
    try:
        if not executable.is_file():
            return False
        parent = executable.parent
        return (parent / "espeak-ng-data").is_dir() or (parent.parent / "espeak-ng-data").is_dir()
    except OSError:
        return False


def runtime_root(executable: Path) -> Path | None:
    if not runtime_complete(executable):
        return None
    parent = executable.parent
    if (parent / "espeak-ng-data").is_dir():
        return parent
    if (parent.parent / "espeak-ng-data").is_dir():
        return parent.parent
    return None


def _safe_runtime_archive(path: Path, executable_name: str) -> bool:
    """Cheaply validate a local runtime archive before staging it for later reuse."""
    lower = path.name.casefold()
    try:
        if lower.endswith(".zip"):
            if not zipfile.is_zipfile(path):
                return False
            with zipfile.ZipFile(path) as archive:
                names = [name.replace("\\", "/") for name in archive.namelist()]
        elif lower.endswith((".tar.gz", ".tgz")):
            with tarfile.open(path, "r:gz") as archive:
                names = [member.name.replace("\\", "/") for member in archive.getmembers()]
        else:
            return False
    except (OSError, zipfile.BadZipFile, tarfile.TarError):
        return False
    executable_folded = executable_name.casefold()
    has_executable = any(name.rsplit("/", 1)[-1].casefold() == executable_folded for name in names)
    has_espeak_data = any("/espeak-ng-data/" in f"/{name.casefold().strip('/')}" for name in names)
    return has_executable and has_espeak_data


def _unique_existing(paths: list[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        try:
            resolved = path.expanduser().resolve()
            key = str(resolved).casefold()
            if key in seen or not resolved.exists():
                continue
        except OSError:
            continue
        seen.add(key)
        result.append(resolved)
    return result


def common_asset_roots() -> list[Path]:
    home = Path.home()
    roots = [
        home / "Downloads",
        home / "Documents",
        home / ".cache" / "huggingface",
        home / ".cache" / "piper",
    ]
    local_app_data = os.environ.get("LOCALAPPDATA")
    app_data = os.environ.get("APPDATA")
    temp = os.environ.get("TEMP") or os.environ.get("TMP")
    if local_app_data:
        roots.extend([
            Path(local_app_data) / "huggingface",
            Path(local_app_data) / "piper",
        ])
    if app_data:
        roots.extend([
            Path(app_data) / "huggingface",
            Path(app_data) / "piper",
        ])
    if temp:
        roots.extend([
            Path(temp) / "piper",
            Path(temp) / "tts",
            Path(temp) / "models",
        ])
    return _unique_existing(roots)


def discover_asset_directories(search_root: Path, app_root: Path) -> list[Path]:
    """Find likely TTS/model cache folders without inspecting arbitrary files."""
    found: list[Path] = []
    try:
        root = search_root.resolve()
        current_app = app_root.resolve()
    except OSError:
        return found
    if not root.is_dir():
        return found

    try:
        for current, dirnames, _filenames in os.walk(root, topdown=True):
            current_path = Path(current)
            kept: list[str] = []
            for dirname in dirnames:
                folded = dirname.casefold()
                candidate = current_path / dirname
                if folded in PRUNE_DIR_NAMES:
                    continue
                try:
                    resolved = candidate.resolve()
                    # Do not recursively rediscover the current project's staged
                    # reuse cache as an external source during the same scan.
                    if resolved == (current_app / "tts_packages" / "_cache").resolve():
                        continue
                    if resolved == (current_app / "tts_packages" / "_reuse_runtime").resolve():
                        continue
                except OSError:
                    continue
                if (
                    folded in TTS_ASSET_DIR_NAMES
                    or folded.startswith("piper")
                    or folded.startswith("voice")
                    or folded.startswith("tts")
                    or folded.endswith("_models")
                    or folded.endswith("-models")
                ):
                    found.append(resolved)
                    # This subtree will be scanned separately for exact catalog
                    # filenames; no need for the outer discovery walk to enter it.
                    continue
                kept.append(dirname)
            dirnames[:] = kept
    except OSError:
        pass
    return _unique_existing(found)


def _walk_for_targets(root: Path, target_names: set[str], executable_names: set[str]):
    root_depth = len(root.parts)
    try:
        for current, dirnames, filenames in os.walk(root, topdown=True):
            current_path = Path(current)
            depth = len(current_path.parts) - root_depth
            dirnames[:] = [
                name for name in dirnames
                if name.casefold() not in PRUNE_DIR_NAMES and depth < 10
            ]
            for filename in filenames:
                if filename in target_names or filename.casefold() in executable_names:
                    yield current_path / filename
    except OSError:
        return


def _link_or_copy(source: Path, target: Path) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        return "existing"
    try:
        os.link(source, target)
        return "hardlink"
    except OSError:
        shutil.copy2(source, target)
        return "copy"


def _copytree_link_or_copy(source: Path, target: Path) -> str:
    if target.exists():
        return "existing"

    methods: set[str] = set()

    def copy_function(src: str, dst: str) -> str:
        src_path = Path(src)
        dst_path = Path(dst)
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(src_path, dst_path)
            methods.add("hardlink")
        except OSError:
            shutil.copy2(src_path, dst_path)
            methods.add("copy")
        return str(dst_path)

    shutil.copytree(source, target, copy_function=copy_function)
    if methods == {"hardlink"}:
        return "hardlink-tree"
    if methods == {"copy"}:
        return "copy-tree"
    return "mixed-tree"


def stage_catalog_assets(
    app_root: Path,
    *,
    search_root: Path | None = None,
    extra_roots: list[Path] | None = None,
) -> dict:
    app_root = Path(app_root).resolve()
    catalog_path = app_root / "tts_package_catalog.json"
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    if int(payload.get("schema_version", 0)) != 1:
        raise ValueError("unsupported TTS package catalog schema")

    cache_dir = app_root / "tts_packages" / "_cache"
    runtime_stage = app_root / "tts_packages" / "_reuse_runtime"
    cache_dir.mkdir(parents=True, exist_ok=True)
    runtime_stage.mkdir(parents=True, exist_ok=True)

    file_specs: dict[str, dict] = {}
    for package in payload.get("packages", []):
        model = str(package.get("model", ""))
        config = str(package.get("config", ""))
        if model:
            file_specs[model] = {
                "kind": "model",
                "package_id": str(package.get("id", "")),
                "md5": str(package.get("model_md5", "")),
                "size": int(package.get("model_bytes", 0) or 0),
            }
        if config:
            file_specs[config] = {
                "kind": "config",
                "package_id": str(package.get("id", "")),
                "md5": str(package.get("config_md5", "")),
                "size": 0,
            }

    current_platform = platform_key()
    engine_specs: dict[str, dict] = {}
    for engine_id, engine in (payload.get("engines") or {}).items():
        info = ((engine.get("platforms") or {}).get(current_platform) or {})
        if not isinstance(info, dict) or not info:
            continue
        archive = str(info.get("archive", ""))
        executable = str(info.get("executable", "piper"))
        if archive:
            file_specs[archive] = {
                "kind": "engine-archive",
                "engine_id": str(engine_id),
                "md5": "",
                "size": 0,
                "executable": executable,
            }
        engine_specs[executable.casefold()] = {
            "engine_id": str(engine_id),
            "executable": executable,
        }

    family_root = Path(search_root or default_tree_search_root(app_root)).resolve()
    roots = discover_asset_directories(family_root, app_root)
    roots.extend(common_asset_roots())
    if extra_roots:
        roots.extend(extra_roots)
    # Always inspect the project family root's conventional sibling cache names
    # indirectly through discover_asset_directories, plus an existing app-local
    # TTS tree on repeated installs.
    if (app_root / "tts_packages").exists():
        roots.append(app_root / "tts_packages")
    roots = _unique_existing(roots)

    staged_files: dict[str, dict] = {}
    staged_runtimes: dict[str, dict] = {}
    seen_sources: set[str] = set()

    target_names = set(file_specs)
    executable_names = set(engine_specs)
    for root in roots:
        for candidate in _walk_for_targets(root, target_names, executable_names):
            try:
                source_key = str(candidate.resolve()).casefold()
            except OSError:
                continue
            if source_key in seen_sources:
                continue
            seen_sources.add(source_key)

            spec = file_specs.get(candidate.name)
            if spec is not None and candidate.name not in staged_files:
                kind = spec["kind"]
                if kind in {"model", "config"}:
                    if not file_valid(candidate, spec.get("md5", ""), int(spec.get("size", 0) or 0)):
                        continue
                elif kind == "engine-archive":
                    if not _safe_runtime_archive(candidate, str(spec.get("executable", "piper"))):
                        continue
                target = cache_dir / candidate.name
                # Existing cache entries must also match before being trusted.
                if target.exists():
                    if kind in {"model", "config"} and not file_valid(
                        target, spec.get("md5", ""), int(spec.get("size", 0) or 0)
                    ):
                        target.unlink(missing_ok=True)
                    elif kind == "engine-archive" and not _safe_runtime_archive(
                        target, str(spec.get("executable", "piper"))
                    ):
                        target.unlink(missing_ok=True)
                method = _link_or_copy(candidate, target)
                staged_files[candidate.name] = {
                    "kind": kind,
                    "package_id": spec.get("package_id", ""),
                    "engine_id": spec.get("engine_id", ""),
                    "source": str(candidate.resolve()),
                    "target": str(target.resolve()),
                    "method": method,
                }

            engine_spec = engine_specs.get(candidate.name.casefold())
            if engine_spec is not None:
                engine_id = str(engine_spec["engine_id"])
                if engine_id in staged_runtimes:
                    continue
                source_root = runtime_root(candidate)
                if source_root is None:
                    continue
                target_root = runtime_stage / engine_id / current_platform
                method = _copytree_link_or_copy(source_root, target_root)
                staged_runtimes[engine_id] = {
                    "source": str(source_root.resolve()),
                    "target": str(target_root.resolve()),
                    "method": method,
                    "executable": str(engine_spec["executable"]),
                }

    manifest = {
        "schema_version": 1,
        "platform": current_platform,
        "project_family_search_root": str(family_root),
        "asset_directories_scanned": [str(path) for path in roots],
        "files": staged_files,
        "runtimes": staged_runtimes,
    }
    manifest_path = cache_dir / "local_reuse_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Find and stage reusable local TTS/Piper assets.")
    parser.add_argument("--app-root", type=Path, default=ROOT)
    parser.add_argument("--search-root", type=Path, default=None)
    args = parser.parse_args()
    try:
        manifest = stage_catalog_assets(args.app_root, search_root=args.search_root)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"[WARN] Local TTS/model reuse scan could not complete: {exc}")
        return 1

    files = manifest.get("files", {})
    runtimes = manifest.get("runtimes", {})
    models = sum(1 for item in files.values() if item.get("kind") == "model")
    configs = sum(1 for item in files.values() if item.get("kind") == "config")
    archives = sum(1 for item in files.values() if item.get("kind") == "engine-archive")
    print(f"[INFO] TTS/model reuse search root: {manifest['project_family_search_root']}")
    if not files and not runtimes:
        print("[INFO] No reusable catalog-matching TTS models or Piper runtimes found locally.")
        return 0
    print(
        "[LOCAL] Reusable TTS assets staged: "
        f"{models} model(s), {configs} config(s), {archives} runtime archive(s), "
        f"{len(runtimes)} complete runtime(s)."
    )
    for filename, item in sorted(files.items()):
        print(f"[LOCAL] {filename} <- {item['source']} ({item['method']})")
    for engine_id, item in sorted(runtimes.items()):
        print(f"[LOCAL] {engine_id} runtime <- {item['source']} ({item['method']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
