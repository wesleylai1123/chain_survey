from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from core import data_loader
from core import guidance_service
from core import guidance_verification


class GuidanceVerificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        shutil.copy(ROOT / "data" / "company_master.csv", self.data_dir / "company_master.csv")

        self.data_dir_patch = patch.object(data_loader, "DATA_DIR", self.data_dir)
        self.data_dir_patch.start()
        data_loader.clear_data_caches()

        self._write_quarterly_financials()
        self.doc_id = guidance_service.register_source_document(
            ticker="2330.TW",
            file_path="data/raw_transcripts/2330.TW/114Q2.pdf",
            source_quarter="114Q2",
            call_date="2025-07-18",
        )["doc_id"]

    def tearDown(self) -> None:
        data_loader.clear_data_caches()
        self.data_dir_patch.stop()
        self.temp_dir.cleanup()

    def _write_quarterly_financials(self) -> None:
        header = (
            "company,ticker,period,revenue,gross_profit,operating_income,pre_tax_income,"
            "net_income,eps,total_assets,total_liabilities,total_equity,book_value_per_share,"
            "source_date,source\n"
        )
        # 114Q2 revenue=1000 margin=50%% ; 114Q3 revenue=1150 (+15%%) margin=52%% (+2pp)
        rows = (
            "台積電,2330.TW,114Q2,1000,500,400,410,380,10,5000,2000,3000,100,20250718,test\n"
            "台積電,2330.TW,114Q3,1150,598,470,480,440,11,5200,2100,3100,102,20251018,test\n"
        )
        (self.data_dir / "quarterly_financials.csv").write_text(header + rows, encoding="utf-8")
        data_loader.clear_data_caches()

    def _confirmed_claim(self, **overrides: object) -> dict[str, object]:
        defaults = dict(
            doc_id=self.doc_id,
            ticker="2330.TW",
            source_quarter="114Q2",
            target_period="114Q3",
            category="revenue_growth",
            product_or_segment=None,
            direction="up",
            quant_low=10.0,
            quant_high=15.0,
            raw_text="We expect Q3 revenue to grow 10-15%% sequentially.",
        )
        defaults.update(overrides)
        claim = guidance_service.add_claim(**defaults)
        return guidance_service.confirm_claim(claim["claim_id"], reviewed_by="analyst")

    def test_revenue_growth_claim_within_range_matches(self) -> None:
        claim = self._confirmed_claim()
        result, actual_value, _note = guidance_verification.evaluate_claim(_as_series(claim))
        self.assertEqual(result, "match")
        self.assertAlmostEqual(actual_value, 15.0, places=1)

    def test_revenue_growth_claim_right_direction_outside_range_is_partial(self) -> None:
        claim = self._confirmed_claim(quant_low=1.0, quant_high=5.0)
        result, _actual_value, _note = guidance_verification.evaluate_claim(_as_series(claim))
        self.assertEqual(result, "partial")

    def test_revenue_growth_claim_wrong_direction_misses(self) -> None:
        claim = self._confirmed_claim(direction="down", quant_low=None, quant_high=None)
        result, _actual_value, _note = guidance_verification.evaluate_claim(_as_series(claim))
        self.assertEqual(result, "miss")

    def test_product_line_claim_uses_directional_proxy(self) -> None:
        claim = self._confirmed_claim(
            category="product_line",
            product_or_segment="Advanced Packaging",
            direction="up",
            quant_low=None,
            quant_high=None,
        )
        result, _actual_value, note = guidance_verification.evaluate_claim(_as_series(claim))
        self.assertEqual(result, "match")
        self.assertIn("revenue and margin", note)

    def test_capex_claim_is_unverifiable(self) -> None:
        claim = self._confirmed_claim(category="capex", quant_low=None, quant_high=None)
        result, actual_value, _note = guidance_verification.evaluate_claim(_as_series(claim))
        self.assertEqual(result, "unverifiable")
        self.assertIsNone(actual_value)

    def test_run_verification_writes_outcomes_for_all_confirmed_claims(self) -> None:
        self._confirmed_claim()
        self._confirmed_claim(category="capex", quant_low=None, quant_high=None)

        outcomes = guidance_verification.run_verification()
        self.assertEqual(len(outcomes), 2)
        self.assertEqual(set(outcomes["match_result"]), {"match", "unverifiable"})

        reloaded = data_loader.load_claim_outcomes()
        self.assertEqual(len(reloaded), 2)

    def test_compute_credibility_score_averages_resolved_outcomes(self) -> None:
        self._confirmed_claim()  # match -> 1.0
        self._confirmed_claim(direction="down", quant_low=None, quant_high=None)  # miss -> 0.0
        self._confirmed_claim(category="capex", quant_low=None, quant_high=None)  # unverifiable -> excluded
        guidance_verification.run_verification()

        score = guidance_verification.compute_credibility_score("2330.TW")
        self.assertAlmostEqual(score, 0.5, places=2)

    def test_compute_credibility_score_returns_none_when_nothing_resolved(self) -> None:
        self._confirmed_claim(category="capex", quant_low=None, quant_high=None)
        guidance_verification.run_verification()
        self.assertIsNone(guidance_verification.compute_credibility_score("2330.TW"))

    def test_non_adjacent_previous_quarter_is_unverifiable(self) -> None:
        # 113Q4 -> 114Q3 is a three-quarter gap, not a QoQ baseline. Revenue
        # rises 15% across the gap, so without an adjacency check this would
        # score a false "match".
        header = (
            "company,ticker,period,revenue,gross_profit,operating_income,pre_tax_income,"
            "net_income,eps,total_assets,total_liabilities,total_equity,book_value_per_share,"
            "source_date,source\n"
        )
        rows = (
            "台積電,2330.TW,113Q4,1000,500,400,410,380,10,5000,2000,3000,100,20241018,test\n"
            "台積電,2330.TW,114Q3,1150,598,470,480,440,11,5200,2100,3100,102,20251018,test\n"
        )
        (self.data_dir / "quarterly_financials.csv").write_text(header + rows, encoding="utf-8")
        data_loader.clear_data_caches()

        claim = self._confirmed_claim()
        result, actual_value, _note = guidance_verification.evaluate_claim(_as_series(claim))
        self.assertEqual(result, "unverifiable")
        self.assertIsNone(actual_value)

    def test_gross_margin_claim_against_nan_baseline_is_unverifiable(self) -> None:
        # 114Q2 has revenue=0, so its computed gross_margin is NaN. A NaN
        # baseline must be unverifiable, not a confident "miss".
        header = (
            "company,ticker,period,revenue,gross_profit,operating_income,pre_tax_income,"
            "net_income,eps,total_assets,total_liabilities,total_equity,book_value_per_share,"
            "source_date,source\n"
        )
        rows = (
            "台積電,2330.TW,114Q2,0,0,0,0,0,0,5000,2000,3000,100,20250718,test\n"
            "台積電,2330.TW,114Q3,1150,598,470,480,440,11,5200,2100,3100,102,20251018,test\n"
        )
        (self.data_dir / "quarterly_financials.csv").write_text(header + rows, encoding="utf-8")
        data_loader.clear_data_caches()

        claim = self._confirmed_claim(
            category="gross_margin",
            direction="up",
            quant_low=None,
            quant_high=None,
        )
        result, actual_value, _note = guidance_verification.evaluate_claim(_as_series(claim))
        self.assertEqual(result, "unverifiable")
        self.assertIsNone(actual_value)


def _as_series(row: dict[str, object]):
    import pandas as pd

    return pd.Series(row)


if __name__ == "__main__":
    unittest.main()
