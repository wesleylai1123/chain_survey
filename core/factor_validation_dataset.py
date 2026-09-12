from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np
import pandas as pd


INCOME_ALIASES: Mapping[str, Sequence[str]] = {
    "revenue": ("Revenue", "OperatingRevenue", "OperatingRevenueNet"),
    "gross_profit": ("GrossProfit",),
    "operating_income": ("OperatingIncome", "OperatingIncomeLoss"),
    "pre_tax_income": ("IncomeBeforeIncomeTax", "NetIncomeBeforeTax", "ProfitBeforeTax"),
    "net_income": ("IncomeAfterTaxes", "NetIncome"),
    "eps": ("EPS",),
    "cost_of_goods_sold": ("CostOfGoodsSold",),
}
BALANCE_ALIASES: Mapping[str, Sequence[str]] = {
    "total_assets": ("TotalAssets",),
    "total_liabilities": ("TotalLiabilities",),
    "total_equity": ("TotalEquity", "Equity"),
    "inventory": ("Inventories", "Inventory"),
    "cash": ("CashAndCashEquivalents", "CashAndCashEquivalentsCurrent"),
    "accounts_receivable": ("AccountsReceivableNet", "AccountsReceivable"),
}
CASHFLOW_ALIASES: Mapping[str, Sequence[str]] = {
    "operating_cash_flow": ("CashFlowsFromOperatingActivities",),
    "capex": ("PropertyAndPlantAndEquipment", "PaymentsToAcquirePropertyPlantAndEquipment"),
}
TARGET_COLUMNS = ("future_3m_return", "future_6m_return", "future_12m_return")


@dataclass(frozen=True)
class AvailabilityPolicy:
    regular_quarter_days: int = 60
    annual_quarter_days: int = 90


def _pivot_types(frame: pd.DataFrame, aliases: Mapping[str, Sequence[str]]) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["stock_id", "report_date", *aliases.keys()])
    work = frame.copy()
    work["date"] = pd.to_datetime(work["date"], errors="coerce")
    work["value"] = pd.to_numeric(work["value"], errors="coerce")
    work = work.dropna(subset=["date", "stock_id", "type", "value"])
    rows: list[pd.DataFrame] = []
    for output, candidates in aliases.items():
        picked = work[work["type"].isin(candidates)].copy()
        if picked.empty:
            continue
        order = {name: index for index, name in enumerate(candidates)}
        picked["_priority"] = picked["type"].map(order).fillna(len(order))
        picked = picked.sort_values(["stock_id", "date", "_priority"]).drop_duplicates(["stock_id", "date"])
        rows.append(picked[["stock_id", "date", "value"]].rename(columns={"date": "report_date", "value": output}))
    if not rows:
        return pd.DataFrame(columns=["stock_id", "report_date", *aliases.keys()])
    result = rows[0]
    for piece in rows[1:]:
        result = result.merge(piece, on=["stock_id", "report_date"], how="outer")
    return result


def _safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    result = pd.to_numeric(numerator, errors="coerce").div(pd.to_numeric(denominator, errors="coerce"))
    return result.replace([np.inf, -np.inf], np.nan)


def _add_yoy(frame: pd.DataFrame, column: str) -> None:
    if column not in frame:
        return
    frame[f"{column}_yoy"] = frame.groupby("stock_id", sort=False)[column].pct_change(4, fill_method=None)


def _availability_date(report_date: pd.Timestamp, policy: AvailabilityPolicy) -> pd.Timestamp:
    days = policy.annual_quarter_days if report_date.quarter == 4 else policy.regular_quarter_days
    return report_date + pd.Timedelta(days=days)


def _quarterly_month_revenue(monthly: pd.DataFrame) -> pd.DataFrame:
    if monthly.empty:
        return pd.DataFrame(columns=["stock_id", "report_date", "monthly_revenue_3m", "monthly_revenue_3m_yoy"])
    work = monthly.copy()
    work["revenue"] = pd.to_numeric(work["revenue"], errors="coerce")
    year = pd.to_numeric(work.get("revenue_year"), errors="coerce")
    month = pd.to_numeric(work.get("revenue_month"), errors="coerce")
    if year.isna().all() or month.isna().all():
        source_date = pd.to_datetime(work["date"], errors="coerce") - pd.offsets.MonthBegin(1)
        year, month = source_date.dt.year, source_date.dt.month
    work["report_date"] = pd.to_datetime(dict(year=year, month=month, day=1), errors="coerce") + pd.offsets.QuarterEnd(0)
    q = work.groupby(["stock_id", "report_date"], as_index=False)["revenue"].sum(min_count=1)
    q = q.rename(columns={"revenue": "monthly_revenue_3m"}).sort_values(["stock_id", "report_date"])
    q["monthly_revenue_3m_yoy"] = q.groupby("stock_id")["monthly_revenue_3m"].pct_change(4, fill_method=None)
    return q


