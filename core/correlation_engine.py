from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd


TRANSFORMS = ("level", "diff", "pct_change", "forward_return")
METHODS = ("pearson", "spearman")


@dataclass(frozen=True)
class CorrelationResult:
    x_column: str
    y_column: str
    method: str
    x_transform: str
    y_transform: str
    lag: int
    correlation: float
    sample_size: int
    first_half_correlation: float
    second_half_correlation: float
    stability_score: float

    @property
    def absolute_correlation(self) -> float:
        return abs(self.correlation)


def _numeric_series(values: pd.Series) -> pd.Series:
    return pd.to_numeric(values, errors="coerce").astype(float)


def transform_series(series: pd.Series, transform: str = "level", periods: int = 1) -> pd.Series:
    """Transform a numeric series without looking ahead, except explicit forward_return.

    forward_return at t is value[t + periods] / value[t] - 1 and is intended for
    target variables such as future stock returns.
    """
    if transform not in TRANSFORMS:
        raise ValueError(f"Unsupported transform: {transform}")
    if periods < 1:
        raise ValueError("periods must be >= 1")

    numeric = _numeric_series(series)
    if transform == "level":
        return numeric
    if transform == "diff":
        return numeric.diff(periods)
    if transform == "pct_change":
        return numeric.pct_change(periods=periods, fill_method=None)
    return numeric.shift(-periods).div(numeric).sub(1.0)


def prepare_pair(
    data: pd.DataFrame,
    x_column: str,
    y_column: str,
    *,
    x_transform: str = "level",
    y_transform: str = "level",
    transform_periods: int = 1,
    lag: int = 0,
) -> pd.DataFrame:
    """Return aligned X/Y observations.

    Positive lag means X leads Y: X[t] is compared with Y[t + lag].
    Negative lag compares X[t] with an earlier Y observation.
    """
    if x_column not in data.columns or y_column not in data.columns:
        missing = [name for name in (x_column, y_column) if name not in data.columns]
        raise KeyError(f"Missing columns: {missing}")

    x = transform_series(data[x_column], x_transform, transform_periods)
    y = transform_series(data[y_column], y_transform, transform_periods)
    if lag:
        y = y.shift(-lag)

    pair = pd.DataFrame({"x": x, "y": y}).replace([np.inf, -np.inf], np.nan).dropna()
    return pair


def _safe_corr(pair: pd.DataFrame, method: str) -> float:
    if method not in METHODS:
        raise ValueError(f"Unsupported correlation method: {method}")
    if len(pair) < 2 or pair["x"].nunique() < 2 or pair["y"].nunique() < 2:
        return float("nan")
    return float(pair["x"].corr(pair["y"], method=method))


def _split_correlations(pair: pd.DataFrame, method: str) -> tuple[float, float, float]:
    if len(pair) < 8:
        return float("nan"), float("nan"), 0.0

    midpoint = len(pair) // 2
    first = _safe_corr(pair.iloc[:midpoint], method)
    second = _safe_corr(pair.iloc[midpoint:], method)
    if np.isnan(first) or np.isnan(second):
        return first, second, 0.0

    sign_consistent = 1.0 if np.sign(first) == np.sign(second) else 0.0
    magnitude_consistency = max(0.0, 1.0 - abs(abs(first) - abs(second)))
    stability = sign_consistent * magnitude_consistency
    return first, second, float(stability)


def compute_correlation(
    data: pd.DataFrame,
    x_column: str,
    y_column: str,
    *,
    method: str = "pearson",
    x_transform: str = "level",
    y_transform: str = "level",
    transform_periods: int = 1,
    lag: int = 0,
) -> CorrelationResult:
    pair = prepare_pair(
        data,
        x_column,
        y_column,
        x_transform=x_transform,
        y_transform=y_transform,
        transform_periods=transform_periods,
        lag=lag,
    )
    corr = _safe_corr(pair, method)
    first, second, stability = _split_correlations(pair, method)
    return CorrelationResult(
        x_column=x_column,
        y_column=y_column,
        method=method,
        x_transform=x_transform,
        y_transform=y_transform,
        lag=lag,
        correlation=corr,
        sample_size=len(pair),
        first_half_correlation=first,
        second_half_correlation=second,
        stability_score=stability,
    )


def scan_correlations(
    data: pd.DataFrame,
    target_column: str,
    *,
    feature_columns: Iterable[str] | None = None,
    method: str = "spearman",
    feature_transform: str = "pct_change",
    target_transform: str = "forward_return",
    transform_periods: int = 1,
    lags: Iterable[int] = range(0, 5),
    min_samples: int = 8,
) -> pd.DataFrame:
    """Rank feature/lag combinations against a target.

    The default deliberately asks whether changes in a feature are associated with
    a future target return instead of correlating two trending raw levels.
    """
    if target_column not in data.columns:
        raise KeyError(f"Missing target column: {target_column}")

    if feature_columns is None:
        feature_columns = [
            column
            for column in data.columns
            if column != target_column and pd.to_numeric(data[column], errors="coerce").notna().sum() >= min_samples
        ]

    rows: list[dict[str, object]] = []
    for feature in feature_columns:
        if feature == target_column:
            continue
        for lag in lags:
            result = compute_correlation(
                data,
                feature,
                target_column,
                method=method,
                x_transform=feature_transform,
                y_transform=target_transform,
                transform_periods=transform_periods,
                lag=int(lag),
            )
            if result.sample_size < min_samples or np.isnan(result.correlation):
                continue
            rows.append(
                {
                    "feature": feature,
                    "target": target_column,
                    "lag": int(lag),
                    "correlation": result.correlation,
                    "abs_correlation": result.absolute_correlation,
                    "sample_size": result.sample_size,
                    "first_half": result.first_half_correlation,
                    "second_half": result.second_half_correlation,
                    "stability": result.stability_score,
                    "score": result.absolute_correlation * result.stability_score,
                }
            )

    if not rows:
        return pd.DataFrame(
            columns=[
                "feature",
                "target",
                "lag",
                "correlation",
                "abs_correlation",
                "sample_size",
                "first_half",
                "second_half",
                "stability",
                "score",
            ]
        )

    return pd.DataFrame(rows).sort_values(
        ["score", "abs_correlation", "sample_size"], ascending=[False, False, False]
    ).reset_index(drop=True)


def rolling_correlation(
    data: pd.DataFrame,
    x_column: str,
    y_column: str,
    *,
    window: int = 8,
    method: str = "pearson",
    x_transform: str = "level",
    y_transform: str = "level",
    transform_periods: int = 1,
    lag: int = 0,
) -> pd.Series:
    if window < 3:
        raise ValueError("window must be >= 3")
    pair = prepare_pair(
        data,
        x_column,
        y_column,
        x_transform=x_transform,
        y_transform=y_transform,
        transform_periods=transform_periods,
        lag=lag,
    )
    if method == "pearson":
        return pair["x"].rolling(window).corr(pair["y"])
    if method != "spearman":
        raise ValueError(f"Unsupported correlation method: {method}")

    return pair[["x", "y"]].rolling(window).apply(
        lambda values: pd.Series(values).rank().iloc[-1], raw=False
    )["x"].rolling(window).corr(pair["y"].rank())
