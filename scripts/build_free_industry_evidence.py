from __future__ import annotations

from pathlib import Path
import calendar

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MONTHLY_REVENUE = ROOT / "data" / "monthly_revenue.csv"
FREE_SNAPSHOT = ROOT / "data" / "free_industry_evidence_snapshot.csv"
OUTPUT = ROOT / "data" / "evidence_observations_free.csv"

ABF_COMPANIES = {"欣興", "南電", "景碩"}


def _roc_yyyymm_to_period_end(value: object) -> pd.Timestamp:
    text = str(value).replace(".0", "").strip()
    year = 1911 + int(text[:3])
    month = int(text[3:5])
    return pd.Timestamp(year=year, month=month, day=calendar.monthrange(year, month)[1], tz="Asia/Taipei")


def _roc_yyyymmdd_to_timestamp(value: object) -> pd.Timestamp:
    text = str(value).replace(".0", "").strip()
    year = 1911 + int(text[:3])
    month = int(text[3:5])
    day = int(text[5:7])
    return pd.Timestamp(year=year, month=month, day=day, tz="Asia/Taipei")


def _signal(change_pct: float, transform_type: str) -> float:
    value = float(change_pct)
    if transform_type == "pct_yoy":
        return max(-1.0, min(1.0, value / 100.0))
    if transform_type == "pct_change_ref20":
        return max(-1.0, min(1.0, value / 20.0))
    if transform_type == "pct_change_ref5":
        return max(-1.0, min(1.0, value / 5.0))
    raise ValueError(f"Unknown transform_type: {transform_type}")


def build_mops_company_evidence(monthly_revenue: pd.DataFrame) -> pd.DataFrame:
    frame = monthly_revenue[monthly_revenue["company"].isin(ABF_COMPANIES)].copy()
    rows = []
    for _, row in frame.iterrows():
        period = _roc_yyyymm_to_period_end(row["period"])
        published = _roc_yyyymmdd_to_timestamp(row["source_date"])
        yoy = float(row["yoy_pct"])
        rows.append({
            "evidence_id": f"mops_{row['ticker']}_{row['period']}",
            "theme": "AI Infrastructure",
            "dimension": "financial_confirmation",
            "chain": "ABF",
            "evidence_group": f"mops_monthly_revenue_{row['ticker']}_{row['period']}",
            "indicator": f"{row['company']} monthly revenue YoY",
            "period_date": period,
            "published_at": published,
            "as_of_date": published,
            "raw_value": float(row["monthly_revenue"]),
            "raw_unit": "TWD thousand",
            "change_pct": yoy,
            "signal": _signal(yoy, "pct_yoy"),
            "source_type": "government_statistic",
            "reliability": 0.98,
            "half_life_days": 90,
            "source": row["source"],
            "transform": "clip(yoy_pct / 100, -1, 1)",
            "transform_version": "mops_yoy_v1",
            "provenance": "REAL_POINT_IN_TIME_FREE",
        })
    return pd.DataFrame(rows)


def build_snapshot_evidence(snapshot: pd.DataFrame) -> pd.DataFrame:
    frame = snapshot.copy()
    frame["period_date"] = pd.to_datetime(frame["period_date"], utc=True)
    frame["published_at"] = pd.to_datetime(frame["published_at"], utc=True)
    frame["as_of_date"] = frame["published_at"]
    frame["change_pct"] = pd.to_numeric(frame["change_pct"], errors="raise")
    frame["signal"] = [
        _signal(v, t) for v, t in zip(frame["change_pct"], frame["transform_type"])
    ]
    frame["transform"] = frame["transform_type"]
    frame["transform_version"] = "free_sources_v1"
    frame["provenance"] = "REAL_POINT_IN_TIME_FREE"
    keep = [
        "evidence_id","theme","dimension","chain","evidence_group","indicator",
        "period_date","published_at","as_of_date","raw_value","raw_unit","change_pct",
        "signal","source_type","reliability","half_life_days","source",
        "transform","transform_version","provenance"
    ]
    return frame[keep]


def build_free_evidence() -> pd.DataFrame:
    mops = pd.read_csv(MONTHLY_REVENUE)
    snapshot = pd.read_csv(FREE_SNAPSHOT)
    combined = pd.concat(
        [build_mops_company_evidence(mops), build_snapshot_evidence(snapshot)],
        ignore_index=True,
        sort=False,
    )
    combined["collected_at"] = pd.Timestamp.now(tz="UTC")
    return combined.sort_values(["published_at","evidence_id"]).reset_index(drop=True)


def main() -> None:
    output = build_free_evidence()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(OUTPUT, index=False)
    print(
        "FREE_INDUSTRY_EVIDENCE_OK "
        f"rows={len(output)} chains={sorted(output['chain'].unique())}"
    )


if __name__ == "__main__":
    main()
