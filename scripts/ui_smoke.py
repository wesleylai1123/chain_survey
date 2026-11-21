from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from PIL import ImageGrab

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from app.product_eps_dashboard import ProductEpsDashboard


OUTPUT_DIR = ROOT / "artifacts"
OUTPUT_PATH = OUTPUT_DIR / "product-eps-dashboard.png"


def capture_dashboard_screenshot(output_path: Path, app: ProductEpsDashboard | None = None) -> None:
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

    app = ProductEpsDashboard()
    app.update_idletasks()
    app.update()

    app._load_demo_scenario()
    app.update_idletasks()
    app.update()

    scenario_eps = app.metric_labels["scenario_eps"].cget("text")
    eps_change = app.metric_labels["eps_change"].cget("text")
    rows = app.result_tree.get_children()

    if scenario_eps == "-":
        raise RuntimeError("UI smoke test did not produce a scenario EPS")
    if not rows:
        raise RuntimeError("UI smoke test did not produce contribution rows")

    capture_dashboard_screenshot(OUTPUT_PATH, app)
    if not OUTPUT_PATH.exists() or OUTPUT_PATH.stat().st_size == 0:
        raise RuntimeError("UI screenshot was not created")

    print(f"UI_SMOKE_OK scenario_eps={scenario_eps} eps_change={eps_change} rows={len(rows)}")
    print(f"UI_SCREENSHOT={OUTPUT_PATH}")
    app.destroy()


if __name__ == "__main__":
    main()
