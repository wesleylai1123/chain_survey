from __future__ import annotations

import unittest
import numpy as np
import pandas as pd

from core.abf_margin_transmission import MarginScanConfig, scan_revenue_to_margin


class AbfMarginTransmissionTests(unittest.TestCase):
    def _panel(self) -> pd.DataFrame:
        rng=np.random.default_rng(7)
        rows=[]
        for ticker in ("3037.TW","3189.TW","8046.TW"):
            rev=np.linspace(-0.3,0.5,16)+rng.normal(0,0.03,16)
            gm=0.18+0.05*np.roll(rev,1)+rng.normal(0,0.005,16)
            for i,date in enumerate(pd.date_range("2021-03-31",periods=16,freq="Q")):
                rows.append({
                    "ticker":ticker,
                    "report_date":date.date().isoformat(),
                    "available_date":(date+pd.Timedelta(days=60)).date().isoformat(),
                    "monthly_revenue_3m_yoy":rev[i],
                    "revenue_yoy":rev[i],
                    "gross_margin_qoq":gm[i]-gm[i-1] if i else np.nan,
                    "gross_margin_yoy_delta":gm[i]-gm[i-4] if i>=4 else np.nan,
                })
        return pd.DataFrame(rows)

    def test_scans_quarter_lags(self) -> None:
        result=scan_revenue_to_margin(
            self._panel(),
            config=MarginScanConfig(min_samples=12,permutation_iterations=100),
        )
        self.assertFalse(result.empty)
        self.assertTrue(set(result["lag_quarters"]) <= {0,1,2})
        self.assertIn("monthly_revenue_3m_yoy",set(result["feature"]))
        self.assertIn("gross_margin_qoq",set(result["target"]))


if __name__=="__main__":
    unittest.main()
