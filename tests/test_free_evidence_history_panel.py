from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.build_free_evidence_history_panel import build_history_panel, coverage_summary


class FreeEvidenceHistoryPanelTests(unittest.TestCase):
    def test_builds_correlation_ready_panel(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            pd.DataFrame([{
                "company":"南電","ticker":"8046.TW","period":"2025-01",
                "period_date":"2025-01-31T00:00:00+08:00","published_at":"2025-02-10T23:59:59+08:00",
                "monthly_revenue":100.0,"yoy_pct":10.0,"source":"MOPS",
                "source_url":"u","knowledge_time_method":"regulatory_deadline_proxy"
            }]).to_csv(root/"mops_abf_monthly_revenue_history.csv",index=False)
            panel=build_history_panel(root)
            self.assertEqual(len(panel),1)
            self.assertEqual(panel.iloc[0]["chain"],"ABF")
            self.assertEqual(panel.iloc[0]["metric_id"],"abf_company_revenue_yoy::8046.TW")
            summary=coverage_summary(panel)
            self.assertEqual(int(summary.iloc[0]["observations"]),1)

    def test_rejects_future_leakage(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            pd.DataFrame([{
                "company":"南電","ticker":"8046.TW","period":"2025-01",
                "period_date":"2025-01-31T00:00:00+08:00","published_at":"2025-01-01T00:00:00+08:00",
                "monthly_revenue":100.0,"yoy_pct":10.0,"source":"MOPS",
                "source_url":"u","knowledge_time_method":"bad"
            }]).to_csv(root/"mops_abf_monthly_revenue_history.csv",index=False)
            with self.assertRaises(ValueError):
                build_history_panel(root)


if __name__=="__main__":
    unittest.main()
