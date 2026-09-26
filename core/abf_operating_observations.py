"""Source-backed ABF product and downside observations."""

from __future__ import annotations

from urllib.parse import urlparse

import pandas as pd

REQUIRED = {
    "data_id", "stock_id", "period_end", "observation_scope", "value", "unit",
    "published_at", "published_date", "publication_precision", "source_url",
    "source_page", "source_excerpt",
}
PUBLICATION_PRECISIONS = {"EXACT_SECOND", "DATE_ONLY"}


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
    for column in ("observation_scope", "unit", "publication_precision", "source_page", "source_excerpt"):
        if result[column].isna().any() or result[column].astype(str).str.strip().eq("").any():
            raise ValueError(f"Observation requires {column}")
    if not result["publication_precision"].isin(PUBLICATION_PRECISIONS).all():
        raise ValueError("Unsupported publication precision")

    exact=result["publication_precision"].eq("EXACT_SECOND")
    dated=result["publication_precision"].eq("DATE_ONLY")
    exact_text=result["published_at"].fillna("").astype(str)
    if exact.any() and not exact_text[exact].str.contains(r"(?:Z|[+-]\d{2}:\d{2})$",regex=True).all():
        raise ValueError("Exact publication time needs timezone offset")
    published=pd.to_datetime(result["published_at"],utc=True,errors="coerce")
    if exact.any() and published[exact].isna().any():
        raise ValueError("Invalid exact publication time")
    published_dates=pd.to_datetime(result["published_date"],errors="coerce")
    if dated.any() and published_dates[dated].isna().any():
        raise ValueError("Date-only publication requires published_date")
    if not result["source_url"].map(lambda u: urlparse(str(u)).scheme == "https" and bool(urlparse(str(u)).hostname)).all():
        raise ValueError("Observation requires a direct HTTPS source URL")
    if result.duplicated(["data_id", "stock_id", "period_end", "observation_scope", "source_url"]).any():
        raise ValueError("Duplicate source observation")
    available=pd.Series(pd.NaT,index=result.index,dtype="datetime64[ns]")
    available.loc[exact]=(published[exact].dt.tz_convert("Asia/Taipei").dt.tz_localize(None).dt.normalize()+pd.Timedelta(days=1))
    available.loc[dated]=published_dates[dated].dt.normalize()+pd.Timedelta(days=1)
    result["available_date"]=available.dt.date.astype(str)
    return result
