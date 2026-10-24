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


def capture(app: AbfResearchLab, tab_name: str, name: str) -> Path:
    tab=next(tab for tab in app.book.tabs() if app.book.tab(tab,'text')==tab_name)
    app.book.select(tab)
    app.update_idletasks()
    app.update()
    out=OUT_DIR/name
    if shutil.which("scrot"):
        subprocess.run(["scrot",str(out)],check=True)
    else:
        bounds=(app.winfo_rootx(),app.winfo_rooty(),app.winfo_rootx()+app.winfo_width(),app.winfo_rooty()+app.winfo_height())
        ImageGrab.grab(bbox=bounds).save(out)
    if not out.exists() or out.stat().st_size==0:
        raise RuntimeError(f"Screenshot missing: {out}")
    return out


def main() -> None:
    app=AbfResearchLab()
    app.update_idletasks(); app.update()
    if len(app.indicators)<6:
        raise RuntimeError("Indicator taxonomy incomplete")
    if app.comparisons.empty:
        raise RuntimeError('Explicit comparison/missing-state table absent')
    if set(app.comparisons['scenario'])!={'UPSIDE','DOWNSIDE'}:
        raise RuntimeError('Independent scenario rows missing')
    if app.comparison_tree is None or len(app.comparison_tree.get_children())!=60:
        raise RuntimeError('Downside Company × Product rows not rendered')
    OUT_DIR.mkdir(parents=True,exist_ok=True)
    files=[
        capture(app,'Semantics & Stability','abf-semantics-stability.png'),
        capture(app,'Indicator Timing',"abf-indicator-timing.png"),
        capture(app,'Scenario Evidence',"abf-scenario-evidence.png"),
        capture(app,'Data Coverage',"abf-data-coverage.png"),
        capture(app,'Revenue → GM',"abf-revenue-to-gm.png"),
        capture(app,'Revenue Sensitivity',"abf-revenue-sensitivity.png"),
        capture(app,'Driver → Sensitivity → Model',"abf-driver-sensitivity-model.png"),
    ]
    print(f"ABF_RESEARCH_UI_SMOKE_OK indicators={len(app.indicators)} sensitivity={len(app.sensitivity)}")
    for path in files:
        print(f"ABF_RESEARCH_UI_SCREENSHOT={path}")
    app.destroy()


if __name__=="__main__":
    main()
