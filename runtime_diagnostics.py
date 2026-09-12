from __future__ import annotations

from collections import deque
from datetime import datetime
from pathlib import Path
import faulthandler
import os
import platform
import sys
import threading
import traceback
from typing import Any


class RuntimeDiagnostics:
    """Small crash/diagnostic logger with an in-memory breadcrumb trail.

    The breadcrumb buffer is always maintained, but files are only written when
    the user explicitly enables runtime diagnostics. This keeps normal runs
    quiet while preserving the steps that led to an exception once enabled.
    """

    def __init__(self, log_dir: Path, app_name: str, app_version: str, max_breadcrumbs: int = 250):
        self.log_dir = Path(log_dir)
        self.app_name = str(app_name)
        self.app_version = str(app_version)
        self.max_breadcrumbs = max(50, int(max_breadcrumbs))
        self._breadcrumbs: deque[str] = deque(maxlen=self.max_breadcrumbs)
        self._lock = threading.RLock()
        self._enabled = False
        self._handle = None
        self._path: Path | None = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def path(self) -> Path | None:
        return self._path

    def breadcrumb(self, event: str, **details: Any) -> None:
        stamp = datetime.now().astimezone().isoformat(timespec="milliseconds")
        payload = " ".join(f"{key}={self._safe(value)}" for key, value in details.items())
        line = f"[{stamp}] {event}" + (f" | {payload}" if payload else "")
        with self._lock:
            self._breadcrumbs.append(line)
            if self._enabled and self._handle is not None:
                try:
                    self._handle.write(line + "\n")
                    self._handle.flush()
                except Exception:
                    pass

    def enable(self) -> Path | None:
        with self._lock:
            if self._enabled and self._path is not None:
                return self._path
            try:
                self.log_dir.mkdir(parents=True, exist_ok=True)
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                self._path = self.log_dir / f"runtime_diagnostics_v{self.app_version}_{stamp}.log"
                self._handle = self._path.open("a", encoding="utf-8", buffering=1)
                self._enabled = True
                self._write_header()
                if self._breadcrumbs:
                    self._handle.write("\nBreadcrumbs before diagnostics were enabled:\n")
                    for line in self._breadcrumbs:
                        self._handle.write(line + "\n")
                try:
                    faulthandler.enable(file=self._handle, all_threads=True)
                    self._handle.write("\nPython faulthandler: enabled\n")
                except Exception as exc:
                    self._handle.write(f"\nPython faulthandler could not be enabled: {exc}\n")
                self._handle.flush()
                self.breadcrumb("runtime_diagnostics_enabled", path=self._path)
                return self._path
            except Exception:
                self._enabled = False
                self._handle = None
                self._path = None
                return None

    def disable(self) -> None:
        with self._lock:
            if not self._enabled:
                return
            self.breadcrumb("runtime_diagnostics_disabled")
            try:
                if faulthandler.is_enabled():
                    faulthandler.disable()
            except Exception:
                pass
            try:
                if self._handle is not None:
                    self._handle.flush()
                    self._handle.close()
            except Exception:
                pass
            self._handle = None
            self._enabled = False

    def log_exception(self, context: str, exc: BaseException, **details: Any) -> None:
        self.breadcrumb("exception", context=context, type=type(exc).__name__, message=str(exc), **details)
        with self._lock:
            if not self._enabled or self._handle is None:
                return
            try:
                self._handle.write("\n" + "=" * 88 + "\n")
                self._handle.write(f"EXCEPTION CONTEXT: {context}\n")
                for key, value in details.items():
                    self._handle.write(f"{key}: {self._safe(value)}\n")
                self._handle.write("\nRecent breadcrumbs:\n")
                for line in self._breadcrumbs:
                    self._handle.write(line + "\n")
                self._handle.write("\nTraceback:\n")
                traceback.print_exception(type(exc), exc, exc.__traceback__, file=self._handle)
                self._handle.write("=" * 88 + "\n\n")
                self._handle.flush()
            except Exception:
                pass

    def close(self) -> None:
        self.disable()

    def _write_header(self) -> None:
        if self._handle is None:
            return
        self._handle.write(f"{self.app_name} runtime diagnostics v{self.app_version}\n")
        self._handle.write(f"Started: {datetime.now().astimezone().isoformat(timespec='seconds')}\n")
        self._handle.write(f"Python: {sys.version.replace(os.linesep, ' ')}\n")
        self._handle.write(f"Executable: {sys.executable}\n")
        self._handle.write(f"Platform: {platform.platform()}\n")
        self._handle.write(f"Working directory: {os.getcwd()}\n")
        self._handle.write(f"Application directory: {Path(__file__).resolve().parent}\n")
        self._handle.write("This file records runtime breadcrumbs and exceptions because the option was enabled.\n")

    @staticmethod
    def _safe(value: Any) -> str:
        text = str(value).replace("\r", "\\r").replace("\n", "\\n")
        if len(text) > 800:
            text = text[:797] + "..."
        return text
