from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

from core.correlation_engine import METHODS, TRANSFORMS, transform_series


@dataclass(frozen=True)
class PanelCorrelationResult:
    x_column: str
    y_column: str
    method: str
    x_transform: str
    y_transform: str
    lag: int
    pooled_correlation: float
    sample_size: int
    entity_count: int
    period_count: int
    median_company_correlation: float
    company_sign_agreement: float
    median_cross_sectional_correlation: float
    cross_sectional_sign_agreement: float
    median_cycle_correlation: float
    cycle_sign_agreement: float
    cycle_count: int
    generalization_score: float
    aligned: pd.DataFrame
    company_correlations: pd.DataFrame
    cross_sectional_correlations: pd.DataFrame
    cycle_correlations: pd.DataFrame


def _safe_corr(frame: pd.DataFrame, method: str) -> float:
    if method not in METHODS:
        raise ValueError(f"Unsupported correlation method: {method}")
    if len(frame) < 2 or frame["x"].nunique() < 2 or frame["y"].nunique() < 2:
        return float("nan")
    return float(frame["x"].corr(frame["y"], method=method))


def _median_or_nan(values: pd.Series) -> float:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    return float(clean.median()) if not clean.empty else float("nan")


def _sign_agreement(values: pd.Series, reference: float) -> float:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    clean = clean[clean != 0]
    if clean.empty or np.isnan(reference) or reference == 0:
        return float("nan")
    return float((np.sign(clean) == np.sign(reference)).mean())


