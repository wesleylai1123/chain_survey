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


if __name__ == "__main__":
    unittest.main()
