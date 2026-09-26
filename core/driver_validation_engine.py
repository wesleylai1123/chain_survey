from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Iterable

import numpy as np
import pandas as pd

from core.operating_correlation_engine import (
    OperatingCorrelationConfig,
    align_point_in_time,
    build_abf_basket,
    evaluate_pair,
    scan_operating_correlations,
)


@dataclass(frozen=True)
class DriverValidationConfig:
    min_samples: int = 24
    rolling_windows: tuple[int, ...] = (12, 18)
    min_rolling_windows: int = 6
    bootstrap_iterations: int = 1000
    permutation_iterations: int = 1000
    block_size: int = 3
    fdr_alpha: float = 0.10
    random_seed: int = 20260925
    min_abs_oos: float = 0.15
    min_cross_company_positive_share: float = 2 / 3
    min_rolling_sign_share: float = 0.65


def _corr(values: pd.DataFrame) -> float:
    if len(values) < 3 or values["x"].nunique() < 2 or values["y"].nunique() < 2:
        return float("nan")
    return float(values["x"].corr(values["y"], method="spearman"))


def rolling_correlations(aligned: pd.DataFrame, windows: Iterable[int]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for window in windows:
        if len(aligned) < window:
            continue
        for end in range(window, len(aligned) + 1):
            chunk = aligned.iloc[end-window:end]
            value = _corr(chunk)
            if np.isnan(value):
                continue
            rows.append({
                "window": int(window),
                "end_period": str(chunk.iloc[-1]["target_period"]),
                "correlation": value,
            })
    return pd.DataFrame(rows)


def _moving_blocks(n: int, block_size: int) -> list[np.ndarray]:
    block_size=max(1,min(block_size,n))
    return [np.arange(i,min(i+block_size,n)) for i in range(0,n-block_size+1)]


def block_bootstrap_ci(
    aligned: pd.DataFrame,
    *,
    iterations: int,
    block_size: int,
    seed: int,
) -> tuple[float, float]:
    n=len(aligned)
    if n < 6:
        return float("nan"), float("nan")
    blocks=_moving_blocks(n,block_size)
    rng=np.random.default_rng(seed)
    values=[]
    while len(values) < iterations:
        indices=[]
        while len(indices) < n:
            block=blocks[int(rng.integers(0,len(blocks)))]
            indices.extend(block.tolist())
        sample=aligned.iloc[indices[:n]][["x","y"]].reset_index(drop=True)
        value=_corr(sample)
        if not np.isnan(value):
            values.append(value)
    lo,hi=np.quantile(values,[0.025,0.975])
    return float(lo),float(hi)


def block_permutation_pvalue(
    aligned: pd.DataFrame,
    *,
    iterations: int,
    block_size: int,
    seed: int,
) -> float:
    observed=abs(_corr(aligned[["x","y"]]))
    if np.isnan(observed) or len(aligned) < 6:
        return float("nan")
    n=len(aligned)
    block_size=max(1,min(block_size,n))
    blocks=[aligned["y"].iloc[i:i+block_size].to_numpy() for i in range(0,n,block_size)]
    rng=np.random.default_rng(seed)
    exceed=0
    for _ in range(iterations):
        order=rng.permutation(len(blocks))
        y=np.concatenate([blocks[i] for i in order])[:n]
        perm=pd.DataFrame({"x":aligned["x"].to_numpy(),"y":y})
        value=abs(_corr(perm))
        if not np.isnan(value) and value >= observed:
            exceed += 1
    return float((exceed + 1) / (iterations + 1))


def benjamini_hochberg(pvalues: pd.Series) -> pd.Series:
    values=pd.to_numeric(pvalues,errors="coerce")
    result=pd.Series(np.nan,index=values.index,dtype=float)
    valid=values.dropna().sort_values()
    m=len(valid)
    if m == 0:
        return result
    adjusted=np.empty(m,float)
    ordered=valid.to_numpy()
    for i,p in enumerate(ordered,start=1):
        adjusted[i-1]=p*m/i
    adjusted=np.minimum.accumulate(adjusted[::-1])[::-1]
    adjusted=np.clip(adjusted,0,1)
    result.loc[valid.index]=adjusted
    return result


def nested_walk_forward(
    history: pd.DataFrame,
    feature: str,
    target: str,
    *,
    lags: tuple[int,...]=(0,1,2,3,4,5,6),
    min_train: int=18,
    test_size: int=6,
    step: int=6,
) -> pd.DataFrame:
    frame=build_abf_basket(history)
    prepared={}
    all_periods=set()
    for lag in lags:
        aligned=align_point_in_time(frame,feature,target,lag)
        prepared[lag]=aligned
        all_periods.update(aligned["target_period"].astype(str))
    periods=sorted(all_periods)
    rows=[]
    for split in range(min_train,len(periods)-2+1,step):
        train_periods=set(periods[:split])
        test_periods=set(periods[split:split+test_size])
        if len(test_periods)<3:
            continue
        lag_scores=[]
        for lag,aligned in prepared.items():
            train=aligned[aligned["target_period"].astype(str).isin(train_periods)]
            corr=_corr(train[["x","y"]])
            if len(train)>=min_train and not np.isnan(corr):
                lag_scores.append((abs(corr),corr,lag))
        if not lag_scores:
            continue
        _,train_corr,best_lag=max(lag_scores,key=lambda x:x[0])
        test=prepared[best_lag][prepared[best_lag]["target_period"].astype(str).isin(test_periods)]
        test_corr=_corr(test[["x","y"]])
        rows.append({
            "train_end":periods[split-1],
            "test_start":min(test_periods),
            "test_end":max(test_periods),
            "selected_lag":best_lag,
            "train_corr":train_corr,
            "test_corr":test_corr,
            "test_samples":len(test),
        })
    return pd.DataFrame(rows)


def cross_company_generalization(
    history: pd.DataFrame,
    feature: str,
    lag: int,
) -> pd.DataFrame:
    frame=build_abf_basket(history)
    rows=[]
    for ticker in ("3037.TW","3189.TW","8046.TW"):
        target=f"abf_company_revenue_yoy::{ticker}"
        row=evaluate_pair(frame,feature,target,lag)
        rows.append({
            "ticker":ticker,
            "target":target,
            "sample_size":row["sample_size"],
            "spearman":row["spearman"],
            "test_30":row["test_30"],
        })
    return pd.DataFrame(rows)


def validate_driver(
    history: pd.DataFrame,
    feature: str,
    target: str,
    lag: int,
    *,
    config: DriverValidationConfig=DriverValidationConfig(),
) -> dict[str, object]:
    frame=build_abf_basket(history)
    aligned=align_point_in_time(frame,feature,target,lag)
    base=evaluate_pair(frame,feature,target,lag)

    seed=int(sha256(f"{feature}|{target}|{lag}|{config.random_seed}".encode()).hexdigest()[:8],16)
    rolling=rolling_correlations(aligned,config.rolling_windows)
    boot_lo,boot_hi=block_bootstrap_ci(
        aligned,iterations=config.bootstrap_iterations,block_size=config.block_size,seed=seed
    )
    pvalue=block_permutation_pvalue(
        aligned,iterations=config.permutation_iterations,block_size=config.block_size,seed=seed+1
    )
    walk=nested_walk_forward(frame,feature,target)
    cross=cross_company_generalization(frame,feature,lag)

    sign=np.sign(base["spearman"]) if not np.isnan(base["spearman"]) else 0
    rolling_share=0.0
    if not rolling.empty and sign:
        rolling_share=float((np.sign(rolling["correlation"])==sign).mean())
    oos_values=walk["test_corr"].dropna() if not walk.empty else pd.Series(dtype=float)
    walk_oos_median=float(oos_values.median()) if not oos_values.empty else float("nan")
    walk_oos_sign_share=float((np.sign(oos_values)==sign).mean()) if not oos_values.empty and sign else 0.0
    company_values=cross["spearman"].dropna()
    company_sign_share=float((np.sign(company_values)==sign).mean()) if not company_values.empty and sign else 0.0

    bootstrap_excludes_zero=bool((boot_lo > 0 and boot_hi > 0) or (boot_lo < 0 and boot_hi < 0))
    gates={
        "sample_size": int(base["sample_size"]) >= config.min_samples,
        "oos_direction": (not np.isnan(base["test_30"])) and np.sign(base["test_30"])==sign and abs(base["test_30"])>=config.min_abs_oos,
        "rolling_stability": len(rolling)>=config.min_rolling_windows and rolling_share>=config.min_rolling_sign_share,
        "cross_company": company_sign_share>=config.min_cross_company_positive_share,
        "bootstrap_excludes_zero": bootstrap_excludes_zero,
        "walk_forward": (not np.isnan(walk_oos_median)) and np.sign(walk_oos_median)==sign and walk_oos_sign_share>=0.60,
    }

    return {
        "feature":feature,
        "target":target,
        "lag_months":lag,
        "sample_size":int(base["sample_size"]),
        "spearman":float(base["spearman"]),
        "pearson":float(base["pearson"]),
        "test_30":float(base["test_30"]),
        "rolling_sign_share":rolling_share,
        "rolling_min":float(rolling["correlation"].min()) if not rolling.empty else float("nan"),
        "rolling_median":float(rolling["correlation"].median()) if not rolling.empty else float("nan"),
        "rolling_max":float(rolling["correlation"].max()) if not rolling.empty else float("nan"),
        "bootstrap_ci_low":boot_lo,
        "bootstrap_ci_high":boot_hi,
        "permutation_p":pvalue,
        "walk_forward_oos_median":walk_oos_median,
        "walk_forward_sign_share":walk_oos_sign_share,
        "cross_company_sign_share":company_sign_share,
        "cross_company":cross,
        "rolling":rolling,
        "walk_forward":walk,
        "gates":gates,
        "gate_pass_count":sum(bool(v) for v in gates.values()),
        "gate_count":len(gates),
    }


def validate_candidate_table(
    history: pd.DataFrame,
    *,
    top_n: int=12,
    config: DriverValidationConfig=DriverValidationConfig(),
) -> tuple[pd.DataFrame, dict[str,dict[str,object]]]:
    correlations=scan_operating_correlations(
        history,
        config=OperatingCorrelationConfig(min_samples=18),
    )
    basket=correlations[correlations["target"]=="abf_revenue_yoy_basket"].head(top_n)
    details={}
    rows=[]
    for _,candidate in basket.iterrows():
        result=validate_driver(
            history,str(candidate["feature"]),str(candidate["target"]),int(candidate["lag_months"]),config=config
        )
        key=f"{result['feature']}|{result['target']}|{result['lag_months']}"
        details[key]=result
        rows.append({
            k:v for k,v in result.items()
            if k not in {"cross_company","rolling","walk_forward","gates"}
        })
    table=pd.DataFrame(rows)
    if table.empty:
        return table,details
    table["fdr_q"]=benjamini_hochberg(table["permutation_p"])
    table["fdr_pass"]=table["fdr_q"]<=config.fdr_alpha
    table["status"]=np.where(
        (table["gate_pass_count"]==table["gate_count"]) & table["fdr_pass"],
        "VALIDATED",
        "CANDIDATE",
    )
    table["validation_score"]=(
        table["spearman"].abs()
        * table["rolling_sign_share"]
        * table["cross_company_sign_share"]
        * table["walk_forward_sign_share"]
        * (1.0-table["fdr_q"].fillna(1.0))
    )
    return table.sort_values(["status","validation_score"],ascending=[True,False]).reset_index(drop=True),details
