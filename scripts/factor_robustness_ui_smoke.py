from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from PIL import ImageGrab

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from app.factor_robustness_lab import DEFAULT_DATASET, FactorRobustnessLab

OUTPUT_DIR = ROOT / "artifacts"
OUTPUT_PATH = OUTPUT_DIR / "factor-robustness-lab.png"


def capture_screenshot(output_path: Path) -> None:
    if shutil.which("scrot"):
        subprocess.run(["scrot", str(output_path)], check=True)
        return
    ImageGrab.grab().save(output_path)


def main() -> None:
    if not DEFAULT_DATASET.exists():
        raise RuntimeError(f"Missing factor validation dataset: {DEFAULT_DATASET}")
    app = FactorRobustnessLab(DEFAULT_DATASET)
    app.update_idletasks()
    app.update()
    if app.data.empty:
        raise RuntimeError("Robustness UI did not load dataset")
    if not app.tree.get_children():
        raise RuntimeError("Robustness scan produced no rows")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    capture_screenshot(OUTPUT_PATH)
    if not OUTPUT_PATH.exists() or OUTPUT_PATH.stat().st_size == 0:
        raise RuntimeError("Robustness screenshot was not created")
    print(f"FACTOR_ROBUSTNESS_UI_SMOKE_OK rows={len(app.data)} results={len(app.tree.get_children())}")
    print(f"FACTOR_ROBUSTNESS_UI_SCREENSHOT={OUTPUT_PATH}")
    app.destroy()


if __name__ == "__main__":
    main()
