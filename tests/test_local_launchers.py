from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class LocalLauncherTests(unittest.TestCase):
    def test_macos_linux_launcher_bootstraps_venv_and_starts_gui(self) -> None:
        script = ROOT / "run.sh"

        self.assertTrue(script.exists(), "run.sh should exist")
        text = script.read_text(encoding="utf-8")
        self.assertIn("python3 -m venv .venv", text)
        self.assertIn(".venv/bin/python -m pip install -r requirements.txt", text)
        self.assertIn(".venv/bin/python app/main.py", text)

    def test_windows_launcher_bootstraps_venv_and_starts_gui(self) -> None:
        script = ROOT / "run.ps1"

        self.assertTrue(script.exists(), "run.ps1 should exist")
        text = script.read_text(encoding="utf-8")
        self.assertIn("python -m venv .venv", text)
        self.assertIn(".venv\\Scripts\\python.exe", text)
        self.assertIn("app/main.py", text)

    def test_readme_documents_one_command_quick_start(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("./run.sh", readme)
        self.assertIn(".\\run.ps1", readme)


if __name__ == "__main__":
    unittest.main()
