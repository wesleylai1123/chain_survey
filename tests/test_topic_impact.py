import unittest
from unittest.mock import patch

import pandas as pd

from core import topic_impact


class TopicImpactTests(unittest.TestCase):
    def test_analyst_mapping_cannot_inherit_unrelated_dependency_score(self):
        mappings = pd.DataFrame([{
            "source_company": "聯發科", "source_product": "Dimensity",
            "related_company": "台積電", "direction": "upstream",
            "relation": "supplier_of", "weight": 0.01, "rationale": "Custom test mapping",
        }])
        with patch.object(topic_impact, "get_managed_mappings_for_product", return_value=mappings):
            report = topic_impact.analyze_topic("聯發科", "全球智慧手機需求轉弱")
        links = {r["link"]: r for r in report["chain"] if r["company"] == "台積電" and r["product"] == "Dimensity"}
        self.assertIsNone(links["分析師設定"]["score"])
        self.assertAlmostEqual(links["3nm/4nm Wafer 生產商（產品依賴）"]["score"], -0.3848, delta=0.03)

    def test_analyst_mapping_does_not_convert_company_fx_to_product_exposure(self):
        mappings = pd.DataFrame([{
            "source_company": "聯發科", "source_product": "ASIC",
            "related_company": "台積電", "direction": "upstream",
            "relation": "supplier_of", "weight": 0.85, "rationale": "Custom test mapping",
        }])
        with patch.object(topic_impact, "get_managed_mappings_for_product", return_value=mappings):
            report = topic_impact.analyze_topic("聯發科", "美元兌新台幣升值")
        self.assertTrue(all(row["score"] is None for row in report["products"]))

    def test_ai_topic_identifies_direct_asic_exposure(self):
        report = topic_impact.analyze_topic("聯發科", "AI 基礎建設資本支出加速")
        products = {row["product"]: row for row in report["products"]}
        asic = products["ASIC"]

        self.assertEqual(report["relevance"], "高")
        self.assertEqual(report["direction"], "正面")
        self.assertAlmostEqual(asic["score"], 0.8 * 0.95)
        self.assertIn("直接", asic["exposure"])
        self.assertIn("AI 客製化晶片", asic["paths"][0]["reason"])
        self.assertIn("ASIC", asic["paths"][0]["path"])
        self.assertIsNone(asic["revenue_mix_pct"])
        self.assertEqual(asic["relationship_weight"], 0.5)
        self.assertIsNone(products["Wi-Fi/Bluetooth Combo"]["score"])
        tsmc = next(row for row in report["chain"] if row["company"] == "台積電" and row["product"] is None)
        self.assertGreater(tsmc["score"], 0)
        self.assertEqual(tsmc["role"], "上游")

    def test_handset_selloff_distinguishes_direct_and_indirect_products(self):
        report = topic_impact.analyze_topic("聯發科", "全球智慧手機需求轉弱")
        products = {row["product"]: row for row in report["products"]}

        self.assertEqual(report["direction"], "負面")
        self.assertAlmostEqual(products["Dimensity"]["score"], -0.8075)
        self.assertAlmostEqual(products["PMIC"]["score"], -0.595)
        self.assertIsNone(products["ASIC"]["score"])
        self.assertTrue(any(path["layer"] == 2 and path["cumulative_lag"] == 1
                            for path in products["Dimensity"]["paths"]))
        dimensity_suppliers = [
            row for row in report["chain"]
            if row["product"] == "Dimensity" and row["role"] == "上游"
        ]
        self.assertIn("台積電", [row["company"] for row in dimensity_suppliers])
        self.assertTrue(any(row["score"] is not None for row in dimensity_suppliers))

    def test_company_only_fx_exposure_does_not_score_products(self):
        report = topic_impact.analyze_topic("聯發科", "美元兌新台幣升值")

        self.assertEqual(report["direction"], "正面")
        self.assertTrue(report["products"])
        self.assertTrue(all(row["score"] is None for row in report["products"]))
        self.assertIn("公司", report["summary"])

    def test_company_can_have_indirect_exposure_without_product_rows(self):
        report = topic_impact.analyze_topic("小米", "美元兌新台幣升值")
        self.assertEqual(report["products"], [])
        self.assertEqual(report["relevance"], "低")
        self.assertEqual(report["direction"], "正面")


if __name__ == "__main__":
    unittest.main()
