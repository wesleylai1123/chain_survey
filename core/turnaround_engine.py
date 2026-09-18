from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np
import pandas as pd


TARGET_COLUMNS = ("future_3m_return", "future_6m_return", "future_12m_return")


@dataclass(frozen=True)
class TurnaroundWeights:
    revenue_acceleration: float = 0.25
    gross_margin_momentum: float = 0.20
    operating_margin_momentum: float = 0.15
    eps_acceleration: float = 0.20
    cashflow_momentum: float = 0.10
    inventory_relief: float = 0.05
    cycle: float = 0.05

    def as_dict(self) -> dict[str, float]:
        return {
            "revenue_acceleration": self.revenue_acceleration,
            "gross_margin_momentum": self.gross_margin_momentum,
            "operating_margin_momentum": self.operating_margin_momentum,
            "eps_acceleration": self.eps_acceleration,
            "cashflow_momentum": self.cashflow_momentum,
            "inventory_relief": self.inventory_relief,
            "cycle": self.cycle,
        }


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce").replace([np.inf, -np.inf], np.nan)


def _combine(primary: pd.Series, fallback: pd.Series) -> pd.Series:
    return primary.combine_first(fallback)


def _cycle_value(cycle: object) -> float:
    # A recovery regime is more useful for a turnaround detector than a mature expansion.
    return {
        "Contraction": 0.00,
        "Slowdown": 0.25,
        "Expansion": 0.75,
        "Recovery": 1.00,
    }.get(str(cycle), np.nan)


def _pct_rank_by_period(frame: pd.DataFrame, column: str) -> pd.Series:
    values = pd.to_numeric(frame[column], errors="coerce")
    return values.groupby(frame["report_date"]).rank(method="average", pct=True)


def _stage(row: pd.Series) -> str:
    revenue_growth = row.get("revenue_growth")
    revenue_acceleration = row.get("revenue_acceleration")
    score = row.get("turnaround_score")
    improving = int(row.get("improving_signal_count", 0) or 0)
    crossings = int(row.get("positive_crossing_count", 0) or 0)
    gm_momentum = row.get("gross_margin_momentum")
    op_momentum = row.get("operating_margin_momentum")

    if pd.notna(score) and score < 35 and improving <= 1:
        return "Deteriorating"
    if pd.notna(revenue_growth) and revenue_growth < 0 and pd.notna(revenue_acceleration) and revenue_acceleration > 0 and improving >= 3:
        return "Early reversal"
    if crossings > 0 or str(row.get("cycle")) == "Recovery":
        if improving >= 3:
            return "Recovery"
    if (
        pd.notna(revenue_growth)
        and revenue_growth >= 0
        and pd.notna(gm_momentum)
        and gm_momentum > 0
        and pd.notna(op_momentum)
        and op_momentum > 0
        and improving >= 3
    ):
        return "Expansion"
    return "Mixed"


def _format_pct(value: object, digits: int = 1) -> str:
    if pd.isna(value):
        return "-"
    return f"{float(value) * 100:+.{digits}f}%"


def _driver_summary(row: pd.Series) -> str:
    candidates = [
        ("Revenue accel", row.get("revenue_acceleration")),
        ("GM Δ", row.get("gross_margin_momentum")),
        ("Op margin Δ", row.get("operating_margin_momentum")),
        ("EPS accel", row.get("eps_acceleration")),
        ("OCF margin Δ", row.get("cashflow_momentum")),
        ("Inventory relief", row.get("inventory_relief")),
    ]
    positive = [(name, value) for name, value in candidates if pd.notna(value) and float(value) > 0]
    positive.sort(key=lambda item: abs(float(item[1])), reverse=True)
    if not positive:
        return "No positive inflection signal"
    return " | ".join(f"{name} {_format_pct(value)}" for name, value in positive[:3])


