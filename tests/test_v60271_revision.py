from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class InstallerRevisionRegressionTests(unittest.TestCase):
    def test_current_version_is_consistent(self) -> None:
        version = (ROOT / "version.txt").read_text(encoding="utf-8").strip()
        verifier = (ROOT / "tools" / "verify_installation.py").read_text(encoding="utf-8")
        installer = (ROOT / "install_windows.bat").read_text(encoding="utf-8")

        self.assertRegex(version, r"^\d+\.\d+(?:\.\d+)?$")
        self.assertIn(f'EXPECTED_VERSION = "{version}"', verifier)
        self.assertIn('set /p "VERSION="<"version.txt"', installer)
        self.assertIn('Installer v%VERSION%', installer)

    def test_installer_helpers_parse_as_python(self) -> None:
        for relative in (
            Path("tools/install_dependencies.py"),
            Path("tools/index_local_tts_assets.py"),
            Path("tools/verify_installation.py"),
        ):
            with self.subTest(path=str(relative)):
                source = (ROOT / relative).read_text(encoding="utf-8")
                compile(source, str(relative), "exec")

    def test_windows_example_path_cannot_trigger_unicode_escape(self) -> None:
        source = (ROOT / "tools" / "install_dependencies.py").read_text(encoding="utf-8")
        self.assertIn('r"""Return the bounded parent-tree root used for dependency reuse.', source)


if __name__ == "__main__":
    unittest.main()
