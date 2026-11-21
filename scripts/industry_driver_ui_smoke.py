from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from PIL import ImageGrab

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from app.industry_driver_lab import IndustryDriverLab

OUT=ROOT/"artifacts"/"industry-driver-lab.png"

def main() -> None:
    app=IndustryDriverLab()
    app.update_idletasks(); app.update()
    if len(app.models)!=4:
        raise RuntimeError("Expected four industry models")
    if not app.model_tree.get_children():
        raise RuntimeError("Model table empty")
    if not app.driver_tree.get_children():
        raise RuntimeError("Driver table empty")
    OUT.parent.mkdir(parents=True,exist_ok=True)
    if shutil.which("scrot"):
        subprocess.run(["scrot",str(OUT)],check=True)
    else:
        ImageGrab.grab().save(OUT)
    if not OUT.exists() or OUT.stat().st_size==0:
        raise RuntimeError("Screenshot missing")
    print(f"INDUSTRY_DRIVER_UI_SMOKE_OK models={len(app.models)}")
    print(f"INDUSTRY_DRIVER_UI_SCREENSHOT={OUT}")
    app.destroy()

if __name__=="__main__":
    main()
