from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from PIL import ImageGrab

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from app.factor_validation_lab import DEFAULT_DATASET, FactorValidationLab

OUTPUT_DIR = ROOT / "artifacts"
OUTPUT_PATH = OUTPUT_DIR / "factor-validation-lab.png"


def capture_screenshot(output_path: Path) -> None:
    if shutil.which("scrot"):
        subprocess.run(["scrot", str(output_path)], check=True)
        return
    screenshot = ImageGrab.grab()
    screenshot.save(output_path)


def main() -> None:
    if not DEFAULT_DATASET.exists():
        raise RuntimeError(f"Missing factor validation dataset: {DEFAULT_DATASET}")
    app = FactorValidationLab(DEFAULT_DATASET)
    app.update_idletasks()
    app.update()
    if app.data.empty:
        raise RuntimeError("Factor validation UI did not load dataset")
    if app.metric_vars["rows"].get() in {"-", "0"}:
        raise RuntimeError("Factor validation UI did not calculate dataset metrics")
    if not app.scan_tree.get_children():
        raise RuntimeError("Factor scanner did not produce rows")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    capture_screenshot(OUTPUT_PATH)
    if not OUTPUT_PATH.exists() or OUTPUT_PATH.stat().st_size == 0:
        raise RuntimeError("Factor validation screenshot was not created")
    print(f"FACTOR_VALIDATION_UI_SMOKE_OK rows={len(app.data)} factors={app.metric_vars['factors'].get()}")
    print(f"FACTOR_VALIDATION_UI_SCREENSHOT={OUTPUT_PATH}")
    app.destroy()


if __name__ == "__main__":
    main()
