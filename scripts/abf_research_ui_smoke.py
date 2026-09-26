from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from PIL import ImageGrab

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from app.abf_research_lab import AbfResearchLab

OUT_DIR=ROOT/"artifacts"


def capture(app: AbfResearchLab, index: int, name: str) -> Path:
    app.book.select(index)
    app.update_idletasks()
    app.update()
    out=OUT_DIR/name
    if shutil.which("scrot"):
        subprocess.run(["scrot",str(out)],check=True)
    else:
        ImageGrab.grab().save(out)
    if not out.exists() or out.stat().st_size==0:
        raise RuntimeError(f"Screenshot missing: {out}")
    return out


def main() -> None:
    app=AbfResearchLab()
    app.update_idletasks(); app.update()
    if len(app.indicators)<6:
        raise RuntimeError("Indicator taxonomy incomplete")
    if app.sensitivity.empty:
        raise RuntimeError("Sensitivity table missing; history not restored")
    OUT_DIR.mkdir(parents=True,exist_ok=True)
    files=[
        capture(app,0,"abf-indicator-timing.png"),
        capture(app,1,"abf-scenario-evidence.png"),
        capture(app,2,"abf-data-coverage.png"),
        capture(app,3,"abf-revenue-to-gm.png"),
        capture(app,4,"abf-revenue-sensitivity.png"),
        capture(app,5,"abf-driver-sensitivity-model.png"),
    ]
    print(f"ABF_RESEARCH_UI_SMOKE_OK indicators={len(app.indicators)} sensitivity={len(app.sensitivity)}")
    for path in files:
        print(f"ABF_RESEARCH_UI_SCREENSHOT={path}")
    app.destroy()


if __name__=="__main__":
    main()
