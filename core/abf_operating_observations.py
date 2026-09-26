"""Source-backed ABF product and downside observations."""

from __future__ import annotations

from urllib.parse import urlparse

import pandas as pd

REQUIRED = {"data_id", "stock_id", "period_end", "value", "unit", "published_at", "source_url", "source_excerpt"}


def verified_operating_observations(frame: pd.DataFrame, allowed_ids: set[str]) -> pd.DataFrame:
    if frame.empty and not len(frame.columns):
        return pd.DataFrame(columns=sorted(REQUIRED))
    missing = REQUIRED - set(frame.columns)
    if missing:
        raise ValueError(f"Operating observations missing columns: {sorted(missing)}")
    result = frame.copy()
    if result.empty:
        return result
    if not result["data_id"].isin(allowed_ids).all():
        raise ValueError("Unknown ABF data_id")
    if not result["stock_id"].astype(str).str.fullmatch(r"\d{4}").all():
        raise ValueError("ABF observation requires a four-digit stock_id")
    result["stock_id"] = result["stock_id"].astype(str)
    if pd.to_datetime(result["period_end"], errors="coerce").isna().any():
        raise ValueError("Invalid observation period")
    if pd.to_numeric(result["value"], errors="coerce").isna().any():
        raise ValueError("Observation value must be numeric")
    for column in ("unit", "source_excerpt"):
        if result[column].isna().any() or result[column].astype(str).str.strip().eq("").any():
            raise ValueError(f"Observation requires {column}")
    if not result["published_at"].astype(str).str.contains(r"(?:Z|[+-]\d{2}:\d{2})$", regex=True).all():
        raise ValueError("Publication time needs timezone offset")
    published = pd.to_datetime(result["published_at"], utc=True, errors="coerce")
    if published.isna().any():
        raise ValueError("Invalid publication time")
    if not result["source_url"].map(lambda u: urlparse(str(u)).scheme == "https" and bool(urlparse(str(u)).hostname)).all():
        raise ValueError("Observation requires a direct HTTPS source URL")
    if result.duplicated(["data_id", "stock_id", "period_end", "source_url"]).any():
        raise ValueError("Duplicate source observation")
    result["available_date"] = (published.dt.tz_convert("Asia/Taipei").dt.normalize() + pd.Timedelta(days=1)).dt.date.astype(str)
    return result
