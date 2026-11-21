from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_HISTORY=ROOT/"data"/"history"/"free_industry_history_panel.csv"

@dataclass(frozen=True)
class OperatingCorrelationConfig:
    lags: tuple[int,...]=(0,1,2,3,4,5,6)
    min_samples: int=18
    method: str="spearman"
    oos_fraction: float=0.30


def _safe_corr(x: pd.Series,y: pd.Series,method: str) -> float:
    frame=pd.DataFrame({"x":pd.to_numeric(x,errors="coerce"),"y":pd.to_numeric(y,errors="coerce")}).dropna()
    if len(frame)<3 or frame["x"].nunique()<2 or frame["y"].nunique()<2:
        return float("nan")
    return float(frame["x"].corr(frame["y"],method=method))


def _prepare(history: pd.DataFrame) -> pd.DataFrame:
    frame=history.copy()
    frame["period_m"]=pd.PeriodIndex(frame["period"].astype(str).str[:7],freq="M")
    frame["published_at"]=pd.to_datetime(frame["published_at"],utc=True,format="mixed")
    frame["change_pct"]=pd.to_numeric(frame["change_pct"],errors="coerce")
    return frame


def align_point_in_time(
    history: pd.DataFrame,
    feature_metric: str,
    target_metric: str,
    lag: int,
) -> pd.DataFrame:
    frame=_prepare(history)
    features=frame[frame["metric_id"]==feature_metric][["period_m","published_at","change_pct"]].rename(
        columns={"published_at":"feature_published_at","change_pct":"x"}
    )
    targets=frame[frame["metric_id"]==target_metric][["period_m","published_at","change_pct"]].rename(
        columns={"period_m":"target_period","published_at":"target_published_at","change_pct":"y"}
    )
    features["target_period"]=features["period_m"]+int(lag)
    aligned=features.merge(targets,on="target_period",how="inner")
    aligned=aligned[aligned["feature_published_at"]<=aligned["target_published_at"]]
    return aligned.sort_values("period_m").reset_index(drop=True)


def evaluate_pair(
    history: pd.DataFrame,
    feature_metric: str,
    target_metric: str,
    lag: int,
    *,
    method: str="spearman",
    oos_fraction: float=0.30,
) -> dict[str,object]:
    aligned=align_point_in_time(history,feature_metric,target_metric,lag)
    n=len(aligned)
    corr=_safe_corr(aligned["x"],aligned["y"],method)
    pearson=_safe_corr(aligned["x"],aligned["y"],"pearson")
    midpoint=n//2
    first=_safe_corr(aligned.iloc[:midpoint]["x"],aligned.iloc[:midpoint]["y"],method) if midpoint>=3 else float("nan")
    second=_safe_corr(aligned.iloc[midpoint:]["x"],aligned.iloc[midpoint:]["y"],method) if n-midpoint>=3 else float("nan")
    split=max(3,int(n*(1.0-oos_fraction)))
    train=_safe_corr(aligned.iloc[:split]["x"],aligned.iloc[:split]["y"],method) if split>=3 else float("nan")
    test=_safe_corr(aligned.iloc[split:]["x"],aligned.iloc[split:]["y"],method) if n-split>=3 else float("nan")
    signs=[v for v in (first,second,train,test) if not np.isnan(v) and v!=0]
    sign_stability=float(np.mean([np.sign(v)==np.sign(corr) for v in signs])) if signs and not np.isnan(corr) else 0.0
    return {
        "feature":feature_metric,
        "target":target_metric,
        "lag_months":int(lag),
        "sample_size":n,
        "spearman":corr if method=="spearman" else _safe_corr(aligned["x"],aligned["y"],"spearman"),
        "pearson":pearson,
        "first_half":first,
        "second_half":second,
        "train_70":train,
        "test_30":test,
        "sign_stability":sign_stability,
        "score":0.0 if np.isnan(corr) else abs(corr)*sign_stability,
    }


def build_abf_basket(history: pd.DataFrame) -> pd.DataFrame:
    frame=_prepare(history)
    target=frame[frame["metric_id"].astype(str).str.startswith("abf_company_revenue_yoy::")].copy()
    if target.empty:
        return frame
    basket=target.groupby("period_m").agg(
        change_pct=("change_pct","median"),
        published_at=("published_at","max"),
    ).reset_index()
    basket["source_id"]="derived_abf_basket"
    basket["metric_id"]="abf_revenue_yoy_basket"
    basket["entity"]="ABF substrate basket"
    basket["period"]=basket["period_m"].astype(str)
    basket["period_date"]=basket["period_m"].dt.to_timestamp("M").dt.tz_localize("Asia/Taipei").dt.tz_convert("UTC")
    basket["value"]=basket["change_pct"]
    basket["value_unit"]="percent"
    basket["chain"]="ABF"
    basket["dimension"]="financial_confirmation"
    basket["source"]="Derived median of 3037/3189/8046 monthly revenue YoY"
    basket["source_url"]="derived"
    basket["knowledge_time_method"]="max_component_publication_time"
    basket=basket.drop(columns=["period_m"])
    return pd.concat([history,basket[history.columns]],ignore_index=True,sort=False)


def scan_operating_correlations(
    history: pd.DataFrame,
    *,
    config: OperatingCorrelationConfig=OperatingCorrelationConfig(),
) -> pd.DataFrame:
    frame=build_abf_basket(history)
    features=[
        m for m in frame.loc[frame["source_id"]=="tpca_public_industry","metric_id"].dropna().unique()
    ]
    targets=[
        m for m in frame["metric_id"].dropna().astype(str).unique()
        if m.startswith("abf_company_revenue_yoy::") or m=="abf_revenue_yoy_basket"
    ]
    rows=[]
    for feature in features:
        for target in targets:
            for lag in config.lags:
                row=evaluate_pair(frame,feature,target,lag,method=config.method,oos_fraction=config.oos_fraction)
                if row["sample_size"]>=config.min_samples and not np.isnan(row["spearman"]):
                    rows.append(row)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["score","sample_size","spearman"],ascending=[False,False,False]).reset_index(drop=True)
