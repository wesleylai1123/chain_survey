from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

from scripts.refresh_factor_validation import DATASETS, normalize_price


class FundamentalFactorSemanticsTests(unittest.TestCase):
    def test_adjusted_price_is_the_validation_target_source(self):
        self.assertEqual(DATASETS["prices"],"TaiwanStockPrice")

    def test_adjusted_price_normalization_keeps_basis(self):
        frame=pd.DataFrame([{"stock_id":"2330","date":"2026-01-02","close":100.0}])
        frame.attrs["dataset"]="TaiwanStockPriceAdj"
        out=normalize_price(frame)
        self.assertEqual(out.iloc[0]["price_basis"],"ADJUSTED_CLOSE")

    def test_factor_catalog_marks_reported_eps_as_reference(self):
        cat=pd.read_csv(Path("data/fundamental_factor_catalog.csv")).set_index("factor")
        self.assertEqual(cat.loc["eps_yoy","model_status"],"REFERENCE_ONLY")
        self.assertEqual(cat.loc["net_income_yoy","model_status"],"CALIBRATION_ELIGIBLE")
        self.assertEqual(cat.loc["future_6m_return","acquisition"],"TaiwanStockPriceAdj")
        self.assertIn("DEACCUMULATED",cat.loc["operating_cash_flow","basis"].upper())

    def test_cycle_contract_disables_small_universe(self):
        cat=pd.read_csv(Path("data/fundamental_factor_catalog.csv")).set_index("factor")
        self.assertIn("fewer than 20",cat.loc["cycle","notes"])


if __name__=="__main__":
    unittest.main()
