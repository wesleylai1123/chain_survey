from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from PIL import ImageGrab

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from app.turnaround_radar import DEFAULT_DATASET, TurnaroundRadar

OUTPUT_DIR = ROOT / "artifacts"
OUTPUT_PATH = OUTPUT_DIR / "turnaround-radar.png"


def capture_screenshot(output_path: Path) -> None:
    if shutil.which("scrot"):
        subprocess.run(["scrot", str(output_path)], check=True)
        return
    ImageGrab.grab().save(output_path)


def main() -> None:
    if not DEFAULT_DATASET.exists():
        raise RuntimeError(f"Missing factor validation dataset: {DEFAULT_DATASET}")
    app = TurnaroundRadar(DEFAULT_DATASET)
    app.update_idletasks()
    app.update()
    if app.data.empty:
        raise RuntimeError("Turnaround Radar did not load dataset")
    if app.radar.empty:
        raise RuntimeError("Turnaround Radar did not produce ranked companies")
    if not app.radar_tree.get_children():
        raise RuntimeError("Turnaround Radar table has no rows")
    if not app.validation_tree.get_children():
        raise RuntimeError("Turnaround validation table has no rows")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    capture_screenshot(OUTPUT_PATH)
    if not OUTPUT_PATH.exists() or OUTPUT_PATH.stat().st_size == 0:
        raise RuntimeError("Turnaround Radar screenshot was not created")
    print(
        "TURNAROUND_UI_SMOKE_OK "
        f"companies={len(app.radar)} top={app.radar.iloc[0]['ticker']} "
        f"score={app.radar.iloc[0]['turnaround_score']:.1f}"
    )
    print(f"TURNAROUND_UI_SCREENSHOT={OUTPUT_PATH}")
    app.destroy()


if __name__ == "__main__":
    main()
