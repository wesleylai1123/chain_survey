from __future__ import annotations

import unittest
import pandas as pd

from core.abf_data_coverage import audit_abf_data_coverage
from core.abf_operating_observations import verified_operating_observations


class AbfDataCoverageTests(unittest.TestCase):
    def test_marks_missing_external_and_proxy(self) -> None:
        history=pd.DataFrame([
            {"metric_id":"pcb_revenue_yoy"},
            {"metric_id":"rigid_pcb_export_yoy"},
            {"metric_id":"pcb_material_revenue_yoy"},
            {"metric_id":"ccl_import_yoy"},
            {"metric_id":"ccl_export_yoy"},
            {"metric_id":"abf_company_revenue_yoy::3037.TW"},
            {"metric_id":"abf_company_revenue_yoy::3189.TW"},
            {"metric_id":"abf_company_revenue_yoy::8046.TW"},
        ]*24)
        rows=[]
        for ticker in ("3037.TW","3189.TW","8046.TW"):
            for i in range(10):
                rows.append({
                    "ticker":ticker,"gross_margin":0.2,"gross_margin_qoq":0.01,
                    "gross_margin_yoy_delta":0.02,"operating_margin":0.1,
                    "eps":3.0,"eps_yoy":0.2,"inventory":100,"inventory_yoy":0.1,
                    "availability_method":"report_date+60d_proxy",
                })
        factor=pd.DataFrame(rows)
        result=audit_abf_data_coverage(history,factor)
        status=dict(zip(result["data_id"],result["status"]))
        self.assertEqual(status["quarterly_margin_history"],"AVAILABLE")
        self.assertEqual(status["quarterly_exact_filing_time"],"PROXY")
        self.assertEqual(status["abf_asp_history"],"MISSING")
        self.assertEqual(status["abf_utilization_history"],"MISSING")

    def test_sourced_operating_row_is_insufficient_not_available(self) -> None:
        observation=pd.DataFrame([{
            "data_id":"order_cancellation", "stock_id":"3037", "period_end":"2025-06-30",
            "observation_scope":"EVENT", "value":1, "unit":"event",
            "published_at":"2025-07-01T18:00:00+08:00", "published_date":"",
            "publication_precision":"EXACT_SECOND", "source_url":"https://mops.twse.com.tw/example",
            "source_page":"1", "source_excerpt":"Test disclosure",
        }])
        result=audit_abf_data_coverage(pd.DataFrame(), operating_observations=observation)
        row=result[result["data_id"]=="order_cancellation"].iloc[0]
        self.assertEqual(row["status"],"INSUFFICIENT_HISTORY")
        self.assertIn("1 primary observations",row["detail"])
        self.assertIn("companies=1",row["detail"])
        self.assertEqual(
            verified_operating_observations(observation,{"order_cancellation"}).iloc[0]["source_tier"],
            "PRIMARY",
        )

    def test_rejects_secondary_source_as_calibration_data(self) -> None:
        observation=pd.DataFrame([{
            "data_id":"abf_product_mix_history", "stock_id":"3189", "period_end":"2025-06-30",
            "observation_scope":"QUARTER", "value":44.7, "unit":"percent",
            "published_at":"", "published_date":"2026-09-12",
            "publication_precision":"DATE_ONLY", "source_url":"https://example-research.com/report",
            "source_page":"3", "source_excerpt":"ABF mix estimate",
        }])
        with self.assertRaisesRegex(ValueError,"primary company/regulator sources"):
            verified_operating_observations(observation,{"abf_product_mix_history"})

    def test_official_ic_substrate_proxy_does_not_fill_exact_abf_mix(self) -> None:
        observations=pd.read_csv("data/abf_operating_observations.csv",dtype={"stock_id":str})
        result=audit_abf_data_coverage(pd.DataFrame(),operating_observations=observations)
        proxy=result[result["data_id"]=="ic_substrate_revenue_mix_history"].iloc[0]
        status=dict(zip(result["data_id"],result["status"]))
        self.assertEqual(status["ic_substrate_revenue_mix_history"],"INSUFFICIENT_HISTORY")
        self.assertEqual(status["abf_product_mix_history"],"MISSING")
        self.assertIn("4 primary observations",proxy["detail"])
        self.assertIn("companies=1",proxy["detail"])
        self.assertIn("mopsov.twse.com.tw",proxy["detail"])


if __name__=="__main__":
    unittest.main()
