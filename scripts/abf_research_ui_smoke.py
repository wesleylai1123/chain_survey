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

OUT=ROOT/"artifacts"/"abf-research-lab.png"

def main() -> None:
    app=AbfResearchLab()
    app.update_idletasks(); app.update()
    if len(app.indicators)<6:
        raise RuntimeError("Indicator taxonomy incomplete")
    if app.sensitivity.empty:
        raise RuntimeError("Sensitivity table missing; history not restored")
    OUT.parent.mkdir(parents=True,exist_ok=True)
    if shutil.which("scrot"):
        subprocess.run(["scrot",str(OUT)],check=True)
    else:
        ImageGrab.grab().save(OUT)
    print(f"ABF_RESEARCH_UI_SMOKE_OK indicators={len(app.indicators)} sensitivity={len(app.sensitivity)}")
    print(f"ABF_RESEARCH_UI_SCREENSHOT={OUT}")
    app.destroy()

if __name__=="__main__":
    main()
