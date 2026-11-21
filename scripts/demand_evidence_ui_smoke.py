from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from PIL import ImageGrab

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from app.demand_evidence_lab import DEFAULT_EVIDENCE, DemandEvidenceLab

OUTPUT_DIR = ROOT / "artifacts"
OUTPUT_PATH = OUTPUT_DIR / "demand-evidence-lab.png"


def capture_screenshot(output_path: Path) -> None:
    if shutil.which("scrot"):
        subprocess.run(["scrot", str(output_path)], check=True)
        return
    ImageGrab.grab().save(output_path)


def main() -> None:
    app = DemandEvidenceLab(DEFAULT_EVIDENCE)
    app.update_idletasks()
    app.update()
    if app.data.empty:
        raise RuntimeError("Demand Evidence Lab did not load evidence")
    if not app.result:
        raise RuntimeError("Demand Evidence Lab did not calculate inference")
    if not app.dimension_tree.get_children():
        raise RuntimeError("Demand dimension table is empty")
    if not app.evidence_tree.get_children():
        raise RuntimeError("Evidence trace table is empty")
    if int(app.result["deduplicated_groups"]) >= int(app.result["raw_observations"]):
        raise RuntimeError("Demo did not prove evidence deduplication")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    capture_screenshot(OUTPUT_PATH)
    if not OUTPUT_PATH.exists() or OUTPUT_PATH.stat().st_size == 0:
        raise RuntimeError("Demand Evidence screenshot was not created")
    print(
        "DEMAND_EVIDENCE_UI_SMOKE_OK "
        f"score={app.result['score']} state={app.result['state']} "
        f"raw={app.result['raw_observations']} groups={app.result['deduplicated_groups']}"
    )
    print(f"DEMAND_EVIDENCE_UI_SCREENSHOT={OUTPUT_PATH}")
    app.destroy()


if __name__ == "__main__":
    main()
