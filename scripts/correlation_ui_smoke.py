from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from PIL import ImageGrab

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from app.correlation_lab import CorrelationLab


OUTPUT_DIR = ROOT / "artifacts"
OUTPUT_PATH = OUTPUT_DIR / "correlation-lab.png"


def capture_screenshot(output_path: Path, app: CorrelationLab | None = None) -> None:
    if shutil.which("scrot"):
        subprocess.run(["scrot", str(output_path)], check=True)
        return
    try:
        screenshot = ImageGrab.grab()
        screenshot.save(output_path)
    except Exception:
        if app is None:
            raise
        app.scatter_figure.savefig(output_path)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    app = CorrelationLab()
    app.update_idletasks()
    app.update()

    app.run_pair_analysis()
    app.run_scan()
    app.update_idletasks()
    app.update()

    corr = app.metric_vars["corr"].get()
    rows = app.scan_tree.get_children()
    if corr == "-":
        raise RuntimeError("Correlation UI did not calculate a pair correlation")
    if not rows:
        raise RuntimeError("Correlation scanner did not produce rows")

    capture_screenshot(OUTPUT_PATH, app)
    if not OUTPUT_PATH.exists() or OUTPUT_PATH.stat().st_size == 0:
        raise RuntimeError("Correlation UI screenshot was not created")

    print(f"CORRELATION_UI_SMOKE_OK corr={corr} rows={len(rows)}")
    print(f"CORRELATION_UI_SCREENSHOT={OUTPUT_PATH}")
    app.destroy()


if __name__ == "__main__":
    main()
