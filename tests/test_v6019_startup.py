from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class StartupRegressionTests(unittest.TestCase):
    def test_pyqt_slot_is_imported_when_decorator_is_used(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = set()
        used_decorators = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imported.update(alias.asname or alias.name for alias in node.names)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Name):
                        used_decorators.add(decorator.func.id)
                    elif isinstance(decorator, ast.Name):
                        used_decorators.add(decorator.id)
        self.assertIn("pyqtSlot", used_decorators)
        self.assertIn("pyqtSlot", imported)

    def test_launcher_creates_startup_diagnostic_log_and_installs_extensions(self):
        source = (ROOT / "launcher.py").read_text(encoding="utf-8")
        self.assertIn('STARTUP_LOG = LOG_DIR / "startup_error.log"', source)
        self.assertIn("import app", source)
        self.assertIn("install_v6028_tts_flow(app)", source)
        self.assertIn("return int(app.main())", source)
        self.assertIn('traceback.print_exc(file=handle)', source)

    def test_windows_launchers_use_diagnostic_launcher(self):
        start = (ROOT / "start_app.bat").read_text(encoding="utf-8")
        install = (ROOT / "install_windows.bat").read_text(encoding="utf-8")
        self.assertIn('python.exe" launcher.py', start)
        self.assertIn('pythonw.exe" "%CD%\\launcher.py"', install)


if __name__ == "__main__":
    unittest.main()
