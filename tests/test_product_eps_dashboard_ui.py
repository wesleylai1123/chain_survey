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

from app.product_eps_dashboard import build_product_assumption_impact
from core import data_loader


class ProductEpsDashboardUiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
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
        self._write_csv(
            "company_product_relationships.csv",
            ["company", "relation", "product", "weight", "revenue_mix_pct", "gross_margin_pct"],
            [["TestCo", "produces", "CoWoS", 1.0, 20.0, 40.0]],
        )
        self._write_csv(
            "product_financials.csv",
            ["company", "ticker", "product", "period", "revenue", "currency", "revenue_mix_pct", "gross_margin_pct", "gross_profit", "source_type", "source", "confidence"],
            [["TestCo", "0000.TW", "HBM", "2026Q2", 100.0, "TWD", 20.0, 40.0, 40.0, "estimated", "unit-test", 0.8]],
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

    def test_dashboard_assumption_inputs_build_product_impact(self) -> None:
        impact = build_product_assumption_impact(
            company="TestCo",
            period="2026Q2",
            product="HBM",
            volume_change_pct="10",
            asp_change_pct="20",
            gross_margin_change_ppt="5",
        )

        self.assertEqual(impact["company"], "TestCo")
        self.assertEqual(impact["product"], "HBM")
        self.assertEqual(impact["period"], "2026Q2")
        self.assertAlmostEqual(impact["revenue_change"], 32.0)
        self.assertAlmostEqual(impact["gross_profit_change"], 19.4)
        self.assertAlmostEqual(impact["scenario_gross_margin_pct"], 45.0)

    def test_dashboard_estimates_product_snapshot_from_company_mix_when_product_financials_are_missing(self) -> None:
        impact = build_product_assumption_impact(
            company="TestCo",
            period="2026Q2",
            product="CoWoS",
            volume_change_pct="10",
            asp_change_pct="20",
            gross_margin_change_ppt="5",
        )

        self.assertAlmostEqual(impact["base_revenue"], 100.0)
        self.assertAlmostEqual(impact["base_gross_profit"], 40.0)
        self.assertAlmostEqual(impact["revenue_change"], 32.0)
        self.assertAlmostEqual(impact["gross_profit_change"], 19.4)


if __name__ == "__main__":
    unittest.main()
