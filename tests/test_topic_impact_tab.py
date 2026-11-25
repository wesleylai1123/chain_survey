from __future__ import annotations

import subprocess
import sys
import tkinter as tk
import unittest
from tkinter import ttk

from app.topic_impact_tab import TopicImpactTab


AI_EVENT = "AI 基礎建設資本支出加速"
PATH_REASON = "客戶擴增加速器訂單，帶動資料中心晶片需求。"


def product(name, direction="證據不足", score=None, positive=None, negative=None, paths=()):
    return {
        "product": name,
        "direction": direction,
        "score": score,
        "positive_score": positive,
        "negative_score": negative,
        "exposure": "直接及間接" if paths else "無產品路徑",
        "relationship_weight": 0.8,
        "revenue_mix_pct": 12.5 if paths else None,
        "revenue_mix_period": "2025Q4" if paths else None,
        "paths": list(paths),
    }


def chain(company, product_name=None):
    return {
        "company": company,
        "role": "上游",
        "product": product_name,
        "link": "供應製程",
        "score": -0.42,
        "positive_score": None,
        "negative_score": -0.42,
        "direction": "負面",
        "path": "製程 → 晶片",
        "reason": "產能配置調整影響交期。",
        "cumulative_lag": 2,
        "paths": [],
    }


def analyze_fixture(company, event):
    return {
        "company": company,
        "event": event,
        "description": "AI 伺服器資本支出增加。",
        "relevance": "高",
        "direction": "混合",
        "summary": "加速器需求與製程成本同時影響產品。",
        "products": [
            product("手機 SoC"),
            product("網通晶片", "負面", score=-0.6, negative=-0.6),
            product(
                "ASIC", "混合", positive=0.84, negative=-0.51,
                paths=(
                    dict(path="AI 資本支出 → ASIC", reason=PATH_REASON * 12,
                         layer=0, cumulative_lag=0, signed_score=0.84),
                    dict(path="製程成本 → ASIC", reason="先進製程報價上升。",
                         layer=1, cumulative_lag=2, signed_score=-0.51),
                ),
            ),
        ],
        "chain": [
            chain("公司合作夥伴"),
            chain("ASIC 供應商", "ASIC"),
            chain("網通供應商", "網通晶片"),
        ],
    }


class TopicImpactTabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.platform == "darwin":
            # Aqua can abort the process before Tk raises a Python exception.
            probe = subprocess.run(
                [sys.executable, "-c", "import tkinter as tk; tk.Tk().destroy()"],
                capture_output=True,
            )
            if probe.returncode:
                raise unittest.SkipTest("Aqua Tk needs a desktop session")

    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            if "display" in str(error):
                self.skipTest(str(error))
            raise
        self.addCleanup(self.root.destroy)
        self.root.geometry("1160x760")
        self.root.tk.call("tk", "scaling", 2.0)
        ttk.Style(self.root).theme_use("clam")

    def make_tab(self, analyze=analyze_fixture, companies=("台積電", "聯發科"),
                 events=("台積電先進製程漲價", AI_EVENT)):
        notebook = ttk.Notebook(self.root, padding=16)
        notebook.pack(fill="both", expand=True)
        notebook.add(ttk.Frame(notebook), text="其他分頁")
        tab = TopicImpactTab(notebook, companies, events, analyze)
        notebook.add(tab, text="題材影響分析")
        notebook.select(tab)
        self.root.update()
        return tab

    def tree_rows(self, tree):
        return [tree.item(item, "values") for item in tree.get_children()]

    def test_default_analysis_orders_products_and_renders_wrapped_evidence(self):
        calls = []

        def analyze(company, event):
            calls.append((company, event))
            return analyze_fixture(company, event)

        tab = self.make_tab(analyze)
        self.assertEqual(calls, [("聯發科", AI_EVENT)])
        rows = self.tree_rows(tab.products_tree)
        self.assertEqual([row[0] for row in rows], ["ASIC", "網通晶片", "手機 SoC"])
        self.assertIn("混合", rows[0])
        self.assertIn("無產品路徑", rows[-1])
        self.assertEqual(str(tab.products_tree.cget("selectmode")), "browse")
        self.assertEqual(tab.products_tree.selection(), tab.products_tree.get_children()[:1])
        self.assertIn("影響方向　混合", tab.result_label.cget("text"))
        self.assertIn("加速器需求", tab.summary_text.get("1.0", "end"))
        self.assertEqual(str(tab.product_text.cget("wrap")), "word")
        self.assertEqual(str(tab.product_text.cget("state")), "disabled")
        evidence = tab.product_text.get("1.0", "end")
        for value in ("+0.84", "-0.51", "12.5%", "2025Q4", "AI 資本支出 → ASIC", PATH_REASON,
                      "先進製程報價上升", "累計落後　0"):
            self.assertIn(value, evidence)
        self.assertGreater(tab.products_tree.winfo_height(), 100)
        self.assertGreater(tab.product_text.winfo_width(), 250)
        self.assertLessEqual(
            tab.product_text.winfo_rootx() + tab.product_text.winfo_width(),
            self.root.winfo_rootx() + self.root.winfo_width(),
        )

    def test_selected_product_chain_excludes_other_products_and_company_context(self):
        tab = self.make_tab()
        self.assertEqual([row[0] for row in self.tree_rows(tab.product_chain.tree)], ["ASIC 供應商"])
        self.assertEqual([row[0] for row in self.tree_rows(tab.company_chain.tree)], ["公司合作夥伴"])

        tab.products_tree.selection_set(tab.products_tree.get_children()[1])
        self.root.update()
        self.assertEqual([row[0] for row in self.tree_rows(tab.product_chain.tree)], ["網通供應商"])
        self.assertEqual([row[0] for row in self.tree_rows(tab.company_chain.tree)], ["公司合作夥伴"])
        for value in ("供應製程", "負面", "累計落後　2", "製程 → 晶片", "產能配置調整"):
            self.assertIn(value, tab.product_chain.evidence.get("1.0", "end"))

        tab.products_tree.selection_set(tab.products_tree.get_children()[-1])
        self.root.update()
        self.assertEqual(self.tree_rows(tab.product_chain.tree), [])
        self.assertIn("沒有供應鏈資料", tab.product_chain.evidence.get("1.0", "end"))
        self.assertIn("沒有可追溯", tab.product_text.get("1.0", "end"))

    def test_failed_refresh_clears_previous_results_and_recovers(self):
        failing = False

        def analyze(company, event):
            if failing:
                raise ValueError("事件資料缺漏")
            return analyze_fixture(company, event)

        tab = self.make_tab(analyze, companies=("台積電",), events=("台積電先進製程漲價",))
        self.assertEqual(tab.company_var.get(), "台積電")
        self.assertEqual(tab.event_var.get(), "台積電先進製程漲價")
        failing = True
        tab.refresh()
        self.root.update()
        self.assertEqual(self.tree_rows(tab.products_tree), [])
        self.assertEqual(self.tree_rows(tab.company_chain.tree), [])
        self.assertIn("事件資料缺漏", tab.summary_text.get("1.0", "end"))
        failing = False
        tab.refresh()
        self.root.update()
        self.assertEqual(len(self.tree_rows(tab.products_tree)), 3)

    def test_mixed_chain_evidence_shows_both_extremes_and_each_path_once(self):
        def analyze(company, event):
            result = analyze_fixture(company, event)
            result["chain"][1].update(
                direction="混合", score=None, positive_score=0.72, negative_score=-0.53,
                path="AI 資本支出 → 供應商", reason="合作關係仍有效｜加速器訂單上修。",
                cumulative_lag=1,
                paths=[
                    dict(path="AI 資本支出 → 供應商", reason="加速器訂單上修。",
                         layer=1, cumulative_lag=1, signed_score=0.72),
                    dict(path="製程成本 → 供應商", reason="產能配置調整。",
                         layer=2, cumulative_lag=3, signed_score=-0.53),
                ],
            )
            return result

        tab = self.make_tab(analyze)
        row, = self.tree_rows(tab.product_chain.tree)
        self.assertIn("+0.72 / -0.53", row)
        evidence = tab.product_chain.evidence.get("1.0", "end")
        for value in ("合作關係仍有效", "最強正面分數　+0.72", "最強負面分數　-0.53",
                      "製程成本 → 供應商", "產能配置調整", "累計落後　1", "累計落後　3"):
            self.assertIn(value, evidence)
        self.assertEqual(evidence.count("AI 資本支出 → 供應商"), 1)
        self.assertEqual(evidence.count("加速器訂單上修。"), 1)


if __name__ == "__main__":
    unittest.main()
