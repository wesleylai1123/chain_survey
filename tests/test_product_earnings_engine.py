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
from core.company_earnings_bridge import (
    CompanyBridgeAssumptions,
    attribute_product_contributions,
    bridge_product_impacts_to_company,
)
from core.product_earnings_engine import ProductScenario, infer_revenue_from_operating_metrics, simulate_product_scenario


class ProductEarningsEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        self._write_csv(
            "product_financials.csv",
            ["company", "ticker", "product", "period", "revenue", "currency", "revenue_mix_pct", "gross_margin_pct", "gross_profit", "source_type", "source", "confidence"],
            [
                ["TestCo", "0000.TW", "HBM", "2026Q2", 100.0, "TWD", 20.0, 40.0, 40.0, "estimated", "unit-test", 0.8],
                ["TestCo", "0000.TW", "ASIC", "2026Q2", 50.0, "TWD", 10.0, 50.0, 25.0, "estimated", "unit-test", 0.8],
            ],
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
        self.assertEqual(result["product_contributions"][0]["product"], "HBM")

    def test_multiple_products_are_aggregated_and_attributed(self) -> None:
        hbm = simulate_product_scenario(
            "TestCo",
            "HBM",
            "2026Q2",
            ProductScenario(volume_change_pct=10.0, asp_change_pct=0.0, gross_margin_change_ppt=0.0),
        )
        asic = simulate_product_scenario(
            "TestCo",
            "ASIC",
            "2026Q2",
            ProductScenario(volume_change_pct=20.0, asp_change_pct=0.0, gross_margin_change_ppt=10.0),
        )
        assumptions = CompanyBridgeAssumptions(variable_opex_pct_of_revenue_change=10.0)
        result = bridge_product_impacts_to_company("TestCo", "2026Q2", [hbm, asic], assumptions)
        contributions = result["product_contributions"]

        self.assertEqual(result["product_count"], 2)
        self.assertAlmostEqual(result["revenue_change"], 20.0)
        self.assertAlmostEqual(result["gross_profit_change"], 11.0)
        self.assertAlmostEqual(result["operating_income_change"], 9.0)
        self.assertAlmostEqual(result["eps_change"], 0.72)
        self.assertEqual([row["product"] for row in contributions], ["ASIC", "HBM"])
        self.assertAlmostEqual(sum(row["eps_change"] for row in contributions), result["product_eps_change"])
        self.assertAlmostEqual(result["non_operating_eps_change"], 0.0)
        self.assertAlmostEqual(contributions[0]["eps_change"], 0.56)
        self.assertAlmostEqual(contributions[1]["eps_change"], 0.16)
        self.assertAlmostEqual(sum(row["eps_contribution_pct"] for row in contributions), 100.0)

    def test_attribution_keeps_non_operating_change_separate(self) -> None:
        impacts = [
            {"company": "TestCo", "period": "2026Q2", "product": "HBM", "revenue_change": 20.0, "gross_profit_change": 10.0},
            {"company": "TestCo", "period": "2026Q2", "product": "ASIC", "revenue_change": -10.0, "gross_profit_change": -2.0},
        ]
        assumptions = CompanyBridgeAssumptions(
            variable_opex_pct_of_revenue_change=10.0,
            non_operating_income_change=5.0,
            effective_tax_rate_pct=20.0,
            diluted_shares=10.0,
        )
        result = bridge_product_impacts_to_company("TestCo", "2026Q2", impacts, assumptions)
        contributions = attribute_product_contributions("TestCo", "2026Q2", impacts, assumptions)

        self.assertAlmostEqual(result["product_eps_change"], 0.56)
        self.assertAlmostEqual(result["non_operating_eps_change"], 0.4)
        self.assertAlmostEqual(result["eps_change"], 0.96)
        self.assertEqual([row["product"] for row in contributions], ["HBM", "ASIC"])
        self.assertAlmostEqual(contributions[0]["eps_change"], 0.64)
        self.assertAlmostEqual(contributions[1]["eps_change"], -0.08)
        self.assertAlmostEqual(sum(row["absolute_eps_contribution_pct"] for row in contributions), 100.0)

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

        self.assertAlmostEqual(result["pre_tax_income_change"], 25.0)
        self.assertAlmostEqual(result["net_income_change"], 18.75)
        self.assertAlmostEqual(result["scenario_eps"], 4.9375)


if __name__ == "__main__":
    unittest.main()
