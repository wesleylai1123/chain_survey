import argparse
import sys
from pathlib import Path

from PIL import ImageGrab

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.gui_app import FundamentalChainApp


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-screenshot", action="store_true", help="Exercise the window without screen recording permission.")
    args = parser.parse_args()
    app = FundamentalChainApp()
    out = ROOT / "artifacts"
    out.mkdir(exist_ok=True)
    app.geometry("1160x760+0+0")
    view = app.topic_impact_tab
    view.master.select(view)

    def capture(name):
        if args.no_screenshot:
            return
        app.update_idletasks()
        app.update()
        x, y = app.winfo_rootx(), app.winfo_rooty()
        image = ImageGrab.grab(bbox=(x, y, x + app.winfo_width(), y + app.winfo_height()))
        if all(low == high for low, high in image.getextrema()):
            raise RuntimeError("Empty screenshot")
        image.save(out / f"topic-impact-{name}.png")

    try:
        app.update()
        assert view.winfo_ismapped()
        rows = [view.products_tree.item(i, "values") for i in view.products_tree.get_children()]
        assert rows[0][:3] == ("ASIC", "正面", "+0.76"), rows
        assert any(r[:2] == ("Wi-Fi/Bluetooth Combo", "證據不足") for r in rows), rows
        assert "AI 客製化晶片" in view.product_text.get("1.0", "end")
        assert view.company_chain.tree.get_children()
        capture("ai")

        view.event_var.set("全球智慧手機需求轉弱")
        view.refresh()
        rows = [view.products_tree.item(i, "values") for i in view.products_tree.get_children()]
        assert rows[0][:2] == ("Dimensity", "負面"), rows
        assert "手機 SoC 平台需求" in view.product_text.get("1.0", "end")
        assert view.product_chain.tree.get_children()
        capture("handset")
    finally:
        app.destroy()
    print("TOPIC_IMPACT_UI_SMOKE_OK")


if __name__ == "__main__":
    main()
