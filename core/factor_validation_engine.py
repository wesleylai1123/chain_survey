from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from core.panel_correlation_engine import compute_panel_correlation


@dataclass(frozen=True)
class OOSValidationResult:
    feature: str
    target: str
    split_date: str
    in_sample_correlation: float
    out_of_sample_correlation: float
    in_sample_samples: int
    out_of_sample_samples: int
    direction_consistent: bool
    degradation: float


def industry_neutralize(
    data: pd.DataFrame,
    value_column: str,
    *,
    industry_column: str = "industry",
    time_column: str = "report_date",
) -> pd.Series:
    """Demean a factor within industry and period to remove broad industry effects."""
    required = {value_column, industry_column, time_column}
    missing = required - set(data.columns)
    if missing:
        raise KeyError(f"Missing columns: {sorted(missing)}")
    values = pd.to_numeric(data[value_column], errors="coerce")
    frame = pd.DataFrame({
        "value": values,
        "industry": data[industry_column],
        "time": data[time_column],
    })
    group_mean = frame.groupby(["time", "industry"], dropna=False)["value"].transform("mean")
    return values - group_mean


def add_industry_neutral_factor(
    data: pd.DataFrame,
    value_column: str,
    *,
    industry_column: str = "industry",
    time_column: str = "report_date",
    suffix: str = "_industry_neutral",
) -> pd.DataFrame:
    result = data.copy()
    result[f"{value_column}{suffix}"] = industry_neutralize(
        result,
        value_column,
        industry_column=industry_column,
        time_column=time_column,
    )
    return result


def chronological_split(data: pd.DataFrame, time_column: str, train_fraction: float = 0.7) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    if not 0.5 <= train_fraction < 1.0:
        raise ValueError("train_fraction must be in [0.5, 1.0)")
    if time_column not in data.columns:
        raise KeyError(time_column)
    times = pd.Series(data[time_column].dropna().astype(str).unique()).sort_values().tolist()
    if len(times) < 4:
        raise ValueError("Need at least four distinct periods for out-of-sample validation")
    cut = min(max(int(len(times) * train_fraction), 1), len(times) - 1)
    split_date = times[cut]
    train = data[data[time_column].astype(str) < split_date].copy()
    test = data[data[time_column].astype(str) >= split_date].copy()
    return train, test, split_date


def validate_factor_oos(
    data: pd.DataFrame,
    feature: str,
    target: str,
    *,
    entity_column: str = "ticker",
    time_column: str = "report_date",
    cycle_column: str | None = "cycle",
    method: str = "spearman",
    train_fraction: float = 0.7,
    industry_neutral: bool = False,
    industry_column: str = "industry",
    min_group_samples: int = 3,
) -> OOSValidationResult:
    work = data.copy()
    feature_name = feature
    if industry_neutral:
        work = add_industry_neutral_factor(
            work,
            feature,
            industry_column=industry_column,
            time_column=time_column,
        )
        feature_name = f"{feature}_industry_neutral"

    train, test, split_date = chronological_split(work, time_column, train_fraction)
    train_result = compute_panel_correlation(
        train,
        entity_column,
        time_column,
        feature_name,
        target,
        cycle_column=cycle_column,
        method=method,
        x_transform="level",
        y_transform="level",
        min_group_samples=min_group_samples,
    )
    test_result = compute_panel_correlation(
        test,
        entity_column,
        time_column,
        feature_name,
        target,
        cycle_column=cycle_column,
        method=method,
        x_transform="level",
        y_transform="level",
        min_group_samples=min_group_samples,
    )
    ins, oos = train_result.pooled_correlation, test_result.pooled_correlation
    consistent = bool(not np.isnan(ins) and not np.isnan(oos) and np.sign(ins) == np.sign(oos))
    degradation = float("nan") if np.isnan(ins) or np.isnan(oos) else abs(ins) - abs(oos)
    return OOSValidationResult(
        feature=feature,
        target=target,
        split_date=split_date,
        in_sample_correlation=ins,
        out_of_sample_correlation=oos,
        in_sample_samples=train_result.sample_size,
        out_of_sample_samples=test_result.sample_size,
        direction_consistent=consistent,
        degradation=degradation,
    )


def scan_oos_factors(
    data: pd.DataFrame,
    target: str,
    *,
    feature_columns: list[str],
    industry_neutral: bool = True,
    train_fraction: float = 0.7,
) -> pd.DataFrame:
    rows = []
    for feature in feature_columns:
        try:
            result = validate_factor_oos(
                data,
                feature,
                target,
                industry_neutral=industry_neutral,
                train_fraction=train_fraction,
            )
        except (ValueError, KeyError):
            continue
        if np.isnan(result.in_sample_correlation) or np.isnan(result.out_of_sample_correlation):
            continue
        rows.append({
            "feature": feature,
            "target": target,
            "split_date": result.split_date,
            "in_sample_r": result.in_sample_correlation,
            "out_of_sample_r": result.out_of_sample_correlation,
            "direction_consistent": result.direction_consistent,
            "degradation": result.degradation,
            "in_sample_samples": result.in_sample_samples,
            "out_of_sample_samples": result.out_of_sample_samples,
            "robust_score": abs(result.out_of_sample_correlation) * (1.0 if result.direction_consistent else 0.0),
        })
    if not rows:
        return pd.DataFrame(columns=["feature","target","split_date","in_sample_r","out_of_sample_r","direction_consistent","degradation","in_sample_samples","out_of_sample_samples","robust_score"])
    return pd.DataFrame(rows).sort_values(["robust_score", "out_of_sample_samples"], ascending=[False, False]).reset_index(drop=True)
