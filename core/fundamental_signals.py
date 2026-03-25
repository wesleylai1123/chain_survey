from __future__ import annotations

import pandas as pd

from core.data_loader import load_companies, load_monthly_revenue, load_quarterly_financials


def _clip(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _latest_by_ticker(df: pd.DataFrame, period_column: str) -> pd.DataFrame:
    ordered = df.copy()
    ordered[period_column] = ordered[period_column].astype(str)
    ordered = ordered.sort_values(["ticker", period_column])
    return ordered.groupby("ticker", as_index=False).tail(1).reset_index(drop=True)


def build_company_fundamental_signal_table() -> pd.DataFrame:
    companies = load_companies()[["name", "ticker", "sector", "industry"]].copy()
    signals = companies.copy()

    try:
        monthly = _latest_by_ticker(load_monthly_revenue(), "period")
        monthly["monthly_signal"] = (
            monthly["yoy_pct"].fillna(0.0) * 0.006
            + monthly["mom_pct"].fillna(0.0) * 0.002
            + monthly["ytd_yoy_pct"].fillna(0.0) * 0.004
        ).clip(-0.25, 0.25)
        signals = signals.merge(monthly[["ticker", "monthly_signal", "yoy_pct", "mom_pct", "ytd_yoy_pct"]], on="ticker", how="left")
    except FileNotFoundError:
        signals["monthly_signal"] = 0.0
        signals["yoy_pct"] = pd.NA
        signals["mom_pct"] = pd.NA
        signals["ytd_yoy_pct"] = pd.NA

    try:
        quarterly = _latest_by_ticker(load_quarterly_financials(), "period")
        quarterly["gross_margin_pct"] = (quarterly["gross_profit"] / quarterly["revenue"] * 100).fillna(0.0)
        quarterly["operating_margin_pct"] = (quarterly["operating_income"] / quarterly["revenue"] * 100).fillna(0.0)
        quarterly["debt_ratio_pct"] = (quarterly["total_liabilities"] / quarterly["total_assets"] * 100).fillna(0.0)
        quarterly["quarterly_signal"] = (
            (quarterly["gross_margin_pct"] - 20.0) * 0.004
            + (quarterly["operating_margin_pct"] - 10.0) * 0.004
            + (45.0 - quarterly["debt_ratio_pct"]) * 0.003
        ).clip(-0.25, 0.25)
        signals = signals.merge(
            quarterly[
                [
                    "ticker",
                    "quarterly_signal",
                    "gross_margin_pct",
                    "operating_margin_pct",
                    "debt_ratio_pct",
                ]
            ],
            on="ticker",
            how="left",
        )
    except FileNotFoundError:
        signals["quarterly_signal"] = 0.0
        signals["gross_margin_pct"] = pd.NA
        signals["operating_margin_pct"] = pd.NA
        signals["debt_ratio_pct"] = pd.NA

    signals["monthly_signal"] = signals["monthly_signal"].fillna(0.0)
    signals["quarterly_signal"] = signals["quarterly_signal"].fillna(0.0)
    signals["fundamental_signal"] = (signals["monthly_signal"] * 0.55 + signals["quarterly_signal"] * 0.45).round(4)
    signals["positive_multiplier"] = signals["fundamental_signal"].apply(lambda value: round(_clip(1.0 + value, 0.65, 1.4), 4))
    signals["negative_multiplier"] = signals["fundamental_signal"].apply(lambda value: round(_clip(1.0 - value, 0.65, 1.4), 4))
    return signals


def get_company_signal_lookup() -> dict[str, dict[str, float | str | None]]:
    table = build_company_fundamental_signal_table()
    lookup: dict[str, dict[str, float | str | None]] = {}
    for _, row in table.iterrows():
        lookup[str(row["name"])] = {
            "ticker": row["ticker"],
            "fundamental_signal": float(row["fundamental_signal"]),
            "positive_multiplier": float(row["positive_multiplier"]),
            "negative_multiplier": float(row["negative_multiplier"]),
            "monthly_signal": float(row["monthly_signal"]),
            "quarterly_signal": float(row["quarterly_signal"]),
            "yoy_pct": None if pd.isna(row.get("yoy_pct")) else float(row["yoy_pct"]),
            "mom_pct": None if pd.isna(row.get("mom_pct")) else float(row["mom_pct"]),
            "ytd_yoy_pct": None if pd.isna(row.get("ytd_yoy_pct")) else float(row["ytd_yoy_pct"]),
            "gross_margin_pct": None if pd.isna(row.get("gross_margin_pct")) else float(row["gross_margin_pct"]),
            "operating_margin_pct": None if pd.isna(row.get("operating_margin_pct")) else float(row["operating_margin_pct"]),
            "debt_ratio_pct": None if pd.isna(row.get("debt_ratio_pct")) else float(row["debt_ratio_pct"]),
        }
    return lookup
