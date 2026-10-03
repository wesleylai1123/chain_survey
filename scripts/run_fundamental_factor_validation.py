from __future__ import annotations

from pathlib import Path
import argparse
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

import numpy as np
import pandas as pd

from core.panel_correlation_engine import scan_panel_correlations
from core.factor_validation_engine import validate_factor_oos
DEFAULT_DATASET=ROOT/"artifacts"/"factor_validation_dataset.csv"
DEFAULT_CATALOG=ROOT/"data"/"fundamental_factor_catalog.csv"
DEFAULT_OUTPUT=ROOT/"artifacts"/"fundamental_factor_validation.csv"

CANDIDATE_STATUSES={"CALIBRATION_ELIGIBLE","CALIBRATION_CANDIDATE"}
TARGETS=("future_3m_return","future_6m_return","future_12m_return")


def eligible_factors(data: pd.DataFrame, catalog: pd.DataFrame, min_non_null: int=24) -> list[str]:
    allowed=catalog[catalog["model_status"].isin(CANDIDATE_STATUSES)]["factor"].astype(str).tolist()
    result=[]
    for factor in allowed:
        if factor not in data.columns:
            continue
        if pd.to_numeric(data[factor],errors="coerce").notna().sum() >= min_non_null:
            result.append(factor)
    return sorted(set(result))


def return_basis_summary(data: pd.DataFrame) -> tuple[str,bool]:
    if "return_basis" not in data:
        return "UNKNOWN",False
    values=sorted(set(data["return_basis"].dropna().astype(str)))
    basis=" | ".join(values) if values else "UNKNOWN"
    adjusted=bool(values) and all("ADJUSTED" in value and "UNADJUSTED" not in value for value in values)
    return basis,adjusted


def validate_fundamental_factors(
    data: pd.DataFrame,
    catalog: pd.DataFrame,
    *,
    min_non_null: int=24,
    min_samples: int=24,
    train_fraction: float=0.70,
) -> pd.DataFrame:
    factors=eligible_factors(data,catalog,min_non_null=min_non_null)
    if not factors:
        return pd.DataFrame()
    catalog_by=catalog.set_index("factor",drop=False)
    basis,adjusted=return_basis_summary(data)
    rows=[]
    cycle_column="cycle" if "cycle" in data and data["cycle"].astype(str).ne("Unknown").any() else None

    for target in TARGETS:
        if target not in data:
            continue
        scan=scan_panel_correlations(
            data,"ticker","report_date",target,
            cycle_column=cycle_column,
            feature_columns=factors,
            method="spearman",feature_transform="level",target_transform="level",
            lags=(0,),min_samples=min_samples,min_group_samples=3,
        )
        scan_by=scan.set_index("feature") if not scan.empty else pd.DataFrame()
        for factor in factors:
            if scan.empty or factor not in scan_by.index:
                continue
            corr=scan_by.loc[factor]
            try:
                oos=validate_factor_oos(
                    data,factor,target,
                    entity_column="ticker",time_column="report_date",
                    cycle_column=cycle_column,method="spearman",
                    train_fraction=train_fraction,industry_neutral=False,min_group_samples=3,
                )
            except (ValueError,KeyError):
                continue
            meta=catalog_by.loc[factor] if factor in catalog_by.index else {}
            candidate=(
                adjusted
                and oos.direction_consistent
                and oos.out_of_sample_samples >= 12
                and abs(oos.out_of_sample_correlation) >= 0.10
                and float(corr["company_sign_agreement"]) >= 0.60
            )
            if not adjusted:
                assessment="RESEARCH_ONLY_RAW_RETURN_BASIS"
            elif candidate:
                assessment="OOS_CANDIDATE"
            elif not oos.direction_consistent:
                assessment="OOS_DIRECTION_UNSTABLE"
            else:
                assessment="INSUFFICIENT_ROBUSTNESS"
            rows.append({
                "factor":factor,
                "category":meta.get("category","") if hasattr(meta,"get") else "",
                "factor_status":meta.get("model_status","") if hasattr(meta,"get") else "",
                "factor_basis":meta.get("basis","") if hasattr(meta,"get") else "",
                "source":meta.get("source","") if hasattr(meta,"get") else "",
                "target":target,
                "return_basis":basis,
                "adjusted_return_basis":adjusted,
                "pooled_spearman":float(corr["pooled_correlation"]),
                "company_median_r":float(corr["median_company_correlation"]),
                "company_sign_agreement":float(corr["company_sign_agreement"]),
                "sample_size":int(corr["sample_size"]),
                "split_date":oos.split_date,
                "in_sample_r":oos.in_sample_correlation,
                "out_of_sample_r":oos.out_of_sample_correlation,
                "direction_consistent":oos.direction_consistent,
                "oos_samples":oos.out_of_sample_samples,
                "degradation":oos.degradation,
                "robust_score":abs(oos.out_of_sample_correlation) if oos.direction_consistent else 0.0,
                "assessment":assessment,
            })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(
        ["assessment","robust_score","oos_samples"],ascending=[True,False,False]
    ).reset_index(drop=True)


def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument("--dataset",type=Path,default=DEFAULT_DATASET)
    p.add_argument("--catalog",type=Path,default=DEFAULT_CATALOG)
    p.add_argument("--output",type=Path,default=DEFAULT_OUTPUT)
    args=p.parse_args()
    data=pd.read_csv(args.dataset)
    catalog=pd.read_csv(args.catalog).fillna("")
    out=validate_fundamental_factors(data,catalog)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    out.to_csv(args.output,index=False)
    print(f"FUNDAMENTAL_VALIDATION_OK rows={len(out)} factors={out['factor'].nunique() if not out.empty else 0}")
    if not out.empty:
        print(out[[
            "factor","target","return_basis","pooled_spearman","out_of_sample_r",
            "direction_consistent","oos_samples","assessment"
        ]].head(40).to_string(index=False))


if __name__=="__main__":
    main()
