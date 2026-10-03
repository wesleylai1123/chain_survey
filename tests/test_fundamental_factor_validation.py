from __future__ import annotations

import unittest
import pandas as pd

from scripts.run_fundamental_factor_validation import eligible_factors, return_basis_summary, validate_fundamental_factors


class FundamentalFactorValidationTests(unittest.TestCase):
    def _catalog(self):
        return pd.DataFrame([
            {"factor":"good","category":"Quality","model_status":"CALIBRATION_CANDIDATE","basis":"x","source":"official"},
            {"factor":"reference","category":"Quality","model_status":"REFERENCE_ONLY","basis":"y","source":"official"},
        ])

    def test_only_catalog_eligible_factors_are_scanned(self):
        data=pd.DataFrame({"good":range(30),"reference":range(30)})
        self.assertEqual(eligible_factors(data,self._catalog(),min_non_null=24),["good"])

    def test_raw_return_basis_cannot_be_promoted(self):
        rows=[]
        periods=pd.date_range("2020-03-31",periods=20,freq="QE")
        for company in ("A","B","C"):
            for i,d in enumerate(periods):
                x=float(i)+(0 if company=="A" else 0.2)
                rows.append({
                    "ticker":company,"report_date":str(d.date()),"industry":"X","cycle":"Unknown",
                    "good":x,
                    "future_3m_return":x/100,"future_6m_return":x/80,"future_12m_return":x/60,
                    "return_basis":"RAW_CLOSE_UNADJUSTED",
                })
        out=validate_fundamental_factors(pd.DataFrame(rows),self._catalog(),min_non_null=20,min_samples=20)
        self.assertFalse(out.empty)
        self.assertEqual(set(out["assessment"]),{"RESEARCH_ONLY_RAW_RETURN_BASIS"})
        self.assertFalse(out["adjusted_return_basis"].any())

    def test_adjusted_basis_is_detected(self):
        basis,ok=return_basis_summary(pd.DataFrame({"return_basis":["ADJUSTED_CLOSE"]}))
        self.assertTrue(ok)
        self.assertEqual(basis,"ADJUSTED_CLOSE")


if __name__=="__main__":
    unittest.main()
