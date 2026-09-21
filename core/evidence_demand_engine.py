from __future__ import annotations

from dataclasses import dataclass, field
from math import exp, log
from typing import Mapping

import pandas as pd


DIMENSION_WEIGHTS: Mapping[str, float] = {
    "buyer_commitment": 0.20,
    "orders_backlog": 0.20,
    "physical_throughput": 0.30,
    "market_tightness": 0.20,
    "financial_confirmation": 0.10,
}

SOURCE_RELIABILITY: Mapping[str, float] = {
    "government_statistic": 0.98,
    "regulatory_filing": 0.95,
    "company_actual": 0.90,
    "contract_commitment": 0.90,
    "company_guidance": 0.70,
    "supplier_commentary": 0.60,
    "channel_check": 0.50,
    "analyst_estimate": 0.45,
    "anonymous_news": 0.30,
    "social_rumor": 0.10,
    "synthetic_demo": 0.70,
}

REQUIRED_COLUMNS = {
    "evidence_id",
    "theme",
    "dimension",
    "chain",
    "evidence_group",
    "indicator",
    "as_of_date",
    "signal",
    "source_type",
}


@dataclass(frozen=True)
class DemandInferenceConfig:
    dimension_weights: Mapping[str, float] = field(default_factory=lambda: dict(DIMENSION_WEIGHTS))
    default_half_life_days: float = 90.0
    max_evidence_age_days: int = 730


def freshness_weight(age_days: float, half_life_days: float) -> float:
    if half_life_days <= 0:
        raise ValueError("half_life_days must be > 0")
    if age_days <= 0:
        return 1.0
    return exp(-log(2.0) * age_days / half_life_days)


def _validate(frame: pd.DataFrame) -> pd.DataFrame:
    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"Missing evidence columns: {sorted(missing)}")
    work = frame.copy()
    work["signal"] = pd.to_numeric(work["signal"], errors="coerce")
    if work["signal"].isna().any():
        raise ValueError("signal must be numeric")
    if ((work["signal"] < -1.0) | (work["signal"] > 1.0)).any():
        raise ValueError("signal must be within [-1, 1]")
    work["as_of_date"] = pd.to_datetime(work["as_of_date"], errors="coerce", utc=True, format="mixed")
    if work["as_of_date"].isna().any():
        raise ValueError("as_of_date contains invalid dates")
    return work


def score_evidence(
    evidence: pd.DataFrame,
    *,
    as_of_date: str | pd.Timestamp | None = None,
    config: DemandInferenceConfig = DemandInferenceConfig(),
) -> pd.DataFrame:
    """Score raw evidence without using future financial or return information.

    signal is a normalized directional observation in [-1, 1].
    reliability can be supplied per row; otherwise source_type defaults are used.
    freshness decays exponentially by each row's half life.
    """
    work = _validate(evidence)
    anchor = pd.Timestamp(as_of_date) if as_of_date is not None else work["as_of_date"].max()
    work["age_days"] = (anchor - work["as_of_date"]).dt.days.clip(lower=0)
    work = work[work["age_days"] <= config.max_evidence_age_days].copy()

    defaults = work["source_type"].map(SOURCE_RELIABILITY).fillna(0.40)
    if "reliability" in work.columns:
        supplied = pd.to_numeric(work["reliability"], errors="coerce")
        work["reliability_used"] = supplied.where(supplied.notna(), defaults).clip(0.0, 1.0)
    else:
        work["reliability_used"] = defaults

    if "half_life_days" in work.columns:
        half_life = pd.to_numeric(work["half_life_days"], errors="coerce").fillna(config.default_half_life_days)
    else:
        half_life = pd.Series(config.default_half_life_days, index=work.index)
    if (half_life <= 0).any():
        raise ValueError("half_life_days must be > 0")
    work["half_life_days_used"] = half_life
    work["freshness"] = [
        freshness_weight(float(age), float(hl))
        for age, hl in zip(work["age_days"], work["half_life_days_used"])
    ]
    work["effective_signal"] = work["signal"] * work["reliability_used"] * work["freshness"]
    work["effective_weight"] = work["reliability_used"] * work["freshness"]
    return work


