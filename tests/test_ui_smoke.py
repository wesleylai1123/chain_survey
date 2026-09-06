from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from subprocess import CalledProcessError

from scripts.ui_smoke import capture_dashboard_screenshot


class UiSmokeTests(unittest.TestCase):
    def test_capture_screenshot_falls_back_to_pillow_when_scrot_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "dashboard.png"
            image = Mock()

            with patch("scripts.ui_smoke.shutil.which", return_value=None), patch(
                "scripts.ui_smoke.ImageGrab.grab", return_value=image
            ):
                capture_dashboard_screenshot(output_path)

            image.save.assert_called_once_with(output_path)

    def test_capture_screenshot_saves_dashboard_figure_when_system_capture_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "dashboard.png"
            app = Mock()

            with patch("scripts.ui_smoke.shutil.which", return_value=None), patch(
                "scripts.ui_smoke.ImageGrab.grab",
                side_effect=CalledProcessError(1, ["screencapture"]),
            ):
                capture_dashboard_screenshot(output_path, app)

            app.figure.savefig.assert_called_once_with(output_path)


if __name__ == "__main__":
    unittest.main()
