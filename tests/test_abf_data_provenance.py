from __future__ import annotations

import unittest
import pandas as pd

from core.abf_data_provenance import build_abf_data_provenance


class AbfDataProvenanceTests(unittest.TestCase):
    def test_marks_proxy_as_support_only(self):
        coverage=pd.DataFrame([{"data_id":"ic_substrate_revenue_mix_history","status":"INSUFFICIENT_HISTORY"}])
        operating=pd.DataFrame([{
            "data_id":"ic_substrate_revenue_mix_history","period_end":"2025-12-31",
            "source_url":"https://mopsov.twse.com.tw/a.pdf","publication_precision":"DATE_ONLY",
        }])
        out=build_abf_data_provenance(coverage,operating=operating)
        row=out[out.data_id=="ic_substrate_revenue_mix_history"].iloc[0]
        self.assertEqual(row.model_eligibility,"SUPPORT_ONLY")
        self.assertEqual(row.actual_source_hosts,"mopsov.twse.com.tw")

    def test_regulatory_direct_is_not_the_same_as_proxy(self):
        history=pd.DataFrame([
            {"metric_id":"abf_company_revenue_yoy::3037.TW","period_date":"2026-01-31","source_url":"https://mops.twse.com.tw/a","knowledge_time_method":"regulatory_deadline_proxy"},
            {"metric_id":"abf_company_revenue_yoy::3037.TW","period_date":"2026-02-28","source_url":"https://mops.twse.com.tw/b","knowledge_time_method":"regulatory_deadline_proxy"},
        ])
        coverage=pd.DataFrame([{"data_id":"company_monthly_revenue","status":"AVAILABLE"}])
        out=build_abf_data_provenance(coverage,history=history)
        row=out[out.data_id=="company_monthly_revenue"].iloc[0]
        self.assertEqual(row.source_class,"REGULATOR_OFFICIAL")
        self.assertEqual(row.model_eligibility,"CALIBRATION_ELIGIBLE")
        self.assertIn("regulatory_deadline_proxy",row.knowledge_time_method)

    def test_paid_consensus_remains_paid_required(self):
        coverage=pd.DataFrame([{"data_id":"consensus_eps","status":"MISSING"}])
        out=build_abf_data_provenance(coverage)
        row=out[out.data_id=="consensus_eps"].iloc[0]
        self.assertEqual(row.source_class,"PAID_PIT_VENDOR")
        self.assertEqual(row.model_eligibility,"PAID_SOURCE_REQUIRED")


if __name__=="__main__":
    unittest.main()
