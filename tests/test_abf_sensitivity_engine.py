from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from core.abf_sensitivity_engine import SensitivityConfig, estimate_revenue_sensitivity


class AbfSensitivityTests(unittest.TestCase):
    def _history(self) -> pd.DataFrame:
        rng=np.random.default_rng(3)
        rows=[]
        periods=pd.period_range("2022-01","2025-12",freq="M")
        x=np.linspace(-20,30,len(periods))+rng.normal(0,2,len(periods))
        for i,p in enumerate(periods):
            pub=(p.end_time+pd.Timedelta(days=12)).tz_localize("Asia/Taipei")
            rows.append({
                "source_id":"tpca_public_industry","metric_id":"pcb_revenue_yoy","entity":"PCB",
                "period":str(p),"period_date":p.end_time.tz_localize("Asia/Taipei"),"published_at":pub,
                "value":x[i],"value_unit":"percent","change_pct":x[i],"chain":"Networking",
                "dimension":"physical_throughput","source":"x","source_url":"x","knowledge_time_method":"pub",
            })
            q=p+1
            tpub=(q.end_time+pd.Timedelta(days=10)).tz_localize("Asia/Taipei")
            for ticker,noise in (("3037.TW",1.0),("3189.TW",1.2),("8046.TW",1.4)):
                y=2.0+0.6*x[i]+rng.normal(0,noise)
                rows.append({
                    "source_id":"mops_abf_monthly_revenue","metric_id":f"abf_company_revenue_yoy::{ticker}","entity":ticker,
                    "period":str(q),"period_date":q.end_time.tz_localize("Asia/Taipei"),"published_at":tpub,
                    "value":y,"value_unit":"percent","change_pct":y,"chain":"ABF",
                    "dimension":"financial_confirmation","source":"x","source_url":"x","knowledge_time_method":"pub",
                })
        return pd.DataFrame(rows)

    def test_recovers_known_beta(self) -> None:
        result=estimate_revenue_sensitivity(
            self._history(),
            config=SensitivityConfig(bootstrap_iterations=200),
        )
        self.assertAlmostEqual(result["beta"],0.6,delta=0.08)
        self.assertGreater(result["beta_ci_low"],0)
        self.assertGreater(result["r2"],0.8)
        self.assertGreater(result["sample_size"],30)
        self.assertEqual(result["direction_status"],"VALIDATED")
        self.assertIn(result["sensitivity_status"],{"MAGNITUDE_VALIDATED","MAGNITUDE_CANDIDATE"})

    def test_positive_lag_is_preserved(self) -> None:
        result=estimate_revenue_sensitivity(
            self._history(),
            config=SensitivityConfig(bootstrap_iterations=100),
        )
        self.assertEqual(result["lag_months"],1)
        self.assertIn("+1M",result["interpretation"])


if __name__=="__main__":
    unittest.main()
