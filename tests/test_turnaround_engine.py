from __future__ import annotations

import unittest

import pandas as pd

from core.turnaround_engine import build_turnaround_history, build_turnaround_radar, validate_turnaround_signal


class TurnaroundEngineTests(unittest.TestCase):
    @staticmethod
    def _panel() -> pd.DataFrame:
        periods = ["2024-03-31", "2024-06-30", "2024-09-30", "2024-12-31", "2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31"]
        rows = []
        for idx, period in enumerate(periods):
            # A is moving from contraction into broad-based recovery.
            a_growth = -0.22 + idx * 0.055
            rows.append(
                {
                    "ticker": "1111",
                    "name": "Improver",
                    "industry": "Semiconductor",
                    "report_date": period,
                    "cycle": "Recovery" if idx >= 5 else "Contraction",
                    "monthly_revenue_3m_yoy": a_growth,
                    "revenue_yoy": a_growth,
                    "gross_margin": 0.18 + idx * 0.012,
                    "gross_margin_qoq": 0.012,
                    "operating_margin": 0.07 + idx * 0.010,
                    "eps_yoy": -0.40 + idx * 0.14,
                    "inventory_yoy": 0.35 - idx * 0.06,
                    "ocf_margin": 0.05 + idx * 0.012,
                    "future_3m_return": 0.10 + idx * 0.01,
                    "future_6m_return": 0.18 + idx * 0.01,
                    "future_12m_return": 0.25 + idx * 0.01,
                }
            )
            # B has the opposite operating trajectory.
            b_growth = 0.25 - idx * 0.055
            rows.append(
                {
                    "ticker": "2222",
                    "name": "Deteriorator",
                    "industry": "Semiconductor",
                    "report_date": period,
                    "cycle": "Slowdown" if idx >= 5 else "Expansion",
                    "monthly_revenue_3m_yoy": b_growth,
                    "revenue_yoy": b_growth,
                    "gross_margin": 0.32 - idx * 0.012,
                    "gross_margin_qoq": -0.012,
                    "operating_margin": 0.18 - idx * 0.010,
                    "eps_yoy": 0.60 - idx * 0.14,
                    "inventory_yoy": -0.05 + idx * 0.06,
                    "ocf_margin": 0.18 - idx * 0.012,
                    "future_3m_return": -0.08 - idx * 0.005,
                    "future_6m_return": -0.14 - idx * 0.005,
                    "future_12m_return": -0.20 - idx * 0.005,
                }
            )
        return pd.DataFrame(rows)

    def test_improving_company_ranks_above_deteriorating_company(self) -> None:
        radar = build_turnaround_radar(self._panel(), min_history=3)
        self.assertEqual(list(radar["ticker"]), ["1111", "2222"])
        self.assertGreater(radar.iloc[0]["turnaround_score"], radar.iloc[1]["turnaround_score"])
        self.assertGreaterEqual(radar.iloc[0]["improving_signal_count"], 5)
        self.assertIn(radar.iloc[0]["stage"], {"Recovery", "Expansion"})

    def test_future_returns_do_not_change_turnaround_score(self) -> None:
        panel = self._panel()
        first = build_turnaround_history(panel, min_history=3)[["ticker", "report_date", "turnaround_score"]]
        modified = panel.copy()
        modified["future_3m_return"] = modified["future_3m_return"] * -100
        modified["future_6m_return"] = 999.0
        modified["future_12m_return"] = -999.0
        second = build_turnaround_history(modified, min_history=3)[["ticker", "report_date", "turnaround_score"]]
        pd.testing.assert_frame_equal(first, second)

    def test_validation_reports_positive_ic_and_spread(self) -> None:
        validation = validate_turnaround_signal(self._panel(), target="future_6m_return", min_history=3)
        self.assertGreater(validation["samples"], 5)
        self.assertGreater(validation["spearman_ic"], 0.5)
        self.assertGreater(validation["top_bottom_spread"], 0.0)


if __name__ == "__main__":
    unittest.main()
