from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from PIL import ImageGrab

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from app.panel_correlation_lab import PanelCorrelationLab


OUTPUT_DIR = ROOT / "artifacts"
OUTPUT_PATH = OUTPUT_DIR / "panel-correlation-lab.png"


def capture_screenshot(output_path: Path, app: PanelCorrelationLab | None = None) -> None:
    if shutil.which("scrot"):
        subprocess.run(["scrot", str(output_path)], check=True)
        return
    try:
        screenshot = ImageGrab.grab()
        screenshot.save(output_path)
    except Exception:
        if app is None:
            raise
        app.figure.savefig(output_path)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    app = PanelCorrelationLab()
    app.update_idletasks()
    app.update()

    app.run_validation()
    app.run_scan()
    app.notebook.select(app.validation_tab)
    app.update_idletasks()
    app.update()

    pooled = app.metric_vars["pooled"].get()
    score = app.metric_vars["score"].get()
    detail_rows = app.detail_tree.get_children()
    scan_rows = app.scan_tree.get_children()
    if pooled == "-" or score == "-":
        raise RuntimeError("Panel correlation UI did not calculate validation metrics")
    if not detail_rows:
        raise RuntimeError("Panel correlation UI did not produce validation detail rows")
    if not scan_rows:
        raise RuntimeError("Panel correlation scanner did not produce rows")

    capture_screenshot(OUTPUT_PATH, app)
    if not OUTPUT_PATH.exists() or OUTPUT_PATH.stat().st_size == 0:
        raise RuntimeError("Panel correlation UI screenshot was not created")

    print(
        f"PANEL_CORRELATION_UI_SMOKE_OK pooled={pooled} generalization={score} "
        f"detail_rows={len(detail_rows)} scan_rows={len(scan_rows)}"
    )
    print(f"PANEL_CORRELATION_UI_SCREENSHOT={OUTPUT_PATH}")
    app.destroy()


if __name__ == "__main__":
    main()