def deduplicate_evidence(scored: pd.DataFrame) -> pd.DataFrame:
    """Collapse observations that describe the same causal evidence group.

    Multiple articles or comments about one underlying order/capacity event should
    strengthen confidence only modestly instead of being counted as independent demand.
    The group's directional signal is a reliability/freshness weighted mean.
    """
    if scored.empty:
        return scored.copy()

    rows: list[dict[str, object]] = []
    group_cols = ["theme", "dimension", "chain", "evidence_group"]
    for keys, group in scored.groupby(group_cols, dropna=False, sort=False):
        denominator = group["effective_weight"].sum()
        group_signal = 0.0 if denominator <= 0 else float(group["effective_signal"].sum() / denominator)
        strongest = group.loc[group["effective_weight"].idxmax()]
        rows.append(
            {
                "theme": keys[0],
                "dimension": keys[1],
                "chain": keys[2],
                "evidence_group": keys[3],
                "indicator": strongest["indicator"],
                "group_signal": group_signal,
                "group_confidence": float(1.0 - (1.0 - group["effective_weight"].clip(0, 0.95)).prod()),
                "observation_count": int(len(group)),
                "latest_date": group["as_of_date"].max().date().isoformat(),
                "source_types": ", ".join(sorted(set(group["source_type"].astype(str)))),
            }
        )
    return pd.DataFrame(rows)


def infer_demand_state(
    evidence: pd.DataFrame,
    *,
    theme: str | None = None,
    as_of_date: str | pd.Timestamp | None = None,
    config: DemandInferenceConfig = DemandInferenceConfig(),
) -> dict[str, object]:
    work = evidence.copy()
    if theme is not None:
        work = work[work["theme"].astype(str) == str(theme)].copy()
    if work.empty:
        raise ValueError("No evidence available for requested theme")

    scored = score_evidence(work, as_of_date=as_of_date, config=config)
    deduped = deduplicate_evidence(scored)
    if deduped.empty:
        raise ValueError("No evidence remains after freshness filtering")

    dimension_rows: list[dict[str, object]] = []
    weighted_total = 0.0
    total_weight = 0.0
    for dimension, weight in config.dimension_weights.items():
        group = deduped[deduped["dimension"] == dimension]
        if group.empty:
            dimension_rows.append({"dimension": dimension, "score": 50.0, "confidence": 0.0, "groups": 0})
            continue
        confidence_weights = group["group_confidence"].clip(lower=0.05)
        signal = float((group["group_signal"] * confidence_weights).sum() / confidence_weights.sum())
        confidence = float(1.0 - (1.0 - group["group_confidence"].clip(0, 0.95)).prod())
        score = 50.0 + 50.0 * signal
        dimension_rows.append(
            {"dimension": dimension, "score": score, "confidence": confidence * 100.0, "groups": int(len(group))}
        )
        weighted_total += signal * float(weight)
        total_weight += float(weight)

    overall_signal = weighted_total / total_weight if total_weight else 0.0
    overall_score = 50.0 + 50.0 * overall_signal
    chains = deduped.groupby("chain")["group_confidence"].max().sort_values(ascending=False)
    positive_chains = int((deduped.groupby("chain")["group_signal"].mean() > 0.10).sum())
    negative_groups = deduped[deduped["group_signal"] < -0.10].sort_values("group_signal")
    positive_groups = deduped[deduped["group_signal"] > 0.10].sort_values("group_signal", ascending=False)

    confidence = float(min(100.0, 100.0 * (1.0 - (1.0 - deduped["group_confidence"].clip(0, 0.95)).prod())))
    if overall_score >= 70:
        state = "Strong"
    elif overall_score >= 58:
        state = "Improving"
    elif overall_score <= 30:
        state = "Weak"
    elif overall_score <= 42:
        state = "Deteriorating"
    else:
        state = "Mixed"

    return {
        "theme": str(deduped.iloc[0]["theme"]),
        "as_of_date": pd.Timestamp(as_of_date if as_of_date is not None else scored["as_of_date"].max()).date().isoformat(),
        "score": round(overall_score, 2),
        "state": state,
        "confidence": round(confidence, 1),
        "independent_chains": int(chains.size),
        "positive_chains": positive_chains,
        "raw_observations": int(len(scored)),
        "deduplicated_groups": int(len(deduped)),
        "dimensions": pd.DataFrame(dimension_rows),
        "evidence_groups": deduped.sort_values(["group_signal", "group_confidence"], ascending=[False, False]).reset_index(drop=True),
        "positive_evidence": positive_groups.reset_index(drop=True),
        "conflicting_evidence": negative_groups.reset_index(drop=True),
    }
