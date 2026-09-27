from __future__ import annotations

import unittest
import pandas as pd

from core.abf_model_audit import build_abf_model_audit


class AbfModelAuditTests(unittest.TestCase):
    def test_marks_cost_risk_for_refinement_and_beta_candidate(self):
        sens=pd.DataFrame([{
            "company":"ABF Basket","feature":"pcb_revenue_yoy","target":"abf_revenue_yoy_basket",
            "lag_months":1,"beta":0.8,"oos_r2":-1.0,"oos_directional_corr":0.5,
            "magnitude_validation_pass":False,"beta_ci_low":0.1,"beta_ci_high":1.1,"sample_size":31,
        }])
        margin=pd.DataFrame()
        scenarios=pd.DataFrame()
        out=build_abf_model_audit(sens,margin,scenarios)
        self.assertEqual(out[out.component=="Cost / supply pressure"].iloc[0].assessment,"NEEDS_REFINEMENT")
        self.assertEqual(out[out.component=="ABF Basket revenue beta"].iloc[0].assessment,"MAGNITUDE_CANDIDATE")
        self.assertEqual(out[out.component=="Compute / networking end demand"].iloc[0].assessment,"EMPIRICALLY_VALIDATED_DRIVER")

    def test_correlation_is_never_called_causal(self):
        sens=pd.DataFrame(columns=["company"])
        margin=pd.DataFrame([{
            "feature":"revenue_yoy","target":"gross_margin_qoq","lag_quarters":1,
            "spearman":0.4,"oos_spearman":0.2,"fdr_q":0.05,"status":"CANDIDATE",
            "sample_size":60,"cross_company_sign_share":1.0,
        }])
        out=build_abf_model_audit(sens,margin,pd.DataFrame())
        row=out[out.component_type=="CORRELATION"].iloc[0]
        self.assertEqual(row.model_use,"RESEARCH_CANDIDATE_ONLY")
        self.assertIn("not causal",row.why.lower())


if __name__=="__main__":
    unittest.main()