def _attach_market_targets(frame: pd.DataFrame, prices: pd.DataFrame, valuation: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["price_at_available"] = np.nan
    for target in TARGET_COLUMNS:
        result[target] = np.nan
    result["pe"] = np.nan
    result["pb"] = np.nan
    result["dividend_yield"] = np.nan

    price_work = prices.copy()
    if not price_work.empty:
        price_work["date"] = pd.to_datetime(price_work["date"], errors="coerce")
        price_work["close"] = pd.to_numeric(price_work["close"], errors="coerce")
        price_work = price_work.dropna(subset=["date", "close"])
    val_work = valuation.copy()
    if not val_work.empty:
        val_work["date"] = pd.to_datetime(val_work["date"], errors="coerce")

    horizons = {"future_3m_return": 3, "future_6m_return": 6, "future_12m_return": 12}
    for stock_id, indices in result.groupby("stock_id", sort=False).groups.items():
        p = price_work[price_work["stock_id"].astype(str) == str(stock_id)].sort_values("date")
        if not p.empty:
            dates = p["date"].to_numpy(dtype="datetime64[ns]")
            closes = p["close"].to_numpy(dtype=float)
            for idx in indices:
                available = pd.Timestamp(result.at[idx, "available_date"])
                start_pos = int(np.searchsorted(dates, np.datetime64(available), side="left"))
                if start_pos >= len(p):
                    continue
                start_price = closes[start_pos]
                result.at[idx, "price_at_available"] = start_price
                for column, months in horizons.items():
                    target_date = available + pd.DateOffset(months=months)
                    end_pos = int(np.searchsorted(dates, np.datetime64(target_date), side="left"))
                    if end_pos < len(p) and start_price not in (0, np.nan):
                        result.at[idx, column] = closes[end_pos] / start_price - 1.0
        v = val_work[val_work["stock_id"].astype(str) == str(stock_id)].sort_values("date")
        if not v.empty:
            dates = v["date"].to_numpy(dtype="datetime64[ns]")
            for idx in indices:
                available = pd.Timestamp(result.at[idx, "available_date"])
                pos = int(np.searchsorted(dates, np.datetime64(available), side="left"))
                if pos >= len(v):
                    continue
                row = v.iloc[pos]
                for source, dest in (("PER", "pe"), ("PBR", "pb"), ("dividend_yield", "dividend_yield")):
                    if source in row.index:
                        result.at[idx, dest] = pd.to_numeric(row[source], errors="coerce")
    return result


def _assign_cycle(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    signal_column = "monthly_revenue_3m_yoy" if "monthly_revenue_3m_yoy" in result else "revenue_yoy"
    market = result.groupby("report_date", as_index=False)[signal_column].median().rename(columns={signal_column: "universe_revenue_yoy"})
    market = market.sort_values("report_date")
    market["universe_revenue_yoy_delta"] = market["universe_revenue_yoy"].diff()
    def classify(row: pd.Series) -> str:
        level, delta = row["universe_revenue_yoy"], row["universe_revenue_yoy_delta"]
        if pd.isna(level) or pd.isna(delta):
            return "Unknown"
        if level >= 0 and delta >= 0:
            return "Expansion"
        if level >= 0 and delta < 0:
            return "Slowdown"
        if level < 0 and delta < 0:
            return "Contraction"
        return "Recovery"
    market["cycle"] = market.apply(classify, axis=1)
    return result.merge(market, on="report_date", how="left")


def build_factor_validation_dataset(
    companies: pd.DataFrame,
    financial_statements: pd.DataFrame,
    balance_sheets: pd.DataFrame,
    cashflows: pd.DataFrame,
    monthly_revenue: pd.DataFrame,
    prices: pd.DataFrame,
    valuation: pd.DataFrame | None = None,
    *,
    availability_policy: AvailabilityPolicy = AvailabilityPolicy(),
) -> pd.DataFrame:
    """Build a quarterly, point-in-time-aware factor validation panel.

    FinMind statement dates are reporting-period dates, not exact publication timestamps.
    To avoid obvious look-ahead, targets start after a conservative availability-date proxy:
    +60 calendar days for Q1-Q3 and +90 days for Q4 by default. The proxy is retained
    explicitly in the output and should be replaced by exact filing timestamps later.
    """
    income = _pivot_types(financial_statements, INCOME_ALIASES)
    balance = _pivot_types(balance_sheets, BALANCE_ALIASES)
    cash = _pivot_types(cashflows, CASHFLOW_ALIASES)
    panel = income.merge(balance, on=["stock_id", "report_date"], how="outer")
    panel = panel.merge(cash, on=["stock_id", "report_date"], how="outer")
    panel = panel.merge(_quarterly_month_revenue(monthly_revenue), on=["stock_id", "report_date"], how="left")
    panel = panel.sort_values(["stock_id", "report_date"]).reset_index(drop=True)

    for column in ("revenue", "gross_profit", "operating_income", "net_income", "eps", "inventory", "total_equity", "operating_cash_flow", "capex"):
        _add_yoy(panel, column)
    if {"gross_profit", "revenue"}.issubset(panel.columns):
        panel["gross_margin"] = _safe_divide(panel["gross_profit"], panel["revenue"])
        panel["gross_margin_qoq"] = panel.groupby("stock_id")["gross_margin"].diff()
        panel["gross_margin_yoy_delta"] = panel.groupby("stock_id")["gross_margin"].diff(4)
    if {"operating_income", "revenue"}.issubset(panel.columns):
        panel["operating_margin"] = _safe_divide(panel["operating_income"], panel["revenue"])
    if {"net_income", "revenue"}.issubset(panel.columns):
        panel["net_margin"] = _safe_divide(panel["net_income"], panel["revenue"])
    if {"total_liabilities", "total_equity"}.issubset(panel.columns):
        panel["debt_to_equity"] = _safe_divide(panel["total_liabilities"], panel["total_equity"])
    if {"net_income", "total_equity"}.issubset(panel.columns):
        panel["roe_proxy"] = _safe_divide(panel["net_income"], panel["total_equity"])
    if {"operating_cash_flow", "revenue"}.issubset(panel.columns):
        panel["ocf_margin"] = _safe_divide(panel["operating_cash_flow"], panel["revenue"])
    if {"capex", "revenue"}.issubset(panel.columns):
        panel["capex_to_revenue"] = _safe_divide(panel["capex"].abs(), panel["revenue"])

    panel["available_date"] = panel["report_date"].apply(lambda value: _availability_date(pd.Timestamp(value), availability_policy))
    panel["availability_method"] = panel["report_date"].dt.quarter.map(lambda q: "report_date+90d_proxy" if q == 4 else "report_date+60d_proxy")

    company_map = companies.copy()
    company_map["stock_id"] = company_map["ticker"].astype(str).str.extract(r"(\d{4})", expand=False)
    company_map = company_map[["stock_id", "name", "ticker", "sector", "industry"]].dropna(subset=["stock_id"]).drop_duplicates("stock_id")
    panel = panel.merge(company_map, on="stock_id", how="left")
    panel = _attach_market_targets(panel, prices, valuation if valuation is not None else pd.DataFrame())
    panel = _assign_cycle(panel)
    panel["fundamental_source"] = "FinMind: TaiwanStockFinancialStatements/BalanceSheet/CashFlows/MonthRevenue"
    panel["market_source"] = "FinMind: TaiwanStockPriceAdj + TaiwanStockPER"
    panel["report_date"] = pd.to_datetime(panel["report_date"]).dt.date.astype(str)
    panel["available_date"] = pd.to_datetime(panel["available_date"]).dt.date.astype(str)

    preferred = [
        "name", "ticker", "stock_id", "sector", "industry", "report_date", "available_date", "availability_method", "cycle",
        "revenue", "revenue_yoy", "monthly_revenue_3m", "monthly_revenue_3m_yoy", "gross_margin", "gross_margin_qoq", "gross_margin_yoy_delta",
        "operating_margin", "net_margin", "eps", "eps_yoy", "inventory", "inventory_yoy", "roe_proxy", "debt_to_equity", "ocf_margin", "capex_to_revenue",
        "pe", "pb", "dividend_yield", "price_at_available", *TARGET_COLUMNS, "universe_revenue_yoy", "universe_revenue_yoy_delta",
        "fundamental_source", "market_source",
    ]
    ordered = [column for column in preferred if column in panel.columns]
    extras = [column for column in panel.columns if column not in ordered]
    return panel[ordered + extras].sort_values(["ticker", "report_date"]).reset_index(drop=True)
