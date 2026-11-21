import unittest

import numpy as np
import pandas as pd

from core.factor_validation_engine import industry_neutralize, validate_factor_oos


class FactorValidationEngineTests(unittest.TestCase):
    def setUp(self):
        rows = []
        for t in range(12):
            period = f"202{t // 4}Q{t % 4 + 1}"
            for industry, tickers in {"A": ["A1", "A2", "A3"], "B": ["B1", "B2", "B3"]}.items():
                industry_bias = 5 if industry == "A" else -4
                for i, ticker in enumerate(tickers):
                    factor = industry_bias + i + t * 0.4
                    future = 0.03 * i + 0.01 * t
                    rows.append({
                        "ticker": ticker,
                        "report_date": period,
                        "industry": industry,
                        "cycle": "Expansion" if t % 2 == 0 else "Recovery",
                        "factor": factor,
                        "future_6m_return": future,
                    })
        self.frame = pd.DataFrame(rows)

    def test_industry_neutralize_zero_group_mean(self):
        residual = industry_neutralize(self.frame, "factor")
        check = pd.DataFrame({"r": residual, "industry": self.frame["industry"], "time": self.frame["report_date"]})
        means = check.groupby(["time", "industry"])["r"].mean().abs()
        self.assertTrue((means < 1e-12).all())

    def test_oos_validation_returns_both_periods(self):
        result = validate_factor_oos(
            self.frame,
            "factor",
            "future_6m_return",
            industry_neutral=True,
            train_fraction=0.67,
            min_group_samples=2,
        )
        self.assertGreater(result.in_sample_samples, 0)
        self.assertGreater(result.out_of_sample_samples, 0)
        self.assertFalse(np.isnan(result.in_sample_correlation))
        self.assertFalse(np.isnan(result.out_of_sample_correlation))
        self.assertTrue(result.direction_consistent)


if __name__ == "__main__":
    unittest.main()
