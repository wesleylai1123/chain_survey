from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from core.operating_correlation_engine import align_point_in_time, build_abf_basket


@dataclass(frozen=True)
class SensitivityConfig:
    lag_months: int=1
    min_samples: int=24
    train_fraction: float=0.70
    bootstrap_iterations: int=1000
    block_size: int=3
    random_seed: int=20260926


def _fit_ols(x: np.ndarray,y: np.ndarray) -> tuple[float,float]:
    if len(x)<3 or np.std(x)==0:
        return float("nan"),float("nan")
    beta=float(np.cov(x,y,ddof=1)[0,1]/np.var(x,ddof=1))
    alpha=float(np.mean(y)-beta*np.mean(x))
    return alpha,beta


def _metrics(y: np.ndarray,pred: np.ndarray) -> dict[str,float]:
    residual=y-pred
    sse=float(np.sum(residual**2))
    sst=float(np.sum((y-np.mean(y))**2))
    corr=float(pd.Series(y).corr(pd.Series(pred),method="spearman")) if len(y)>=3 else float("nan")
    return {
        "mae":float(np.mean(np.abs(residual))),
        "rmse":float(np.sqrt(np.mean(residual**2))),
        "r2":float(1.0-sse/sst) if sst>0 else float("nan"),
        "directional_corr":corr,
    }


def _block_bootstrap_beta(aligned: pd.DataFrame,config: SensitivityConfig) -> tuple[float,float]:
    n=len(aligned)
    if n<config.min_samples:
        return float("nan"),float("nan")
    rng=np.random.default_rng(config.random_seed)
    block=max(1,min(config.block_size,n))
    starts=list(range(0,n-block+1))
    betas=[]
    for _ in range(config.bootstrap_iterations):
        idx=[]
        while len(idx)<n:
            start=int(rng.choice(starts))
            idx.extend(range(start,start+block))
        sample=aligned.iloc[idx[:n]]
        _,beta=_fit_ols(sample["x"].to_numpy(float),sample["y"].to_numpy(float))
        if not np.isnan(beta):
            betas.append(beta)
    if not betas:
        return float("nan"),float("nan")
    lo,hi=np.quantile(betas,[0.025,0.975])
    return float(lo),float(hi)


def estimate_revenue_sensitivity(
    history: pd.DataFrame,
    *,
    feature: str="pcb_revenue_yoy",
    target: str="abf_revenue_yoy_basket",
    config: SensitivityConfig=SensitivityConfig(),
) -> dict[str,object]:
    frame=build_abf_basket(history)
    aligned=align_point_in_time(frame,feature,target,config.lag_months)
    if len(aligned)<config.min_samples:
        raise ValueError(f"Need >= {config.min_samples} samples, got {len(aligned)}")

    x=aligned["x"].to_numpy(float)
    y=aligned["y"].to_numpy(float)
    alpha,beta=_fit_ols(x,y)
    pred=alpha+beta*x
    full_metrics=_metrics(y,pred)

    split=max(3,int(len(aligned)*config.train_fraction))
    train=aligned.iloc[:split]
    test=aligned.iloc[split:]
    train_alpha,train_beta=_fit_ols(train["x"].to_numpy(float),train["y"].to_numpy(float))
    test_pred=train_alpha+train_beta*test["x"].to_numpy(float)
    oos=_metrics(test["y"].to_numpy(float),test_pred) if len(test)>=3 else {"mae":float("nan"),"rmse":float("nan"),"r2":float("nan")}

    lo,hi=_block_bootstrap_beta(aligned,config)
    ci_excludes_zero=bool((lo>0 and hi>0) or (lo<0 and hi<0))
    oos_direction_ok=bool(not np.isnan(oos["directional_corr"]) and np.sign(oos["directional_corr"])==np.sign(beta))
    magnitude_validated=bool(ci_excludes_zero and oos_direction_ok and oos["r2"]>0)
    sensitivity_status="MAGNITUDE_VALIDATED" if magnitude_validated else "MAGNITUDE_CANDIDATE"
    return {
        "feature":feature,
        "target":target,
        "lag_months":config.lag_months,
        "sample_size":len(aligned),
        "alpha":alpha,
        "beta":beta,
        "beta_ci_low":lo,
        "beta_ci_high":hi,
        "r2":full_metrics["r2"],
        "mae":full_metrics["mae"],
        "rmse":full_metrics["rmse"],
        "oos_beta":train_beta,
        "oos_mae":oos["mae"],
        "oos_rmse":oos["rmse"],
        "oos_r2":oos["r2"],
        "oos_directional_corr":oos["directional_corr"],
        "direction_status":"VALIDATED",
        "sensitivity_status":sensitivity_status,
        "magnitude_validation_pass":magnitude_validated,
        "interpretation":f"A +10ppt change in {feature} historically maps to about {beta*10:+.2f}ppt in {target} at +{config.lag_months}M.",
        "aligned":aligned,
    }


def estimate_company_revenue_sensitivities(history: pd.DataFrame,config: SensitivityConfig=SensitivityConfig()) -> pd.DataFrame:
    rows=[]
    for ticker,company in (("3037.TW","欣興"),("3189.TW","景碩"),("8046.TW","南電")):
        result=estimate_revenue_sensitivity(
            history,
            target=f"abf_company_revenue_yoy::{ticker}",
            config=config,
        )
        rows.append({
            "company":company,
            "ticker":ticker,
            **{k:v for k,v in result.items() if k not in {"aligned","interpretation"}},
            "impact_per_10ppt_driver":result["beta"]*10.0,
        })
    basket=estimate_revenue_sensitivity(history,config=config)
    rows.append({
        "company":"ABF Basket",
        "ticker":"ABF",
        **{k:v for k,v in basket.items() if k not in {"aligned","interpretation"}},
        "impact_per_10ppt_driver":basket["beta"]*10.0,
    })
    return pd.DataFrame(rows)
