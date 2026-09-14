from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
STARTUP_LOG = LOG_DIR / "startup_error.log"


def _write_startup_error(exc: BaseException) -> None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with STARTUP_LOG.open("a", encoding="utf-8") as handle:
            handle.write("=" * 78 + "\n")
            handle.write(f"SciFi-Generator startup failure: {datetime.now().astimezone().isoformat(timespec='seconds')}\n")
            handle.write(f"Python: {sys.version}\n")
            handle.write(f"Executable: {sys.executable}\n")
            handle.write(f"Working directory: {os.getcwd()}\n")
            handle.write(f"Application directory: {BASE_DIR}\n")
            handle.write(f"Exception: {type(exc).__name__}: {exc}\n\n")
            traceback.print_exc(file=handle)
            handle.write("\n")
    except Exception:
        pass


def main() -> int:
    try:
        import app
        from v6028_tts_flow import install as install_v6028_tts_flow

        install_v6028_tts_flow(app)
        return int(app.main())
    except BaseException as exc:
        _write_startup_error(exc)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