def _group_correlations(
    aligned: pd.DataFrame,
    group_column: str,
    method: str,
    min_group_samples: int,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for group, frame in aligned.groupby(group_column, sort=False, dropna=False):
        if len(frame) < min_group_samples:
            continue
        corr = _safe_corr(frame, method)
        if np.isnan(corr):
            continue
        rows.append({group_column: group, "correlation": corr, "sample_size": len(frame)})
    return pd.DataFrame(rows, columns=[group_column, "correlation", "sample_size"])


def prepare_panel_pair(
    data: pd.DataFrame,
    entity_column: str,
    time_column: str,
    x_column: str,
    y_column: str,
    *,
    cycle_column: str | None = None,
    x_transform: str = "level",
    y_transform: str = "level",
    transform_periods: int = 1,
    lag: int = 0,
) -> pd.DataFrame:
    """Align an X/Y pair within each entity without crossing entity boundaries.

    Positive lag means X leads Y by that many rows inside the same entity. All
    transforms, including percent changes and forward returns, are computed inside
    each entity before observations are pooled for cross-company analysis.
    """
    required = [entity_column, time_column, x_column, y_column]
    if cycle_column:
        required.append(cycle_column)
    missing = [column for column in required if column not in data.columns]
    if missing:
        raise KeyError(f"Missing columns: {missing}")
    if x_transform not in TRANSFORMS or y_transform not in TRANSFORMS:
        raise ValueError("Unsupported transform")
    if transform_periods < 1:
        raise ValueError("transform_periods must be >= 1")

    ordered = data.copy().sort_values([entity_column, time_column], kind="stable").reset_index(drop=True)
    x_values = pd.Series(np.nan, index=ordered.index, dtype=float)
    y_values = pd.Series(np.nan, index=ordered.index, dtype=float)

    for _, indices in ordered.groupby(entity_column, sort=False).groups.items():
        idx = list(indices)
        x = transform_series(ordered.loc[idx, x_column], x_transform, transform_periods)
        y = transform_series(ordered.loc[idx, y_column], y_transform, transform_periods)
        x.index = idx
        y.index = idx
        if lag:
            y = y.shift(-lag)
        x_values.loc[idx] = x
        y_values.loc[idx] = y

    columns: dict[str, object] = {
        "entity": ordered[entity_column],
        "time": ordered[time_column],
        "x": x_values,
        "y": y_values,
    }
    if cycle_column:
        columns["cycle"] = ordered[cycle_column]

    aligned = pd.DataFrame(columns).replace([np.inf, -np.inf], np.nan).dropna(subset=["x", "y"])
    return aligned.reset_index(drop=True)


def compute_panel_correlation(
    data: pd.DataFrame,
    entity_column: str,
    time_column: str,
    x_column: str,
    y_column: str,
    *,
    cycle_column: str | None = None,
    method: str = "spearman",
    x_transform: str = "pct_change",
    y_transform: str = "forward_return",
    transform_periods: int = 1,
    lag: int = 0,
    min_group_samples: int = 4,
) -> PanelCorrelationResult:
    aligned = prepare_panel_pair(
        data,
        entity_column,
        time_column,
        x_column,
        y_column,
        cycle_column=cycle_column,
        x_transform=x_transform,
        y_transform=y_transform,
        transform_periods=transform_periods,
        lag=lag,
    )
    pooled = _safe_corr(aligned, method)

    company = _group_correlations(aligned, "entity", method, min_group_samples)
    cross_sectional = _group_correlations(aligned, "time", method, min_group_samples)
    if cycle_column:
        cycles = _group_correlations(aligned, "cycle", method, min_group_samples)
    else:
        cycles = pd.DataFrame(columns=["cycle", "correlation", "sample_size"])

    company_median = _median_or_nan(company["correlation"])
    cross_median = _median_or_nan(cross_sectional["correlation"])
    cycle_median = _median_or_nan(cycles["correlation"])
    company_agreement = _sign_agreement(company["correlation"], pooled)
    cross_agreement = _sign_agreement(cross_sectional["correlation"], pooled)
    cycle_agreement = _sign_agreement(cycles["correlation"], pooled)

    agreements = [value for value in (company_agreement, cross_agreement, cycle_agreement) if not np.isnan(value)]
    robustness = float(np.mean(agreements)) if agreements else 0.0
    generalization_score = 0.0 if np.isnan(pooled) else abs(pooled) * robustness

    return PanelCorrelationResult(
        x_column=x_column,
        y_column=y_column,
        method=method,
        x_transform=x_transform,
        y_transform=y_transform,
        lag=lag,
        pooled_correlation=pooled,
        sample_size=len(aligned),
        entity_count=int(aligned["entity"].nunique()),
        period_count=int(aligned["time"].nunique()),
        median_company_correlation=company_median,
        company_sign_agreement=company_agreement,
        median_cross_sectional_correlation=cross_median,
        cross_sectional_sign_agreement=cross_agreement,
        median_cycle_correlation=cycle_median,
        cycle_sign_agreement=cycle_agreement,
        cycle_count=int(aligned["cycle"].nunique()) if "cycle" in aligned else 0,
        generalization_score=generalization_score,
        aligned=aligned,
        company_correlations=company,
        cross_sectional_correlations=cross_sectional,
        cycle_correlations=cycles,
    )


def scan_panel_correlations(
    data: pd.DataFrame,
    entity_column: str,
    time_column: str,
    target_column: str,
    *,
    cycle_column: str | None = None,
    feature_columns: Iterable[str] | None = None,
    method: str = "spearman",
    feature_transform: str = "pct_change",
    target_transform: str = "forward_return",
    transform_periods: int = 1,
    lags: Iterable[int] = range(0, 5),
    min_samples: int = 20,
    min_group_samples: int = 4,
) -> pd.DataFrame:
    """Scan candidate factors and report raw cross-company generalization metrics."""
    metadata = {entity_column, time_column, target_column}
    if cycle_column:
        metadata.add(cycle_column)
    if feature_columns is None:
        feature_columns = [
            column
            for column in data.columns
            if column not in metadata and pd.to_numeric(data[column], errors="coerce").notna().sum() >= min_samples
        ]

    rows: list[dict[str, object]] = []
    for feature in feature_columns:
        if feature == target_column:
            continue
        for lag in lags:
            result = compute_panel_correlation(
                data,
                entity_column,
                time_column,
                feature,
                target_column,
                cycle_column=cycle_column,
                method=method,
                x_transform=feature_transform,
                y_transform=target_transform,
                transform_periods=transform_periods,
                lag=int(lag),
                min_group_samples=min_group_samples,
            )
            if result.sample_size < min_samples or np.isnan(result.pooled_correlation):
                continue
            rows.append(
                {
                    "feature": feature,
                    "target": target_column,
                    "lag": int(lag),
                    "pooled_correlation": result.pooled_correlation,
                    "abs_pooled_correlation": abs(result.pooled_correlation),
                    "sample_size": result.sample_size,
                    "entity_count": result.entity_count,
                    "median_company_correlation": result.median_company_correlation,
                    "company_sign_agreement": result.company_sign_agreement,
                    "median_cross_sectional_correlation": result.median_cross_sectional_correlation,
                    "cross_sectional_sign_agreement": result.cross_sectional_sign_agreement,
                    "median_cycle_correlation": result.median_cycle_correlation,
                    "cycle_sign_agreement": result.cycle_sign_agreement,
                    "cycle_count": result.cycle_count,
                    "generalization_score": result.generalization_score,
                }
            )

    columns = [
        "feature",
        "target",
        "lag",
        "pooled_correlation",
        "abs_pooled_correlation",
        "sample_size",
        "entity_count",
        "median_company_correlation",
        "company_sign_agreement",
        "median_cross_sectional_correlation",
        "cross_sectional_sign_agreement",
        "median_cycle_correlation",
        "cycle_sign_agreement",
        "cycle_count",
        "generalization_score",
    ]
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows, columns=columns).sort_values(
        ["generalization_score", "abs_pooled_correlation", "sample_size"],
        ascending=[False, False, False],
    ).reset_index(drop=True)
