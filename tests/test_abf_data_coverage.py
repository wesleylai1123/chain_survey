from __future__ import annotations

import unittest
import pandas as pd

from core.abf_data_coverage import audit_abf_data_coverage


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


if __name__=="__main__":
    unittest.main()
