"""Verified quarterly filing times; reporting dates are never publication times."""

from __future__ import annotations

from urllib.parse import urlparse

import pandas as pd

REQUIRED = {"stock_id", "report_date", "published_at", "source_url", "document_type", "document_name"}
OFFICIAL_HOSTS = {"mops.twse.com.tw", "mopsfin.twse.com.tw", "doc.twse.com.tw", "twse.com.tw", "www.twse.com.tw"}


def verified_filing_times(observations: pd.DataFrame) -> pd.DataFrame:
    """Accept only explicitly sourced financial-report publication timestamps.

    The timestamp must include an offset, preserving the original timezone. Conflicting
    observations for one company and quarter require manual resolution, not a guess.
    """
    if observations.empty and not len(observations.columns):
        return pd.DataFrame(columns=[*sorted(REQUIRED), "available_date"])
    missing = REQUIRED - set(observations.columns)
    if missing:
        raise ValueError(f"Filing observations missing columns: {sorted(missing)}")
    result = observations.copy()
    if not result["stock_id"].astype(str).str.fullmatch(r"\d{4}").all():
        raise ValueError("Filing stock_id must be a four-digit string")
    result["stock_id"] = result["stock_id"].astype(str)
    report = pd.to_datetime(result["report_date"], errors="coerce")
    if report.isna().any() or not report.dt.is_quarter_end.all():
        raise ValueError("report_date must be a quarter end")
    result["report_date"] = report.dt.strftime("%Y-%m-%d")
    if not result["document_type"].eq("quarterly_financial_report").all():
        raise ValueError("Only quarterly financial report disclosures qualify")
    if not result["document_name"].astype(str).str.fullmatch(r"20\d{4}_\d{4}_AI1\.pdf").all():
        raise ValueError("document_name must identify the IFRSs consolidated report")
    if not result["source_url"].map(lambda url: urlparse(str(url)).scheme == "https" and urlparse(str(url)).hostname in OFFICIAL_HOSTS).all():
        raise ValueError("Each timestamp needs a direct official HTTPS source URL")
    if not result["published_at"].astype(str).str.contains(r"(?:Z|[+-]\d{2}:\d{2})$", regex=True).all():
        raise ValueError("published_at must have a timezone offset")
    published = pd.to_datetime(result["published_at"], utc=True, errors="coerce")
    if published.isna().any() or (published.dt.tz_convert("Asia/Taipei").dt.tz_localize(None) < report).any():
        raise ValueError("Invalid or pre-quarter publication timestamp")
    if result.duplicated(["stock_id", "report_date"]).any():
        raise ValueError("Duplicate company-quarter filing times require manual resolution")
    # Use the following calendar day. Daily market data will select the next trading
    # session, which is conservative even for a disclosure during market hours.
    result["available_date"] = (published.dt.tz_convert("Asia/Taipei").dt.normalize() + pd.Timedelta(days=1)).dt.tz_localize(None)
    return result