def build_turnaround_history(
    panel: pd.DataFrame,
    *,
    min_history: int = 5,
    weights: TurnaroundWeights = TurnaroundWeights(),
) -> pd.DataFrame:
    """Build point-in-time turnaround features and a cross-sectional score for every period.

    The score intentionally uses only contemporaneous and lagged fundamental observations.
    Future-return columns may remain in the returned frame for validation, but they are never
    inputs to the score. Cross-sectional percentile ranks avoid imposing arbitrary absolute
    thresholds before the research layer has validated them.
    """
    if panel.empty:
        return panel.copy()
    required = {"ticker", "report_date"}
    missing = required - set(panel.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    frame = panel.copy()
    frame["report_date"] = frame["report_date"].astype(str)
    frame = frame.sort_values(["ticker", "report_date"]).reset_index(drop=True)
    group = frame.groupby("ticker", sort=False)
    frame["history_count"] = group.cumcount() + 1

    monthly_growth = _numeric(frame, "monthly_revenue_3m_yoy")
    quarterly_growth = _numeric(frame, "revenue_yoy")
    frame["revenue_growth"] = _combine(monthly_growth, quarterly_growth)
    frame["revenue_acceleration"] = frame["revenue_growth"] - group["revenue_growth"].shift(1)

    gross_margin = _numeric(frame, "gross_margin")
    gross_margin_qoq = _numeric(frame, "gross_margin_qoq")
    frame["gross_margin_momentum"] = _combine(gross_margin_qoq, gross_margin - group["gross_margin"].shift(1))

    frame["operating_margin_level"] = _numeric(frame, "operating_margin")
    frame["operating_margin_momentum"] = frame["operating_margin_level"] - group["operating_margin_level"].shift(1)

    frame["eps_growth"] = _numeric(frame, "eps_yoy")
    frame["eps_acceleration"] = frame["eps_growth"] - group["eps_growth"].shift(1)

    frame["ocf_margin_level"] = _numeric(frame, "ocf_margin")
    frame["cashflow_momentum"] = frame["ocf_margin_level"] - group["ocf_margin_level"].shift(1)

    frame["inventory_growth"] = _numeric(frame, "inventory_yoy")
    frame["inventory_relief"] = group["inventory_growth"].shift(1) - frame["inventory_growth"]

    previous_revenue_growth = group["revenue_growth"].shift(1)
    previous_eps_growth = group["eps_growth"].shift(1)
    frame["positive_crossing_count"] = (
        ((previous_revenue_growth <= 0) & (frame["revenue_growth"] > 0)).fillna(False).astype(int)
        + ((previous_eps_growth <= 0) & (frame["eps_growth"] > 0)).fillna(False).astype(int)
    )

    oriented_features = [
        "revenue_acceleration",
        "gross_margin_momentum",
        "operating_margin_momentum",
        "eps_acceleration",
        "cashflow_momentum",
        "inventory_relief",
    ]
    frame["improving_signal_count"] = sum((frame[col] > 0).fillna(False).astype(int) for col in oriented_features)
    frame["deteriorating_signal_count"] = sum((frame[col] < 0).fillna(False).astype(int) for col in oriented_features)
    frame["cycle_score"] = frame.get("cycle", pd.Series(index=frame.index, dtype=object)).map(_cycle_value)

    score_weights: Mapping[str, float] = weights.as_dict()
    feature_to_score_column = {
        "revenue_acceleration": "revenue_acceleration_pctile",
        "gross_margin_momentum": "gross_margin_momentum_pctile",
        "operating_margin_momentum": "operating_margin_momentum_pctile",
        "eps_acceleration": "eps_acceleration_pctile",
        "cashflow_momentum": "cashflow_momentum_pctile",
        "inventory_relief": "inventory_relief_pctile",
    }
    for feature, score_col in feature_to_score_column.items():
        frame[score_col] = _pct_rank_by_period(frame, feature)

    numerator = pd.Series(0.0, index=frame.index)
    denominator = pd.Series(0.0, index=frame.index)
    for feature, score_col in feature_to_score_column.items():
        weight = float(score_weights[feature])
        valid = frame[score_col].notna()
        numerator = numerator + frame[score_col].fillna(0.0) * weight
        denominator = denominator + valid.astype(float) * weight
    cycle_valid = frame["cycle_score"].notna()
    numerator = numerator + frame["cycle_score"].fillna(0.0) * float(score_weights["cycle"])
    denominator = denominator + cycle_valid.astype(float) * float(score_weights["cycle"])

    frame["turnaround_score"] = np.where(denominator > 0, numerator / denominator * 100.0, np.nan)
    total_weight = sum(float(value) for value in score_weights.values())
    history_quality = (frame["history_count"] / max(min_history + 3, 1)).clip(upper=1.0)
    frame["signal_coverage"] = (denominator / total_weight).clip(0.0, 1.0)
    frame["confidence"] = (frame["signal_coverage"] * history_quality * 100.0).clip(0.0, 100.0)

    frame.loc[frame["history_count"] < min_history, "turnaround_score"] = np.nan
    frame["stage"] = frame.apply(_stage, axis=1)
    frame["driver_summary"] = frame.apply(_driver_summary, axis=1)
    return frame


def build_turnaround_radar(
    panel: pd.DataFrame,
    *,
    min_history: int = 5,
    weights: TurnaroundWeights = TurnaroundWeights(),
) -> pd.DataFrame:
    history = build_turnaround_history(panel, min_history=min_history, weights=weights)
    if history.empty:
        return history
    latest = history.sort_values(["ticker", "report_date"]).groupby("ticker", as_index=False).tail(1).copy()
    latest = latest[latest["turnaround_score"].notna()].copy()
    latest["rank"] = latest["turnaround_score"].rank(method="min", ascending=False).astype(int)
    return latest.sort_values(["turnaround_score", "confidence", "ticker"], ascending=[False, False, True]).reset_index(drop=True)


def validate_turnaround_signal(
    panel: pd.DataFrame,
    *,
    target: str = "future_6m_return",
    min_history: int = 5,
    weights: TurnaroundWeights = TurnaroundWeights(),
) -> dict[str, float | int | str]:
    if target not in panel.columns:
        raise ValueError(f"Missing target column: {target}")
    history = build_turnaround_history(panel, min_history=min_history, weights=weights)
    work = history[["turnaround_score", target]].copy()
    work[target] = pd.to_numeric(work[target], errors="coerce")
    work = work.dropna()
    if len(work) < 5:
        return {
            "target": target,
            "samples": len(work),
            "spearman_ic": np.nan,
            "top_quintile_return": np.nan,
            "bottom_quintile_return": np.nan,
            "top_bottom_spread": np.nan,
        }
    ic = work["turnaround_score"].corr(work[target], method="spearman")
    low_cut = work["turnaround_score"].quantile(0.20)
    high_cut = work["turnaround_score"].quantile(0.80)
    bottom = work.loc[work["turnaround_score"] <= low_cut, target].mean()
    top = work.loc[work["turnaround_score"] >= high_cut, target].mean()
    return {
        "target": target,
        "samples": int(len(work)),
        "spearman_ic": float(ic) if pd.notna(ic) else np.nan,
        "top_quintile_return": float(top) if pd.notna(top) else np.nan,
        "bottom_quintile_return": float(bottom) if pd.notna(bottom) else np.nan,
        "top_bottom_spread": float(top - bottom) if pd.notna(top) and pd.notna(bottom) else np.nan,
    }
