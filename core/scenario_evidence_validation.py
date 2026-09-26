from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from core.driver_validation_engine import benjamini_hochberg, block_bootstrap_ci, block_permutation_pvalue
from core.operating_correlation_engine import build_abf_basket

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_SPEC=ROOT/"data"/"abf_scenario_evidence_spec.json"


@dataclass(frozen=True)
class ScenarioValidationConfig:
    min_samples: int=10
    min_abs_spearman: float=0.20
    min_direction_hit_rate: float=0.60
    min_abs_oos: float=0.15
    bootstrap_iterations: int=1000
    permutation_iterations: int=1000
    block_size: int=3
    random_seed: int=20260926


def load_scenario_spec(path: str | Path=DEFAULT_SPEC) -> dict:
    payload=json.loads(Path(path).read_text(encoding="utf-8"))
    if set(payload.get("scenarios",{}))!={"UPSIDE","DOWNSIDE"}:
        raise ValueError("Scenario spec must define UPSIDE and DOWNSIDE")
    return payload


def _prepare_metric(frame: pd.DataFrame, metric_id: str, transform: str) -> pd.DataFrame:
    sub=frame[frame["metric_id"]==metric_id][["period","published_at","change_pct"]].copy()
    sub["period_m"]=pd.PeriodIndex(sub["period"].astype(str).str[:7],freq="M")
    sub["change_pct"]=pd.to_numeric(sub["change_pct"],errors="coerce")
    sub=sub.sort_values("period_m")
    if transform=="LEVEL":
        sub["signal_value"]=sub["change_pct"]
    elif transform=="MOMENTUM":
        sub["signal_value"]=sub["change_pct"].diff()
    else:
        raise ValueError(f"Unsupported transform: {transform}")
    return sub.dropna(subset=["signal_value"])


def _align_transformed(
    history: pd.DataFrame,
    feature_metric: str,
    target_metric: str,
    lag_months: int,
    feature_transform: str,
    target_transform: str,
) -> pd.DataFrame:
    frame=build_abf_basket(history).copy()
    feature=_prepare_metric(frame,feature_metric,feature_transform).rename(
        columns={"published_at":"feature_published_at","signal_value":"x"}
    )
    target=_prepare_metric(frame,target_metric,target_transform).rename(
        columns={"published_at":"target_published_at","signal_value":"y","period_m":"target_period"}
    )
    feature["target_period"]=feature["period_m"]+int(lag_months)
    aligned=feature[["period_m","target_period","feature_published_at","x"]].merge(
        target[["target_period","target_published_at","y"]],
        on="target_period",
        how="inner",
    )
    aligned=aligned[aligned["feature_published_at"]<=aligned["target_published_at"]]
    return aligned.sort_values("period_m").reset_index(drop=True)


def _scenario_subset(
    aligned: pd.DataFrame,
    scenario: str,
    *,
    feature_trigger: str,
    target_trigger: str,
) -> pd.DataFrame:
    if feature_trigger not in {"POSITIVE","NEGATIVE"}:
        raise ValueError(feature_trigger)
    if target_trigger not in {"POSITIVE","NEGATIVE"}:
        raise ValueError(target_trigger)
    feature_mask=aligned["x"]>0 if feature_trigger=="POSITIVE" else aligned["x"]<0
    side=aligned[feature_mask].copy()
    if scenario not in {"UPSIDE","DOWNSIDE"}:
        raise ValueError(scenario)
    return side


def _safe_corr(frame: pd.DataFrame) -> float:
    if len(frame)<3 or frame["x"].nunique()<2 or frame["y"].nunique()<2:
        return float("nan")
    return float(frame["x"].corr(frame["y"],method="spearman"))


