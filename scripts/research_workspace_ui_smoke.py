from pathlib import Path
import argparse
import sys

from PIL import ImageGrab

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.research_workspace import ResearchWorkspace


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-screenshot", action="store_true")
    args = parser.parse_args()
    app = ResearchWorkspace()
    errors = []
    app.report_callback_exception = lambda _kind, error, _trace: errors.append(error)
    out = ROOT / "artifacts"
    out.mkdir(exist_ok=True)

    def capture(name):
        app.update()
        if errors:
            raise errors[0]
        if args.no_screenshot:
            return
        x, y = app.winfo_rootx(), app.winfo_rooty()
        image = ImageGrab.grab(bbox=(x, y, x + app.winfo_width(), y + app.winfo_height()))
        assert any(low < high for low, high in image.getextrema())
        image.save(out / f"research-workspace-{name}.png")

    try:
        assert app.dataset is not None and app.report is not None
        assert len(app.report.samples) >= 18
        app.geometry("1360x850+0+0")
        capture("analysis")
        assert len(app.scatter.collections) == 2
        assert app.report.rolling.notna().any()
        assert app.chart_note.winfo_height() >= app.chart_note.winfo_reqheight()

        app.geometry("1100x720+0+0")
        app.book.select(1)
        capture("scan")
        cell = app.cells["pcb_material_revenue_yoy", 2].winfo_children()[0]
        cell.event_generate("<Button-1>")
        app.update()
        assert app.book.index("current") == 0 and app.lag.get() == "+2"
        assert app.tiles["score"].cget("text") == f"{app.report.coefficient:+.3f}"

        app.book.select(2)
        capture("samples")
        assert len(app.tree.get_children()) == len(app.report.samples)
        assert app.evidence_text.winfo_height() >= app.evidence_text.winfo_reqheight()
        assert "申報期限代理" in app.evidence_text.get("1.0", "end")
    finally:
        app.destroy()
    print("RESEARCH_WORKSPACE_UI_OK")


if __name__ == "__main__":
    main()
