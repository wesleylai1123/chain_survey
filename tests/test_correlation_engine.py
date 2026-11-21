import unittest

import numpy as np
import pandas as pd

from core.correlation_engine import (
    compute_correlation,
    prepare_pair,
    scan_correlations,
    transform_series,
)


class CorrelationEngineTest(unittest.TestCase):
    def test_perfect_positive_pearson(self):
        frame = pd.DataFrame({"x": np.arange(1, 21), "y": np.arange(1, 21) * 3.0})
        result = compute_correlation(frame, "x", "y")
        self.assertAlmostEqual(result.correlation, 1.0, places=8)
        self.assertEqual(result.sample_size, 20)

    def test_positive_lag_means_x_leads_y(self):
        x = np.arange(1, 31, dtype=float)
        y = np.concatenate(([np.nan, np.nan], x[:-2]))
        frame = pd.DataFrame({"x": x, "y": y})
        result = compute_correlation(frame, "x", "y", lag=2)
        self.assertAlmostEqual(result.correlation, 1.0, places=8)

    def test_forward_return_is_explicit_lookahead_target(self):
        series = pd.Series([100.0, 110.0, 121.0, 133.1])
        transformed = transform_series(series, "forward_return")
        self.assertAlmostEqual(transformed.iloc[0], 0.10, places=8)
        self.assertTrue(np.isnan(transformed.iloc[-1]))

    def test_pct_change_removes_common_level_trend(self):
        frame = pd.DataFrame(
            {
                "x": [10, 20, 30, 40, 50, 60],
                "y": [100, 101, 103, 106, 110, 115],
            }
        )
        raw = compute_correlation(frame, "x", "y")
        changed = compute_correlation(frame, "x", "y", x_transform="pct_change", y_transform="pct_change")
        self.assertGreater(raw.correlation, 0.9)
        self.assertLess(abs(changed.correlation), raw.correlation)

    def test_scan_ranks_predictive_feature(self):
        rng = np.random.default_rng(42)
        n = 80
        returns = rng.normal(0.01, 0.02, n)
        price = 100 * np.cumprod(1 + returns)
        leading_signal = np.roll(returns, -1)
        leading_signal[-1] = 0.0
        noise = rng.normal(0, 1, n)
        frame = pd.DataFrame({"signal": leading_signal, "noise": noise, "price": price})

        scan = scan_correlations(
            frame,
            "price",
            feature_columns=["signal", "noise"],
            method="pearson",
            feature_transform="level",
            target_transform="forward_return",
            lags=[0],
            min_samples=20,
        )
        self.assertEqual(scan.iloc[0]["feature"], "signal")
        self.assertGreater(scan.iloc[0]["abs_correlation"], 0.9)

    def test_prepare_pair_drops_nan_and_inf(self):
        frame = pd.DataFrame({"x": [1, 2, np.inf, 4], "y": [2, np.nan, 6, 8]})
        pair = prepare_pair(frame, "x", "y")
        self.assertEqual(len(pair), 2)


if __name__ == "__main__":
    unittest.main()
