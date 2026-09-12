import unittest

import numpy as np
import pandas as pd

from core.panel_correlation_engine import compute_panel_correlation, prepare_panel_pair, scan_panel_correlations


class PanelCorrelationEngineTest(unittest.TestCase):
    def _panel(self) -> pd.DataFrame:
        rng = np.random.default_rng(3)
        rows = []
        companies = ["A", "B", "C", "D", "E"]
        periods = [f"Q{i:02d}" for i in range(1, 25)]
        for ci, company in enumerate(companies):
            price = 40.0 + ci * 3
            signal = 10.0 + ci
            for i, period in enumerate(periods):
                cycle = "up" if (i // 6) % 2 == 0 else "down"
                shock = rng.normal(0, 0.3)
                signal = signal + 0.4 + shock
                future_return_driver = 0.008 * shock + 0.004 * (1 if cycle == "up" else -1)
                price = price * (1 + 0.01 + future_return_driver + rng.normal(0, 0.002))
                noise = rng.normal(0, 1)
                rows.append(
                    {
                        "company": company,
                        "period": period,
                        "cycle": cycle,
                        "signal": signal,
                        "noise": noise,
                        "price": price,
                    }
                )
        return pd.DataFrame(rows)

    def test_panel_transforms_do_not_cross_company_boundaries(self):
        frame = pd.DataFrame(
            {
                "company": ["A", "A", "B", "B"],
                "period": [1, 2, 1, 2],
                "signal": [100.0, 110.0, 1000.0, 1100.0],
                "price": [10.0, 11.0, 20.0, 22.0],
            }
        )
        aligned = prepare_panel_pair(
            frame,
            "company",
            "period",
            "signal",
            "price",
            x_transform="pct_change",
            y_transform="pct_change",
        )
        self.assertEqual(len(aligned), 2)
        self.assertTrue(np.allclose(aligned["x"], [0.1, 0.1]))
        self.assertTrue(np.allclose(aligned["y"], [0.1, 0.1]))

    def test_cross_company_metrics_are_reported(self):
        frame = self._panel()
        result = compute_panel_correlation(
            frame,
            "company",
            "period",
            "signal",
            "price",
            cycle_column="cycle",
            method="spearman",
            x_transform="diff",
            y_transform="forward_return",
            min_group_samples=4,
        )
        self.assertEqual(result.entity_count, 5)
        self.assertGreater(result.sample_size, 80)
        self.assertFalse(result.company_correlations.empty)
        self.assertFalse(result.cross_sectional_correlations.empty)
        self.assertFalse(result.cycle_correlations.empty)
        self.assertGreaterEqual(result.generalization_score, 0.0)
        self.assertLessEqual(result.generalization_score, 1.0)

    def test_panel_scanner_prefers_predictive_signal_over_noise(self):
        rng = np.random.default_rng(11)
        rows = []
        companies = ["A", "B", "C", "D", "E", "F"]
        periods = list(range(30))
        for company_index, company in enumerate(companies):
            returns = rng.normal(0.01, 0.02, len(periods))
            price = 100 * np.cumprod(1 + returns)
            signal = np.roll(returns, -1)
            signal[-1] = 0.0
            noise = rng.normal(0, 1, len(periods))
            for index, period in enumerate(periods):
                rows.append(
                    {
                        "company": company,
                        "period": period,
                        "cycle": "expansion" if period < 15 else "slowdown",
                        "signal": signal[index] + company_index * 0.0001,
                        "noise": noise[index],
                        "price": price[index],
                    }
                )
        frame = pd.DataFrame(rows)
        scan = scan_panel_correlations(
            frame,
            "company",
            "period",
            "price",
            cycle_column="cycle",
            feature_columns=["signal", "noise"],
            method="pearson",
            feature_transform="level",
            target_transform="forward_return",
            lags=[0],
            min_samples=50,
            min_group_samples=4,
        )
        self.assertEqual(scan.iloc[0]["feature"], "signal")
        self.assertGreater(scan.iloc[0]["abs_pooled_correlation"], 0.8)


if __name__ == "__main__":
    unittest.main()