def validate_scenario_source(
    history: pd.DataFrame,
    *,
    scenario: str,
    metric_id: str,
    target_metric: str,
    lag_months: int,
    feature_transform: str="LEVEL",
    target_transform: str="LEVEL",
    feature_trigger: str="POSITIVE",
    target_trigger: str="POSITIVE",
    config: ScenarioValidationConfig=ScenarioValidationConfig(),
) -> dict[str,object]:
    aligned=_align_transformed(
        history,
        metric_id,
        target_metric,
        lag_months,
        feature_transform,
        target_transform,
    )
    side=_scenario_subset(
        aligned,
        scenario,
        feature_trigger=feature_trigger,
        target_trigger=target_trigger,
    ).reset_index(drop=True)
    n=len(side)
    corr=_safe_corr(side)

    desired_positive=target_trigger=="POSITIVE"
    if n:
        hits=(side["y"]>0) if desired_positive else (side["y"]<0)
        hit_rate=float(hits.mean())
    else:
        hit_rate=float("nan")

    split=max(3,int(n*0.70))
    test=side.iloc[split:] if n>split else side.iloc[0:0]
    oos_corr=_safe_corr(test)

    seed=config.random_seed + (0 if scenario=="UPSIDE" else 10000)
    if n>=6:
        boot_lo,boot_hi=block_bootstrap_ci(
            side,iterations=config.bootstrap_iterations,block_size=config.block_size,seed=seed
        )
        pvalue=block_permutation_pvalue(
            side,iterations=config.permutation_iterations,block_size=config.block_size,seed=seed+1
        )
    else:
        boot_lo=boot_hi=pvalue=float("nan")

    bootstrap_excludes_zero=bool(
        not np.isnan(boot_lo) and not np.isnan(boot_hi)
        and ((boot_lo>0 and boot_hi>0) or (boot_lo<0 and boot_hi<0))
    )
    expected_corr_positive=True
    gates={
        "sample_size": n>=config.min_samples,
        "correlation_direction": (not np.isnan(corr)) and ((corr>0)==expected_corr_positive) and abs(corr)>=config.min_abs_spearman,
        "target_direction_hit_rate": (not np.isnan(hit_rate)) and hit_rate>=config.min_direction_hit_rate,
        "oos_direction": (not np.isnan(oos_corr)) and oos_corr>0 and abs(oos_corr)>=config.min_abs_oos,
        "bootstrap_excludes_zero": bootstrap_excludes_zero,
        "permutation_p": (not np.isnan(pvalue)) and pvalue<=0.10,
    }
    status="VALIDATED" if all(gates.values()) else ("INSUFFICIENT" if not gates["sample_size"] else "CANDIDATE")
    return {
        "scenario":scenario,
        "metric_id":metric_id,
        "target_metric":target_metric,
        "lag_months":lag_months,
        "feature_transform":feature_transform,
        "target_transform":target_transform,
        "feature_trigger":feature_trigger,
        "target_trigger":target_trigger,
        "sample_size":n,
        "spearman":corr,
        "target_direction_hit_rate":hit_rate,
        "oos_spearman":oos_corr,
        "bootstrap_ci_low":boot_lo,
        "bootstrap_ci_high":boot_hi,
        "permutation_p":pvalue,
        "gate_pass_count":sum(bool(v) for v in gates.values()),
        "gate_count":len(gates),
        "status":status,
        "gates":gates,
    }


def validate_abf_scenarios(
    history: pd.DataFrame,
    *,
    spec_path: str | Path=DEFAULT_SPEC,
    config: ScenarioValidationConfig=ScenarioValidationConfig(),
) -> tuple[pd.DataFrame, dict]:
    spec=load_scenario_spec(spec_path)
    target=spec["target_metric"]
    rows=[]
    details={}
    for scenario,side_spec in spec["scenarios"].items():
        for source in side_spec.get("leading_sources",[]):
            result=validate_scenario_source(
                history,
                scenario=scenario,
                metric_id=source["metric_id"],
                target_metric=target,
                lag_months=int(source["lag_months"]),
                feature_transform=str(source.get("feature_transform","LEVEL")),
                target_transform=str(source.get("target_transform","LEVEL")),
                feature_trigger=str(source.get("trigger","POSITIVE")),
                target_trigger=str(source.get("target_trigger","POSITIVE")),
                config=config,
            )
            result["source_id"]=source["source_id"]
            result["source_name"]=source["source_name"]
            result["role"]=source["role"]
            rows.append({k:v for k,v in result.items() if k!="gates"})
            details[f"{scenario}|{source['metric_id']}"]=result
    table=pd.DataFrame(rows)
    if table.empty:
        return table,details

    table["fdr_q"]=np.nan
    for scenario in ("UPSIDE","DOWNSIDE"):
        mask=table["scenario"]==scenario
        if mask.any():
            table.loc[mask,"fdr_q"]=benjamini_hochberg(table.loc[mask,"permutation_p"]).to_numpy()

    table["fdr_pass"]=table["fdr_q"]<=0.10
    for idx,row in table.iterrows():
        base_status=str(row["status"])
        if base_status=="VALIDATED" and not bool(row["fdr_pass"]):
            table.at[idx,"status"]="CANDIDATE"
        key=f"{row['scenario']}|{row['metric_id']}"
        if key in details:
            details[key]["fdr_q"]=None if pd.isna(row["fdr_q"]) else float(row["fdr_q"])
            details[key]["fdr_pass"]=bool(row["fdr_pass"]) if not pd.isna(row["fdr_q"]) else False
            details[key]["status"]=str(table.at[idx,"status"])
    return table,details
