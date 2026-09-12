from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable
import hashlib
import json
import os
import platform
import shutil
import tarfile
import tempfile
import urllib.request
import zipfile


ProgressCallback = Callable[[int, str], None]
CancelCheck = Callable[[], None]


class TtsPackageError(RuntimeError):
    pass


@dataclass(frozen=True)
class TtsPackageDefinition:
    package_id: str
    display_name: str
    engine_id: str
    language: str
    locale: str
    quality: str
    gender_hint: str
    model: str
    config: str
    model_url: str
    config_url: str
    model_md5: str
    config_md5: str
    model_bytes: int
    source: str
    source_url: str
    voice_license: str
    speaker_selector: bool = False
    speaker_selector_label: str = "Sprecher / Stil"
    default_speaker: str = ""


class TtsPackageManager:
    """Installs self-contained local TTS voice packages into the application tree.

    The engine is shared between Piper voice packages to avoid duplicating tens of
    megabytes. Installing any package therefore guarantees that its engine and model
    files are all present below ``tts_packages/`` without requiring a system-wide
    installation.
    """

    def __init__(self, app_dir: Path, catalog_path: Path | None = None) -> None:
        self.app_dir = Path(app_dir).resolve()
        self.catalog_path = Path(catalog_path or self.app_dir / "tts_package_catalog.json")
        self.root = self.app_dir / "tts_packages"
        self.engines_dir = self.root / "_engines"
        self.cache_dir = self.root / "_cache"
        self.voices_dir = self.root / "voices"
        self.root.mkdir(parents=True, exist_ok=True)
        self.engines_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.voices_dir.mkdir(parents=True, exist_ok=True)
        self.catalog_errors: list[str] = []
        self.engines: dict[str, dict] = {}
        self.packages: list[TtsPackageDefinition] = []
        self._load_catalog()

    @staticmethod
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

    def _load_catalog(self) -> None:
        self.catalog_errors.clear()
        self.engines.clear()
        self.packages.clear()
        try:
            payload = json.loads(self.catalog_path.read_text(encoding="utf-8"))
            if int(payload.get("schema_version", 0)) != 1:
                raise ValueError("unsupported catalog schema")
            engines = payload.get("engines", {})
            if not isinstance(engines, dict):
                raise ValueError("engines must be an object")
            self.engines = engines
            for raw in payload.get("packages", []):
                definition = TtsPackageDefinition(
                    package_id=str(raw["id"]),
                    display_name=str(raw["display_name"]),
                    engine_id=str(raw["engine"]),
                    language=str(raw["language"]),
                    locale=str(raw["locale"]),
                    quality=str(raw["quality"]),
                    gender_hint=str(raw.get("gender_hint", "")),
                    model=str(raw["model"]),
                    config=str(raw["config"]),
                    model_url=str(raw["model_url"]),
                    config_url=str(raw["config_url"]),
                    model_md5=str(raw.get("model_md5", "")),
                    config_md5=str(raw.get("config_md5", "")),
                    model_bytes=int(raw.get("model_bytes", 0)),
                    source=str(raw.get("source", "")),
                    source_url=str(raw.get("source_url", "")),
                    voice_license=str(raw.get("voice_license", "")),
                    speaker_selector=bool(raw.get("speaker_selector", False)),
                    speaker_selector_label=str(raw.get("speaker_selector_label", "Sprecher / Stil")),
                    default_speaker=str(raw.get("default_speaker", "")),
                )
                if definition.engine_id not in self.engines:
                    raise ValueError(f"unknown engine for {definition.package_id}: {definition.engine_id}")
                self.packages.append(definition)
        except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            self.catalog_errors.append(f"{self.catalog_path.name}: {exc}")

    def reload_catalog(self) -> None:
        """Reload the external package catalog after the user edited it."""
        self._load_catalog()

    def _encode_path(self, path: Path) -> str:
        """Store paths relative to the app directory whenever possible.

        This keeps downloaded complete packages usable when the whole portable
        SciFi-Generator directory is moved to another drive or machine.
        """
        resolved = Path(path).resolve()
        try:
            return resolved.relative_to(self.app_dir).as_posix()
        except ValueError:
            return str(resolved)

    def _decode_path(self, value: str | os.PathLike[str] | None) -> Path | None:
        if not value:
            return None
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = self.app_dir / candidate
        return candidate.resolve()

    def package(self, package_id: str) -> TtsPackageDefinition | None:
        return next((item for item in self.packages if item.package_id == package_id), None)

    def engine_platform_info(self, engine_id: str) -> dict | None:
        engine = self.engines.get(engine_id) or {}
        platforms = engine.get("platforms") or {}
        info = platforms.get(self.platform_key())
        return dict(info) if isinstance(info, dict) else None

    def package_supported(self, definition: TtsPackageDefinition) -> bool:
        return self.engine_platform_info(definition.engine_id) is not None

    def package_dir(self, package_id: str) -> Path:
        return self.voices_dir / package_id

    def package_state_path(self, package_id: str) -> Path:
        return self.package_dir(package_id) / "package.json"

    @staticmethod
    def _hash_file(path: Path, algorithm: str = "md5") -> str:
        digest = hashlib.new(algorithm)
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    def _file_valid(self, path: Path, expected_md5: str = "", expected_size: int = 0) -> bool:
        if not path.is_file():
            return False
        if expected_size and path.stat().st_size != expected_size:
            return False
        if expected_md5 and self._hash_file(path, "md5").lower() != expected_md5.lower():
            return False
        return True

    @staticmethod
    def _runtime_complete(executable: Path | None) -> bool:
        if executable is None or not executable.is_file():
            return False
        parent = executable.parent
        return (parent / "espeak-ng-data").is_dir() or (parent.parent / "espeak-ng-data").is_dir()

    def _state(self, package_id: str) -> dict:
        path = self.package_state_path(package_id)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, UnicodeError, json.JSONDecodeError):
            return {}

    def is_installed(self, package_id: str) -> bool:
        definition = self.package(package_id)
        if definition is None:
            return False
        state = self._state(package_id)
        model = self.package_dir(package_id) / definition.model
        config = self.package_dir(package_id) / definition.config
        engine_path = self._decode_path(state.get("engine_path"))
        return bool(
            state.get("installed") is True
            and self._file_valid(model, definition.model_md5, definition.model_bytes)
            and self._file_valid(config, definition.config_md5)
            and self._runtime_complete(engine_path)
        )

    def status_text(self, definition: TtsPackageDefinition) -> str:
        if self.is_installed(definition.package_id):
            return "Installiert"
        if not self.package_supported(definition):
            return "Auf diesem System nicht verfügbar"
        return "Verfügbar"

    def _search_roots(self) -> list[Path]:
        roots = [self.app_dir, self.app_dir.parent]
        home = Path.home()
        for extra in (home / "Downloads", home / "Documents"):
            if extra.exists():
                roots.append(extra)
        unique: list[Path] = []
        seen: set[str] = set()
        for root in roots:
            try:
                key = str(root.resolve()).casefold()
            except OSError:
                continue
            if key not in seen and root.exists():
                unique.append(root)
                seen.add(key)
        return unique

    def _walk_named(self, root: Path, filename: str, max_depth: int = 6):
        root = Path(root)
        root_depth = len(root.parts)
        skip = {".git", ".venv", "venv", "__pycache__", "node_modules", "logs", "temp"}
        for current, dirs, files in os.walk(root):
            current_path = Path(current)
            depth = len(current_path.parts) - root_depth
            dirs[:] = [d for d in dirs if d not in skip and depth < max_depth]
            if filename in files:
                yield current_path / filename

    def _find_reusable_file(self, filename: str, expected_md5: str = "", expected_size: int = 0) -> Path | None:
        cache = self.cache_dir / filename
        if self._file_valid(cache, expected_md5, expected_size):
            return cache
        for root in self._search_roots():
            for candidate in self._walk_named(root, filename):
                try:
                    if candidate.resolve().is_relative_to(self.root.resolve()):
                        if candidate.resolve() != cache.resolve():
                            continue
                except (OSError, AttributeError):
                    pass
                try:
                    if self._file_valid(candidate, expected_md5, expected_size):
                        return candidate
                except OSError:
                    continue
        return None

    def _find_reusable_engine_dir(self, executable_name: str) -> Path | None:
        for root in self._search_roots():
            for executable in self._walk_named(root, executable_name, max_depth=5):
                parent = executable.parent
                # A complete legacy Piper runtime carries espeak-ng-data with the binary.
                # Return the smallest directory containing both, so all runtime DLL/SO files
                # are copied together instead of copying just piper(.exe).
                if (parent / "espeak-ng-data").is_dir():
                    return parent
                if (parent.parent / "espeak-ng-data").is_dir():
                    return parent.parent
        return None

    @staticmethod
    def _archive_target(base: Path, member_name: str) -> Path:
        target = (base / member_name).resolve()
        try:
            target.relative_to(base.resolve())
        except ValueError as exc:
            raise TtsPackageError(f"Unsicherer Pfad im TTS-Archiv: {member_name}") from exc
        return target

    @classmethod
    def _safe_extract_zip(cls, archive: Path, destination: Path) -> None:
        with zipfile.ZipFile(archive) as zf:
            for info in zf.infolist():
                cls._archive_target(destination, info.filename)
            zf.extractall(destination)

    @classmethod
    def _safe_extract_tar(cls, archive: Path, destination: Path) -> None:
        with tarfile.open(archive, "r:gz") as tf:
            for member in tf.getmembers():
                cls._archive_target(destination, member.name)
                if member.issym() or member.islnk():
                    raise TtsPackageError(f"Symbolische Links sind in TTS-Archiven nicht erlaubt: {member.name}")
            tf.extractall(destination)

    @staticmethod
    def _download(url: str, target: Path, *, callback: ProgressCallback, start: int, end: int, cancel_check: CancelCheck) -> None:
        if not str(url).lower().startswith("https://"):
            raise TtsPackageError(f"TTS-Downloads sind nur über HTTPS erlaubt: {url}")
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(target.suffix + ".partial")
        partial.unlink(missing_ok=True)
        request = urllib.request.Request(url, headers={"User-Agent": "SciFi-Generator-TTS-Package-Manager/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=45) as response, partial.open("wb") as output:
                total = int(response.headers.get("Content-Length") or 0)
                received = 0
                while True:
                    cancel_check()
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                    received += len(chunk)
                    if total > 0:
                        fraction = min(1.0, received / total)
                        callback(start + round((end - start) * fraction), f"Download: {target.name} — {received / 1048576:.1f}/{total / 1048576:.1f} MiB")
                    else:
                        callback(start, f"Download: {target.name} — {received / 1048576:.1f} MiB")
            os.replace(partial, target)
        except Exception as exc:
            partial.unlink(missing_ok=True)
            raise TtsPackageError(f"Download fehlgeschlagen ({target.name}): {exc}") from exc

    def _engine_install_dir(self, engine_id: str) -> Path:
        return self.engines_dir / engine_id / self.platform_key()

    def _installed_engine_executable(self, engine_id: str) -> Path | None:
        state_path = self._engine_install_dir(engine_id) / "engine.json"
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            executable = self._decode_path(state.get("executable"))
            if self._runtime_complete(executable):
                return executable
        except (OSError, UnicodeError, json.JSONDecodeError):
            pass
        info = self.engine_platform_info(engine_id)
        if not info:
            return None
        name = str(info.get("executable", "piper"))
        engine_dir = self._engine_install_dir(engine_id)
        candidates = list(engine_dir.rglob(name)) if engine_dir.exists() else []
        for candidate in candidates:
            if self._runtime_complete(candidate):
                return candidate
        return None

    def _ensure_engine(self, engine_id: str, callback: ProgressCallback, cancel_check: CancelCheck) -> Path:
        installed = self._installed_engine_executable(engine_id)
        if installed is not None:
            callback(15, "Vorhandene Piper-Laufzeit wird wiederverwendet.")
            return installed
        info = self.engine_platform_info(engine_id)
        if not info:
            raise TtsPackageError(f"Für {self.platform_key()} ist kein komplettes Piper-Laufzeitpaket hinterlegt.")
        executable_name = str(info.get("executable", "piper"))
        engine_dir = self._engine_install_dir(engine_id)
        reusable_dir = self._find_reusable_engine_dir(executable_name)
        if reusable_dir is not None:
            callback(12, f"Bereits vorhandene Piper-Laufzeit gefunden: {reusable_dir}")
            temp = Path(tempfile.mkdtemp(prefix="scifi_piper_engine_", dir=self.root))
            try:
                copied = temp / "runtime"
                shutil.copytree(reusable_dir, copied)
                candidates = list(copied.rglob(executable_name))
                if not candidates:
                    raise TtsPackageError("Die gefundene Piper-Laufzeit enthält kein ausführbares Piper-Programm.")
                shutil.rmtree(engine_dir, ignore_errors=True)
                engine_dir.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(copied), str(engine_dir))
            finally:
                shutil.rmtree(temp, ignore_errors=True)
            executable = next(iter(engine_dir.rglob(executable_name)))
            if os.name != "nt":
                executable.chmod(executable.stat().st_mode | 0o111)
            self._write_engine_state(engine_id, executable, "reused-local-runtime")
            return executable

        archive_name = str(info["archive"])
        archive = self._find_reusable_file(archive_name)
        if archive is None:
            archive = self.cache_dir / archive_name
            callback(5, "Piper-Laufzeit wird heruntergeladen …")
            self._download(str(info["url"]), archive, callback=callback, start=5, end=30, cancel_check=cancel_check)
        else:
            callback(10, f"Lokales Piper-Archiv wird wiederverwendet: {archive}")
            if archive.parent != self.cache_dir:
                cached = self.cache_dir / archive_name
                shutil.copy2(archive, cached)
                archive = cached

        callback(31, "Piper-Laufzeit wird entpackt …")
        temp = Path(tempfile.mkdtemp(prefix="scifi_piper_extract_", dir=self.root))
        try:
            if archive_name.lower().endswith(".zip"):
                self._safe_extract_zip(archive, temp)
            elif archive_name.lower().endswith((".tar.gz", ".tgz")):
                self._safe_extract_tar(archive, temp)
            else:
                raise TtsPackageError(f"Unbekanntes Piper-Archivformat: {archive_name}")
            cancel_check()
            candidates = list(temp.rglob(executable_name))
            if not candidates:
                raise TtsPackageError(f"Piper-Archiv enthält {executable_name} nicht.")
            common_root = candidates[0].parent
            # Prefer the archive's piper directory if there is exactly one.
            if common_root.name.lower() != "piper" and (temp / "piper").is_dir():
                common_root = temp / "piper"
            shutil.rmtree(engine_dir, ignore_errors=True)
            engine_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(common_root), str(engine_dir))
            executable = next(iter(engine_dir.rglob(executable_name)))
            if os.name != "nt":
                executable.chmod(executable.stat().st_mode | 0o111)
            self._write_engine_state(engine_id, executable, str(archive))
            return executable
        finally:
            shutil.rmtree(temp, ignore_errors=True)

    def _write_engine_state(self, engine_id: str, executable: Path, source: str) -> None:
        engine = self.engines.get(engine_id) or {}
        state = {
            "engine_id": engine_id,
            "name": engine.get("name", engine_id),
            "project": engine.get("project", "Piper"),
            "project_url": engine.get("project_url", ""),
            "license": engine.get("license", ""),
            "platform": self.platform_key(),
            "executable": self._encode_path(executable),
            "source": source,
        }
        path = self._engine_install_dir(engine_id) / "engine.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def _obtain_voice_file(self, filename: str, url: str, md5: str, size: int, target: Path, *, callback: ProgressCallback, start: int, end: int, cancel_check: CancelCheck) -> str:
        if self._file_valid(target, md5, size):
            return "already-installed"
        reusable = self._find_reusable_file(filename, md5, size)
        if reusable is not None:
            callback(start, f"Vorhandene Datei wird wiederverwendet: {reusable}")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(reusable, target)
            return f"reused:{reusable}"
        cache = self.cache_dir / filename
        if not self._file_valid(cache, md5, size):
            self._download(url, cache, callback=callback, start=start, end=end, cancel_check=cancel_check)
        if not self._file_valid(cache, md5, size):
            raise TtsPackageError(f"Prüfsumme oder Größe stimmt nach Download nicht: {filename}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cache, target)
        return f"downloaded:{url}"

    def install(self, package_id: str, *, callback: ProgressCallback | None = None, cancel_check: CancelCheck | None = None) -> dict:
        callback = callback or (lambda _value, _message: None)
        cancel_check = cancel_check or (lambda: None)
        definition = self.package(package_id)
        if definition is None:
            raise TtsPackageError(f"Unbekanntes TTS-Paket: {package_id}")
        if not self.package_supported(definition):
            raise TtsPackageError(f"{definition.display_name} wird auf {self.platform_key()} derzeit nicht als Komplettpaket angeboten.")
        callback(1, f"Installiere {definition.display_name} ({definition.quality}) …")
        engine_path = self._ensure_engine(definition.engine_id, callback, cancel_check)
        cancel_check()
        package_dir = self.package_dir(package_id)
        package_dir.mkdir(parents=True, exist_ok=True)
        model_target = package_dir / definition.model
        config_target = package_dir / definition.config
        model_source = self._obtain_voice_file(
            definition.model, definition.model_url, definition.model_md5, definition.model_bytes, model_target,
            callback=callback, start=35, end=86, cancel_check=cancel_check,
        )
        cancel_check()
        config_source = self._obtain_voice_file(
            definition.config, definition.config_url, definition.config_md5, 0, config_target,
            callback=callback, start=87, end=94, cancel_check=cancel_check,
        )
        cancel_check()
        if not self._file_valid(model_target, definition.model_md5, definition.model_bytes):
            raise TtsPackageError("Piper-Modell ist nach der Installation nicht gültig.")
        if not self._file_valid(config_target, definition.config_md5):
            raise TtsPackageError("Piper-Konfiguration ist nach der Installation nicht gültig.")
        source_text = (
            f"SciFi-Generator TTS complete package\n\n"
            f"Voice: {definition.display_name}\nQuality: {definition.quality}\nLanguage: {definition.language}\n"
            f"Voice source: {definition.source_url}\nVoice license: {definition.voice_license}\n\n"
            f"Engine: {(self.engines.get(definition.engine_id) or {}).get('name', definition.engine_id)}\n"
            f"Engine project: {(self.engines.get(definition.engine_id) or {}).get('project_url', '')}\n"
            f"Engine license: {(self.engines.get(definition.engine_id) or {}).get('license', '')}\n\n"
            "The runtime and model are stored locally below tts_packages so no system-wide Piper installation is required.\n"
        )
        (package_dir / "SOURCE_AND_LICENSE.txt").write_text(source_text, encoding="utf-8")
        state = {
            "installed": True,
            "package_id": package_id,
            "display_name": definition.display_name,
            "engine": definition.engine_id,
            "engine_path": self._encode_path(engine_path),
            "model_path": self._encode_path(model_target),
            "config_path": self._encode_path(config_target),
            "locale": definition.locale,
            "quality": definition.quality,
            "gender_hint": definition.gender_hint,
            "model_source": model_source,
            "config_source": config_source,
        }
        self.package_state_path(package_id).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        callback(100, f"{definition.display_name} ist vollständig installiert und kann sofort verwendet werden.")
        return state

    def remove(self, package_id: str) -> None:
        definition = self.package(package_id)
        if definition is None:
            raise TtsPackageError(f"Unbekanntes TTS-Paket: {package_id}")
        shutil.rmtree(self.package_dir(package_id), ignore_errors=True)

    def installed_voices(self) -> list[dict]:
        voices: list[dict] = []
        for definition in self.packages:
            if not self.is_installed(definition.package_id):
                continue
            state = self._state(definition.package_id)
            config_path = self._decode_path(state.get("config_path"))
            speaker_map: dict[str, int] = {}
            try:
                if config_path is None:
                    raise OSError("missing config path")
                config = json.loads(config_path.read_text(encoding="utf-8"))
                raw_speakers = config.get("speaker_id_map") or {}
                if isinstance(raw_speakers, dict):
                    speaker_map = {str(name): int(value) for name, value in raw_speakers.items()}
            except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
                speaker_map = {}

            common = {
                "backend": "piper",
                "package_id": definition.package_id,
                "locale": definition.locale,
                "quality": definition.quality,
                "description": f"Piper Komplettpaket · {definition.quality}",
                "gender": definition.gender_hint,
                "engine_path": str(self._decode_path(state.get("engine_path")) or ""),
                "model_path": str(self._decode_path(state.get("model_path")) or ""),
                "config_path": str(self._decode_path(state.get("config_path")) or ""),
            }
            if speaker_map and definition.speaker_selector:
                ordered = sorted(speaker_map.items(), key=lambda pair: pair[1])
                default_name = definition.default_speaker if definition.default_speaker in speaker_map else ordered[0][0]
                voices.append({
                    **common,
                    "id": definition.package_id,
                    "name": f"{definition.display_name} ({definition.quality})",
                    "speaker_id": int(speaker_map[default_name]),
                    "speaker_name": default_name,
                    "speaker_selector": True,
                    "speaker_selector_label": definition.speaker_selector_label,
                    "speaker_options": [
                        {"name": name, "id": int(speaker_id)} for name, speaker_id in ordered
                    ],
                })
            elif speaker_map and len(speaker_map) <= 32:
                for speaker_name, speaker_id in sorted(speaker_map.items(), key=lambda pair: pair[1]):
                    voices.append({
                        **common,
                        "id": f"{definition.package_id}:{speaker_id}",
                        "name": f"{definition.display_name} — {speaker_name}",
                        "speaker_id": speaker_id,
                        "speaker_name": speaker_name,
                    })
            else:
                voices.append({
                    **common,
                    "id": definition.package_id,
                    "name": f"{definition.display_name} ({definition.quality})",
                    "speaker_id": None,
                    "speaker_name": "",
                })
        return voices

    def diagnostics(self) -> list[str]:
        lines = [f"Plattform: {self.platform_key()}", f"Katalogpakete: {len(self.packages)}"]
        lines.extend(self.catalog_errors)
        for definition in self.packages:
            lines.append(f"{definition.display_name} [{definition.quality}]: {self.status_text(definition)}")
        return lines
