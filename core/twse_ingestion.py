from __future__ import annotations

import io
import ssl
import urllib.request
from pathlib import Path

import pandas as pd

from core.data_loader import load_companies

MONTHLY_REVENUE_URL = "https://mopsfin.twse.com.tw/opendata/t187ap05_L.csv"
QUARTERLY_INCOME_URL = "https://mopsfin.twse.com.tw/opendata/t187ap06_L_ci.csv"
QUARTERLY_BALANCE_URL = "https://mopsfin.twse.com.tw/opendata/t187ap07_L_ci.csv"
SOURCE_NAME = "TWSE/MOPS official open data"


def _ssl_context() -> ssl.SSLContext:
    return ssl._create_unverified_context()


def _read_official_csv(url: str) -> pd.DataFrame:
    raw = urllib.request.urlopen(url, timeout=30, context=_ssl_context()).read()
    return pd.read_csv(io.StringIO(raw.decode("utf-8-sig", errors="ignore")))


def _tw_company_map() -> pd.DataFrame:
    companies = load_companies().copy()
    tw = companies[companies["ticker"].str.endswith(".TW", na=False)].copy()
    tw["company_code"] = tw["ticker"].str.split(".").str[0].astype(str)
    return tw[["name", "ticker", "company_code"]]


def fetch_monthly_revenue() -> pd.DataFrame:
    source = _read_official_csv(MONTHLY_REVENUE_URL)
    tw_companies = _tw_company_map()
    source["公司代號"] = source["公司代號"].astype(str)

    merged = source.merge(tw_companies, left_on="公司代號", right_on="company_code", how="inner")
    out = pd.DataFrame(
        {
            "company": merged["name"],
            "ticker": merged["ticker"],
            "period": merged["資料年月"].astype(str),
            "monthly_revenue": merged["營業收入-當月營收"],
            "previous_month_revenue": merged["營業收入-上月營收"],
            "last_year_monthly_revenue": merged["營業收入-去年當月營收"],
            "mom_pct": merged["營業收入-上月比較增減(%)"],
            "yoy_pct": merged["營業收入-去年同月增減(%)"],
            "ytd_revenue": merged["累計營業收入-當月累計營收"],
            "last_year_ytd_revenue": merged["累計營業收入-去年累計營收"],
            "ytd_yoy_pct": merged["累計營業收入-前期比較增減(%)"],
            "source_date": merged["出表日期"].astype(str),
            "source": SOURCE_NAME,
        }
    )
    return out.sort_values(["ticker", "period"]).reset_index(drop=True)


def fetch_quarterly_financials() -> pd.DataFrame:
    income = _read_official_csv(QUARTERLY_INCOME_URL)
    balance = _read_official_csv(QUARTERLY_BALANCE_URL)
    tw_companies = _tw_company_map()
    income["公司代號"] = income["公司代號"].astype(str)
    balance["公司代號"] = balance["公司代號"].astype(str)

    income = income.merge(tw_companies, left_on="公司代號", right_on="company_code", how="inner")
    balance = balance.merge(tw_companies, left_on="公司代號", right_on="company_code", how="inner")

    income["period"] = income["年度"].astype(str) + "Q" + income["季別"].astype(str)
    balance["period"] = balance["年度"].astype(str) + "Q" + balance["季別"].astype(str)

    merged = income.merge(
        balance[
            [
                "ticker",
                "period",
                "資產總計",
                "負債總計",
                "權益總計",
                "每股參考淨值",
                "出表日期",
            ]
        ],
        on=["ticker", "period"],
        how="left",
        suffixes=("_income", "_balance"),
    )

    out = pd.DataFrame(
        {
            "company": merged["name"],
            "ticker": merged["ticker"],
            "period": merged["period"],
            "revenue": merged["營業收入"],
            "gross_profit": merged["營業毛利（毛損）淨額"],
            "operating_income": merged["營業利益（損失）"],
            "pre_tax_income": merged["稅前淨利（淨損）"],
            "net_income": merged["本期淨利（淨損）"],
            "eps": merged["基本每股盈餘（元）"],
            "total_assets": merged["資產總計"],
            "total_liabilities": merged["負債總計"],
            "total_equity": merged["權益總計"],
            "book_value_per_share": merged["每股參考淨值"],
            "source_date": merged["出表日期_balance"].fillna(merged["出表日期_income"]).astype(str),
            "source": SOURCE_NAME,
        }
    )
    return out.sort_values(["ticker", "period"]).reset_index(drop=True)


def write_canonical_external_tables(data_dir: str | Path | None = None) -> tuple[Path, Path]:
    target_dir = Path(data_dir) if data_dir else Path(__file__).resolve().parents[1] / "data"
    monthly = fetch_monthly_revenue()
    quarterly = fetch_quarterly_financials()

    monthly_path = target_dir / "monthly_revenue.csv"
    quarterly_path = target_dir / "quarterly_financials.csv"

    if monthly_path.exists():
        existing_monthly = pd.read_csv(monthly_path)
        monthly = (
            pd.concat([existing_monthly, monthly], ignore_index=True)
            .drop_duplicates(subset=["ticker", "period"], keep="last")
            .sort_values(["ticker", "period"])
            .reset_index(drop=True)
        )

    if quarterly_path.exists():
        existing_quarterly = pd.read_csv(quarterly_path)
        quarterly = (
            pd.concat([existing_quarterly, quarterly], ignore_index=True)
            .drop_duplicates(subset=["ticker", "period"], keep="last")
            .sort_values(["ticker", "period"])
            .reset_index(drop=True)
        )

    monthly.to_csv(monthly_path, index=False, encoding="utf-8-sig")
    quarterly.to_csv(quarterly_path, index=False, encoding="utf-8-sig")
    return monthly_path, quarterly_path
