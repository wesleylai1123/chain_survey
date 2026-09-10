import unittest

import pandas as pd

from core.taiwan_universe import merge_factor_batches, normalize_taiwan_stock_info, select_research_sample, slice_batch


class TaiwanUniverseTests(unittest.TestCase):
    def test_normalize_filters_non_common_securities(self):
        raw = pd.DataFrame([
            {"stock_id": "2330", "stock_name": "TSMC", "industry_category": "半導體業", "type": "twse", "date": "2026-09-01"},
            {"stock_id": "6488", "stock_name": "GlobalWafers", "industry_category": "半導體業", "type": "tpex", "date": "2026-09-01"},
            {"stock_id": "0050", "stock_name": "ETF", "industry_category": "ETF", "type": "twse", "date": "2026-09-01"},
            {"stock_id": "A123", "stock_name": "Other", "industry_category": "Other", "type": "twse", "date": "2026-09-01"},
        ])
        result = normalize_taiwan_stock_info(raw)
        self.assertEqual(result["stock_id"].tolist(), ["2330", "6488"])
        self.assertEqual(result.set_index("stock_id").loc["2330", "ticker"], "2330.TW")
        self.assertEqual(result.set_index("stock_id").loc["6488", "ticker"], "6488.TWO")

    def test_sample_and_batch_are_deterministic(self):
        universe = pd.DataFrame({
            "stock_id": ["1101", "1102", "1201", "1202", "1301", "1303"],
            "industry": ["A", "A", "B", "B", "C", "C"],
        })
        sample = select_research_sample(universe, industries=2, per_industry=2)
        self.assertEqual(len(sample), 4)
        batch = slice_batch(sample, batch_size=2, batch_index=1)
        self.assertEqual(len(batch), 2)

    def test_merge_batches_deduplicates_company_quarter(self):
        a = pd.DataFrame([
            {"stock_id": "2330", "ticker": "2330.TW", "report_date": "2024-03-31", "x": 1},
        ])
        b = pd.DataFrame([
            {"stock_id": "2330", "ticker": "2330.TW", "report_date": "2024-03-31", "x": 2},
            {"stock_id": "2454", "ticker": "2454.TW", "report_date": "2024-03-31", "x": 3},
        ])
        merged = merge_factor_batches([a, b])
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[merged["stock_id"] == "2330"].iloc[0]["x"], 2)


if __name__ == "__main__":
    unittest.main()
