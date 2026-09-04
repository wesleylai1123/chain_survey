from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from core import data_loader
from core.company_earnings_bridge import CompanyBridgeAssumptions, bridge_product_impacts_to_company
from core.product_earnings_engine import ProductScenario, infer_revenue_from_operating_metrics, simulate_product_scenario


class ProductEarningsEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        self._write_csv(
            "product_financials.csv",
            ["company", "ticker", "product", "period", "revenue", "currency", "revenue_mix_pct", "gross_margin_pct", "gross_profit", "source_type", "source", "confidence"],
            [["TestCo", "0000.TW", "HBM", "2026Q2", 100.0, "TWD", 20.0, 40.0, 40.0, "estimated", "unit-test", 0.8]],
        )
        self._write_csv(
            "product_operating_metrics.csv",
            ["company", "ticker", "product", "period", "metric", "value", "unit", "source_type", "source", "confidence"],
            [
                ["TestCo", "0000.TW", "HBM", "2026Q2", "volume", 10.0, "units", "estimated", "unit-test", 0.8],
                ["TestCo", "0000.TW", "HBM", "2026Q2", "asp", 8.0, "TWD_per_unit", "estimated", "unit-test", 0.8],
            ],
        )
        self._write_csv(
            "quarterly_financials.csv",
            [
                "company",
                "ticker",
                "period",
                "revenue",
                "gross_profit",
                "operating_income",
                "pre_tax_income",
                "net_income",
                "eps",
                "total_assets",
                "total_liabilities",
                "total_equity",
                "book_value_per_share",
                "source_date",
                "source",
            ],
            [["TestCo", "0000.TW", "2026Q2", 500.0, 200.0, 100.0, 100.0, 80.0, 8.0, 1000.0, 400.0, 600.0, 60.0, "2026-08-01", "unit-test"]],
        )
        self.data_dir_patch = patch.object(data_loader, "DATA_DIR", self.data_dir)
        self.data_dir_patch.start()
        data_loader.clear_data_caches()

    def tearDown(self) -> None:
        data_loader.clear_data_caches()
        self.data_dir_patch.stop()
        self.temp_dir.cleanup()

    def _write_csv(self, name: str, header: list[str], rows: list[list[object]]) -> None:
        with open(self.data_dir / name, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            writer.writerows(rows)

    def test_revenue_is_volume_times_asp(self) -> None:
        result = infer_revenue_from_operating_metrics("TestCo", "HBM", "2026Q2")
        self.assertEqual(result["implied_revenue"], 80.0)

    def test_scenario_bridges_volume_asp_and_margin_to_gross_profit(self) -> None:
        result = simulate_product_scenario(
            "TestCo",
            "HBM",
            "2026Q2",
            ProductScenario(volume_change_pct=10.0, asp_change_pct=20.0, gross_margin_change_ppt=5.0),
        )
        self.assertAlmostEqual(result["scenario_revenue"], 132.0)
        self.assertAlmostEqual(result["scenario_gross_profit"], 59.4)
        self.assertAlmostEqual(result["gross_profit_change"], 19.4)

    def test_product_impact_rolls_into_company_eps(self) -> None:
        product_impact = simulate_product_scenario(
            "TestCo",
            "HBM",
            "2026Q2",
            ProductScenario(volume_change_pct=10.0, asp_change_pct=20.0, gross_margin_change_ppt=5.0),
        )
        result = bridge_product_impacts_to_company(
            "TestCo",
            "2026Q2",
            [product_impact],
            CompanyBridgeAssumptions(variable_opex_pct_of_revenue_change=10.0),
        )

        # Product scenario: revenue +32, gross profit +19.4.
        # Variable OPEX = 3.2, so operating income +16.2.
        # Baseline effective tax rate = 20%, shares = 80 / 8 = 10.
        # Net income +12.96 and EPS +1.296.
        self.assertAlmostEqual(result["revenue_change"], 32.0)
        self.assertAlmostEqual(result["gross_profit_change"], 19.4)
        self.assertAlmostEqual(result["variable_opex_change"], 3.2)
        self.assertAlmostEqual(result["operating_income_change"], 16.2)
        self.assertAlmostEqual(result["effective_tax_rate_pct"], 20.0)
        self.assertAlmostEqual(result["diluted_shares"], 10.0)
        self.assertAlmostEqual(result["net_income_change"], 12.96)
        self.assertAlmostEqual(result["scenario_eps"], 9.296)
        self.assertAlmostEqual(result["eps_change"], 1.296)
        self.assertAlmostEqual(result["eps_change_pct"], 16.2)

    def test_bridge_supports_explicit_tax_and_share_overrides(self) -> None:
        product_impact = {
            "company": "TestCo",
            "period": "2026Q2",
            "revenue_change": 50.0,
            "gross_profit_change": 30.0,
        }
        result = bridge_product_impacts_to_company(
            "TestCo",
            "2026Q2",
            [product_impact],
            CompanyBridgeAssumptions(
                variable_opex_pct_of_revenue_change=20.0,
                non_operating_income_change=5.0,
                effective_tax_rate_pct=25.0,
                diluted_shares=20.0,
            ),
        )

        # GP +30 - OPEX +10 + non-op +5 = pre-tax +25.
        # After 25% tax: NI +18.75; with 20 shares EPS becomes (80+18.75)/20.
        self.assertAlmostEqual(result["pre_tax_income_change"], 25.0)
        self.assertAlmostEqual(result["net_income_change"], 18.75)
        self.assertAlmostEqual(result["scenario_eps"], 4.9375)


if __name__ == "__main__":
    unittest.main()
