from __future__ import annotations

import math
from datetime import datetime, timezone

import pandas as pd

from core import data_loader
from core.guidance_service import parse_period

CATEGORY_DIRECT_FIELD = {"revenue_growth": "revenue", "gross_margin": "gross_margin"}
FLAT_THRESHOLD_PCT = 1.0
MATCH_SCORE = {"match": 1.0, "partial": 0.5, "miss": 0.0}
CLAIM_OUTCOME_COLUMNS = ("claim_id", "actual_value", "match_result", "evaluated_at", "note")


def _financials_for_ticker(ticker: str) -> pd.DataFrame:
    df = data_loader.load_quarterly_financials()
    subset = df[df["ticker"] == ticker].copy()
    if subset.empty:
        return subset
    subset["gross_margin"] = (subset["gross_profit"] / subset["revenue"] * 100).round(2)
    subset = subset.sort_values("period", key=lambda periods: periods.map(lambda p: parse_period(p))).reset_index(drop=True)
    return subset


def _period_index(period: str) -> int:
    """Map a ROC period like '114Q3' onto a monotonic quarter index."""
    year, quarter = parse_period(period)
    return year * 4 + quarter


def _qoq_change(subset: pd.DataFrame, target_period: str, field: str) -> float | None:
    matches = subset.index[subset["period"] == target_period]
    if len(matches) == 0:
        return None
    pos = matches[0]
    if pos == 0:
        return None

    # The row before the target is only a valid QoQ baseline if it is the
    # immediately preceding quarter. quarterly_financials.csv is sparse while
    # history is backfilled, so a gap (e.g. 113Q4 -> 114Q3) must surface as
    # unverifiable rather than be silently treated as one quarter's change.
    current_period = subset.loc[pos, "period"]
    previous_period = subset.loc[pos - 1, "period"]
    if _period_index(current_period) - _period_index(previous_period) != 1:
        return None

    current = subset.loc[pos, field]
    previous = subset.loc[pos - 1, field]
    # gross_margin is computed as gross_profit / revenue, so a zero-revenue
    # quarter yields NaN. Comparing against NaN would score a confident "miss"
    # (0.0 in the credibility score) on what is really missing data.
    if not math.isfinite(current) or not math.isfinite(previous):
        return None

    if field == "revenue":
        if previous == 0:
            return None
        return round((current - previous) / abs(previous) * 100, 2)
    return round(current - previous, 2)


def _direction_matches(actual_change: float, direction: str) -> bool:
    if direction == "flat":
        return abs(actual_change) <= FLAT_THRESHOLD_PCT
    if direction == "up":
        return actual_change > FLAT_THRESHOLD_PCT
    if direction == "down":
        return actual_change < -FLAT_THRESHOLD_PCT
    raise ValueError(f"Invalid direction '{direction}'")


def evaluate_claim(claim: pd.Series) -> tuple[str, float | None, str]:
    ticker = str(claim["ticker"])
    category = str(claim["category"])
    target_period = str(claim["target_period"])
    direction = str(claim["direction"])
    subset = _financials_for_ticker(ticker)

    if category in CATEGORY_DIRECT_FIELD:
        field = CATEGORY_DIRECT_FIELD[category]
        change = _qoq_change(subset, target_period, field)
        if change is None:
            return "unverifiable", None, f"no resolvable QoQ baseline for {ticker} {target_period}"

        direction_ok = _direction_matches(change, direction)
        quant_low, quant_high = claim.get("quant_low"), claim.get("quant_high")
        has_range = pd.notna(quant_low) and pd.notna(quant_high)
        if not direction_ok:
            return "miss", change, "actual direction did not match claimed direction"
        if has_range and not (float(quant_low) <= change <= float(quant_high)):
            return "partial", change, "direction correct, actual value outside claimed range"
        return "match", change, "direction and range consistent" if has_range else "direction consistent"

    # The design spec defines two criteria for the product-line proxy:
    # (1) cross-quarter consistency of the same product_or_segment, and
    # (2) correlation with the company-level revenue/margin trend.
    # Only (2) is implemented in this iteration. Criterion (1) is a known,
    # deliberately deferred follow-up, not an oversight - see the
    # "Product-Line Signal: Proxy Methodology" section of
    # docs/superpowers/specs/2026-08-08-guidance-analysis-design.md.
    if category == "product_line":
        revenue_change = _qoq_change(subset, target_period, "revenue")
        margin_change = _qoq_change(subset, target_period, "gross_margin")
        if revenue_change is None or margin_change is None:
            return "unverifiable", None, "insufficient QoQ baseline for product-line proxy"

        agreements = sum(
            1 for change in (revenue_change, margin_change) if _direction_matches(change, direction)
        )
        if agreements == 2:
            return "match", revenue_change, "revenue and margin trend both corroborate claim"
        if agreements == 1:
            return "partial", revenue_change, "only one of revenue/margin trend corroborates claim"
        return "miss", revenue_change, "neither revenue nor margin trend corroborates claim"

    return "unverifiable", None, f"category '{category}' has no defined actual-data mapping"


def run_verification() -> pd.DataFrame:
    claims = data_loader.load_guidance_claims()
    confirmed = claims[claims["status"] == "confirmed"] if not claims.empty else claims

    if confirmed.empty:
        outcomes = pd.DataFrame(columns=list(CLAIM_OUTCOME_COLUMNS))
    else:
        evaluated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        records = []
        for _, claim in confirmed.iterrows():
            match_result, actual_value, note = evaluate_claim(claim)
            records.append(
                {
                    "claim_id": claim["claim_id"],
                    "actual_value": actual_value,
                    "match_result": match_result,
                    "evaluated_at": evaluated_at,
                    "note": note,
                }
            )
        outcomes = pd.DataFrame(records)

    outcomes.to_csv(data_loader.DATA_DIR / "claim_outcomes.csv", index=False)
    data_loader.clear_data_caches()
    return outcomes


def compute_credibility_score(ticker: str, trailing_quarters: int = 8) -> float | None:
    claims = data_loader.load_guidance_claims()
    if claims.empty:
        return None
    confirmed = claims[(claims["ticker"] == ticker) & (claims["status"] == "confirmed")]
    if confirmed.empty:
        return None

    distinct_quarters = sorted({str(q) for q in confirmed["source_quarter"]}, key=parse_period)
    window = set(distinct_quarters[-trailing_quarters:])
    windowed_claims = confirmed[confirmed["source_quarter"].isin(window)]
    if windowed_claims.empty:
        return None

    outcomes = data_loader.load_claim_outcomes()
    if outcomes.empty:
        return None
    merged = windowed_claims.merge(outcomes, on="claim_id", how="inner")
    resolved = merged[merged["match_result"].isin(MATCH_SCORE)]
    if resolved.empty:
        return None
    return round(float(resolved["match_result"].map(MATCH_SCORE).mean()), 3)
