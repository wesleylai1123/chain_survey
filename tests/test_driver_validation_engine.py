from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from core.driver_validation_engine import (
    benjamini_hochberg,
    block_bootstrap_ci,
    block_permutation_pvalue,
    nested_walk_forward,
    rolling_correlations,
    validate_driver,
)


class DriverValidationEngineTests(unittest.TestCase):
    def _history(self) -> pd.DataFrame:
        rows=[]
        periods=pd.period_range("2022-01","2025-12",freq="M")
        rng=np.random.default_rng(7)
        x=np.linspace(-20,30,len(periods))+rng.normal(0,2,len(periods))
        for i,p in enumerate(periods):
            pub=(p.end_time+pd.Timedelta(days=12)).tz_localize("Asia/Taipei")
            rows.append({
                "source_id":"tpca_public_industry","metric_id":"pcb_revenue_yoy","entity":"PCB",
                "period":str(p),"period_date":p.end_time.tz_localize("Asia/Taipei"),"published_at":pub,
                "value":x[i],"value_unit":"percent","change_pct":x[i],"chain":"Networking",
                "dimension":"physical_throughput","source":"x","source_url":"x","knowledge_time_method":"pub",
            })
            target_p=p+1
            for ticker,noise in (("3037.TW",1.0),("3189.TW",1.5),("8046.TW",1.2)):
                tpub=(target_p.end_time+pd.Timedelta(days=10)).tz_localize("Asia/Taipei")
                y=x[i]*1.8+rng.normal(0,noise)
                rows.append({
                    "source_id":"mops_abf_monthly_revenue",
                    "metric_id":f"abf_company_revenue_yoy::{ticker}","entity":ticker,
                    "period":str(target_p),"period_date":target_p.end_time.tz_localize("Asia/Taipei"),"published_at":tpub,
                    "value":y,"value_unit":"percent","change_pct":y,"chain":"ABF",
                    "dimension":"financial_confirmation","source":"x","source_url":"x","knowledge_time_method":"pub",
                })
        return pd.DataFrame(rows)

    def test_bh_is_monotonic_and_bounded(self) -> None:
        q=benjamini_hochberg(pd.Series([0.001,0.02,0.04,0.5]))
        self.assertTrue(q.between(0,1).all())
        ordered=q.sort_values().to_numpy()
        self.assertTrue((np.diff(ordered)>=-1e-12).all())

    def test_bootstrap_and_permutation_detect_strong_relation(self) -> None:
        aligned=pd.DataFrame({"x":np.arange(30,dtype=float),"y":np.arange(30,dtype=float)+np.random.default_rng(1).normal(0,1,30)})
        lo,hi=block_bootstrap_ci(aligned,iterations=200,block_size=3,seed=1)
        p=block_permutation_pvalue(aligned,iterations=200,block_size=3,seed=2)
        self.assertGreater(lo,0.7)
        self.assertGreater(hi,lo)
        self.assertLess(p,0.05)

    def test_nested_walk_forward_selects_leading_lag(self) -> None:
        wf=nested_walk_forward(self._history(),"pcb_revenue_yoy","abf_revenue_yoy_basket")
        self.assertFalse(wf.empty)
        self.assertGreater((wf["selected_lag"]==1).mean(),0.5)
        self.assertGreater(wf["test_corr"].median(),0.8)

    def test_validation_retains_diagnostics(self) -> None:
        result=validate_driver(self._history(),"pcb_revenue_yoy","abf_revenue_yoy_basket",1)
        self.assertGreater(result["spearman"],0.9)
        self.assertGreater(result["rolling_sign_share"],0.9)
        self.assertGreater(result["cross_company_sign_share"],0.9)
        self.assertIn("walk_forward",result["gates"])
        self.assertEqual(result["gate_count"],6)


if __name__=="__main__":
    unittest.main()
