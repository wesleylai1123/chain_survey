from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from core.scenario_evidence_validation import ScenarioValidationConfig, validate_abf_scenarios


class ScenarioEvidenceValidationTests(unittest.TestCase):
    def _history(self) -> pd.DataFrame:
        rows=[]
        rng=np.random.default_rng(9)
        periods=pd.period_range("2020-01","2025-12",freq="M")
        x=np.sin(np.linspace(0,8*np.pi,len(periods)))*25
        for i,p in enumerate(periods):
            pub=(p.end_time+pd.Timedelta(days=12)).tz_localize("Asia/Taipei")
            rows.append({
                "source_id":"tpca_public_industry","metric_id":"pcb_revenue_yoy","entity":"PCB",
                "period":str(p),"period_date":p.end_time.tz_localize("Asia/Taipei"),"published_at":pub,
                "value":x[i],"value_unit":"percent","change_pct":x[i],"chain":"Networking",
                "dimension":"physical_throughput","source":"TPCA","source_url":"x","knowledge_time_method":"pub"
            })
            q=p+1
            tpub=(q.end_time+pd.Timedelta(days=10)).tz_localize("Asia/Taipei")
            for ticker in ("3037.TW","3189.TW","8046.TW"):
                y=0.8*x[i]+rng.normal(0,2)
                rows.append({
                    "source_id":"mops_abf_monthly_revenue","metric_id":f"abf_company_revenue_yoy::{ticker}",
                    "entity":ticker,"period":str(q),"period_date":q.end_time.tz_localize("Asia/Taipei"),
                    "published_at":tpub,"value":y,"value_unit":"percent","change_pct":y,"chain":"ABF",
                    "dimension":"financial_confirmation","source":"MOPS","source_url":"x","knowledge_time_method":"pub"
                })
        return pd.DataFrame(rows)

    def test_upside_and_downside_are_validated_independently(self) -> None:
        table,details=validate_abf_scenarios(
            self._history(),
            config=ScenarioValidationConfig(min_samples=10,bootstrap_iterations=200,permutation_iterations=200),
        )
        self.assertEqual(set(table["scenario"]),{"UPSIDE","DOWNSIDE"})
        self.assertGreater(details["UPSIDE|pcb_revenue_yoy"]["sample_size"],10)
        self.assertGreater(details["DOWNSIDE|pcb_revenue_yoy"]["sample_size"],10)
        self.assertEqual(details["UPSIDE|pcb_revenue_yoy"]["status"],"VALIDATED")
        self.assertEqual(details["DOWNSIDE|pcb_revenue_yoy"]["status"],"VALIDATED")

    def test_each_side_keeps_its_own_gates(self) -> None:
        _,details=validate_abf_scenarios(
            self._history(),
            config=ScenarioValidationConfig(min_samples=10,bootstrap_iterations=100,permutation_iterations=100),
        )
        self.assertIsNot(details["UPSIDE|pcb_revenue_yoy"]["gates"],details["DOWNSIDE|pcb_revenue_yoy"]["gates"])


if __name__=="__main__":
    unittest.main()
