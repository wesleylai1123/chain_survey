from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from PIL import ImageGrab

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from app.free_evidence_dashboard import FreeEvidenceDashboard

OUT=ROOT/"artifacts"/"free-evidence-dashboard.png"


def main() -> None:
    app=FreeEvidenceDashboard()
    app.update_idletasks(); app.update()
    if not app.status:
        raise RuntimeError("Free evidence status not loaded")
    if int(app.status.get("sources_ok",0)) < 1:
        raise RuntimeError("No free evidence source succeeded")
    OUT.parent.mkdir(parents=True,exist_ok=True)
    if shutil.which("scrot"):
        subprocess.run(["scrot",str(OUT)],check=True)
    else:
        ImageGrab.grab().save(OUT)
    if not OUT.exists() or OUT.stat().st_size==0:
        raise RuntimeError("Free evidence screenshot missing")
    print(
        "FREE_EVIDENCE_UI_SMOKE_OK "
        f"sources_ok={app.status.get('sources_ok')} evidence_rows={app.status.get('evidence_rows')}"
    )
    print(f"FREE_EVIDENCE_UI_SCREENSHOT={OUT}")
    app.destroy()


if __name__=="__main__":
    main()
