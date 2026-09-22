from __future__ import annotations

import unittest
import pandas as pd

from core.operating_correlation_engine import align_point_in_time, evaluate_pair, scan_operating_correlations


class OperatingCorrelationEngineTests(unittest.TestCase):
    def _history(self) -> pd.DataFrame:
        rows=[]
        for i,month in enumerate(pd.period_range("2024-01","2025-12",freq="M")):
            pub=(month.end_time+pd.Timedelta(days=15)).tz_localize("Asia/Taipei")
            rows.append({
                "source_id":"tpca_public_industry","metric_id":"pcb_revenue_yoy","entity":"Taiwan PCB",
                "period":str(month),"period_date":month.end_time.tz_localize("Asia/Taipei"),"published_at":pub,
                "value":i,"value_unit":"percent","change_pct":i,"chain":"Networking","dimension":"physical_throughput",
                "source":"x","source_url":"x","knowledge_time_method":"page_publication_date"
            })
            target_month=month+1
            target_pub=(target_month.end_time+pd.Timedelta(days=10)).tz_localize("Asia/Taipei")
            rows.append({
                "source_id":"mops_abf_monthly_revenue","metric_id":"abf_company_revenue_yoy::3037.TW","entity":"欣興",
                "period":str(target_month),"period_date":target_month.end_time.tz_localize("Asia/Taipei"),"published_at":target_pub,
                "value":i*2,"value_unit":"percent","change_pct":i*2,"chain":"ABF","dimension":"financial_confirmation",
                "source":"x","source_url":"x","knowledge_time_method":"deadline"
            })
        return pd.DataFrame(rows)

    def test_positive_lag_means_feature_leads_target(self) -> None:
        aligned=align_point_in_time(self._history(),"pcb_revenue_yoy","abf_company_revenue_yoy::3037.TW",1)
        self.assertGreaterEqual(len(aligned),20)
        self.assertTrue((aligned["feature_published_at"]<=aligned["target_published_at"]).all())

    def test_detects_known_one_month_lead(self) -> None:
        result=evaluate_pair(self._history(),"pcb_revenue_yoy","abf_company_revenue_yoy::3037.TW",1)
        self.assertGreater(result["spearman"],0.95)
        self.assertEqual(result["sign_stability"],1.0)

    def test_scan_requires_sufficient_history(self) -> None:
        results=scan_operating_correlations(self._history())
        self.assertFalse(results.empty)
        best=results.iloc[0]
        self.assertGreaterEqual(best["sample_size"],18)


if __name__=="__main__":
    unittest.main()
