from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from core.filing_availability import verified_filing_times


INCOME_ALIASES: Mapping[str, Sequence[str]] = {
    "revenue": ("Revenue", "OperatingRevenue", "OperatingRevenueNet"),
    "gross_profit": ("GrossProfit",),
    "operating_income": ("OperatingIncome", "OperatingIncomeLoss"),
    "pre_tax_income": ("IncomeBeforeIncomeTax", "NetIncomeBeforeTax", "ProfitBeforeTax"),
    "net_income": ("IncomeAfterTaxes", "NetIncome"),
    "eps": ("EPS",),
    "cost_of_goods_sold": ("CostOfGoodsSold",),
    "operating_expenses": ("OperatingExpenses",),
    "non_operating_income_expense": ("TotalNonoperatingIncomeAndExpense",),
    "income_tax_expense": ("TAX",),
}
BALANCE_ALIASES: Mapping[str, Sequence[str]] = {
    "total_assets": ("TotalAssets",),
    "total_liabilities": ("TotalLiabilities",),
    "total_equity": ("TotalEquity", "Equity"),
    "inventory": ("Inventories", "Inventory"),
    "cash": ("CashAndCashEquivalents", "CashAndCashEquivalentsCurrent"),
    "accounts_receivable": ("AccountsReceivableNet", "AccountsReceivable"),
    "accounts_payable": ("AccountsPayable", "AccountsPayableTrade"),
    "property_plant_equipment": ("PropertyPlantAndEquipment", "PropertyPlantAndEquipmentNet"),
}
CASHFLOW_ALIASES: Mapping[str, Sequence[str]] = {
    "operating_cash_flow": ("CashFlowsFromOperatingActivities",),
    "capex": ("PropertyAndPlantAndEquipment", "PaymentsToAcquirePropertyPlantAndEquipment"),
    "depreciation": ("Depreciation",),
    "amortization": ("AmortizationExpense",),
    "interest_expense": ("InterestExpense",),
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


def _deaccumulate_cashflow(cash: pd.DataFrame) -> pd.DataFrame:
    """Convert IFRS YTD cash-flow statement values to standalone-quarter values.

    Q1 is already standalone. Q2/Q3/Q4 require the immediately preceding YTD
    observation in the same fiscal year; missing predecessors remain NaN rather
    than silently treating a cumulative number as a quarterly flow.
    """
    if cash.empty:
        return cash
    result=cash.copy().sort_values(["stock_id","report_date"]).reset_index(drop=True)
    result["report_date"]=pd.to_datetime(result["report_date"])
    result["cashflow_basis"]="DEACCUMULATED_FROM_YTD"
    for column in ("operating_cash_flow","capex","depreciation","amortization","interest_expense"):
        if column not in result:
            continue
        result[f"{column}_ytd"]=pd.to_numeric(result[column],errors="coerce")
        quarterly=pd.Series(np.nan,index=result.index,dtype=float)
        for _,idx in result.groupby("stock_id",sort=False).groups.items():
            loc=list(idx)
            previous_by_year: dict[int, tuple[int,float]]={}
            for i in loc:
                date=pd.Timestamp(result.at[i,"report_date"])
                raw=pd.to_numeric(pd.Series([result.at[i,f"{column}_ytd"]]),errors="coerce").iloc[0]
                if pd.isna(raw):
                    continue
                if date.quarter==1:
                    quarterly.at[i]=float(raw)
                else:
                    prev=previous_by_year.get(date.year)
                    if prev is not None and prev[0]==date.quarter-1:
                        quarterly.at[i]=float(raw)-float(prev[1])
                previous_by_year[date.year]=(date.quarter,float(raw))
        result[column]=quarterly
    return result


def _rolling_ttm(grouped: pd.core.groupby.generic.SeriesGroupBy, periods: int=4) -> pd.Series:
    return grouped.transform(lambda s: pd.to_numeric(s,errors="coerce").rolling(periods,min_periods=periods).sum())


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
        return pd.DataFrame(columns=[
            "stock_id","report_date","monthly_revenue_3m","monthly_revenue_3m_yoy",
            "monthly_revenue_available_date","monthly_revenue_availability_method",
        ])
    work = monthly.copy()
    work["revenue"] = pd.to_numeric(work["revenue"], errors="coerce")
    year = pd.to_numeric(work.get("revenue_year"), errors="coerce")
    month = pd.to_numeric(work.get("revenue_month"), errors="coerce")
    if year.isna().all() or month.isna().all():
        source_date = pd.to_datetime(work["date"], errors="coerce") - pd.offsets.MonthBegin(1)
        year, month = source_date.dt.year, source_date.dt.month
    revenue_period_start=pd.to_datetime(dict(year=year,month=month,day=1),errors="coerce")
    work["report_date"] = revenue_period_start + pd.offsets.QuarterEnd(0)
    statutory=(revenue_period_start + pd.offsets.MonthBegin(1)).map(lambda d: pd.Timestamp(d.year,d.month,10) if pd.notna(d) else pd.NaT)
    create=pd.to_datetime(work.get("create_time",pd.Series(pd.NaT,index=work.index)),errors="coerce")
    work["monthly_revenue_row_available_date"]=create.combine_first(statutory)
    work["monthly_revenue_row_method"]=np.where(create.notna(),"finmind_create_time","statutory_next_month_10d_proxy")

    grouped=work.groupby(["stock_id","report_date"],as_index=False)
    q=grouped["revenue"].sum(min_count=1).rename(columns={"revenue":"monthly_revenue_3m"})
    avail=grouped["monthly_revenue_row_available_date"].max().rename(columns={"monthly_revenue_row_available_date":"monthly_revenue_available_date"})
    q=q.merge(avail,on=["stock_id","report_date"],how="left")
    methods=work.sort_values("monthly_revenue_row_available_date").groupby(["stock_id","report_date"],as_index=False).tail(1)[
        ["stock_id","report_date","monthly_revenue_row_method"]
    ].rename(columns={"monthly_revenue_row_method":"monthly_revenue_availability_method"})
    q=q.merge(methods,on=["stock_id","report_date"],how="left").sort_values(["stock_id","report_date"])
    q["monthly_revenue_3m_yoy"] = q.groupby("stock_id")["monthly_revenue_3m"].pct_change(4, fill_method=None)
    return q


def _attach_market_targets(frame: pd.DataFrame, prices: pd.DataFrame, valuation: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["price_at_available"] = np.nan
    result["return_basis"] = pd.NA
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
                result.at[idx, "return_basis"] = str(p.iloc[start_pos].get("price_basis","RAW_CLOSE_UNADJUSTED"))
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


def _attach_feature_return_targets(
    frame: pd.DataFrame,
    prices: pd.DataFrame,
    *,
    availability_column: str,
    prefix: str,
) -> pd.DataFrame:
    result=frame.copy()
    result[f"{prefix}_price_at_available"]=np.nan
    result[f"{prefix}_return_basis"]=pd.NA
    horizons={f"{prefix}_future_3m_return":3,f"{prefix}_future_6m_return":6,f"{prefix}_future_12m_return":12}
    for column in horizons:
        result[column]=np.nan
    if prices.empty or availability_column not in result:
        return result
    pwork=prices.copy()
    pwork["date"]=pd.to_datetime(pwork["date"],errors="coerce")
    pwork["close"]=pd.to_numeric(pwork["close"],errors="coerce")
    pwork=pwork.dropna(subset=["date","close"])
    for stock_id,indices in result.groupby("stock_id",sort=False).groups.items():
        p=pwork[pwork["stock_id"].astype(str)==str(stock_id)].sort_values("date")
        if p.empty:
            continue
        dates=p["date"].to_numpy(dtype="datetime64[ns]")
        closes=p["close"].to_numpy(dtype=float)
        for idx in indices:
            available=pd.to_datetime(result.at[idx,availability_column],errors="coerce")
            if pd.isna(available):
                continue
            start_pos=int(np.searchsorted(dates,np.datetime64(available),side="left"))
            if start_pos>=len(p):
                continue
            start_price=closes[start_pos]
            result.at[idx,f"{prefix}_price_at_available"]=start_price
            result.at[idx,f"{prefix}_return_basis"]=str(p.iloc[start_pos].get("price_basis","RAW_CLOSE_UNADJUSTED"))
            for column,months in horizons.items():
                target_date=pd.Timestamp(available)+pd.DateOffset(months=months)
                end_pos=int(np.searchsorted(dates,np.datetime64(target_date),side="left"))
                if end_pos<len(p) and start_price!=0:
                    result.at[idx,column]=closes[end_pos]/start_price-1.0
    return result


def _assign_cycle(frame: pd.DataFrame, *, min_companies: int=20) -> pd.DataFrame:
    result = frame.copy()
    signal_column = "monthly_revenue_3m_yoy" if "monthly_revenue_3m_yoy" in result else "revenue_yoy"
    company_count=int(result["stock_id"].astype(str).nunique()) if "stock_id" in result else 0
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
    if company_count < min_companies:
        market["cycle"]="Unknown"
        market["cycle_basis"]=f"DISABLED_INTERNAL_UNIVERSE_TOO_SMALL_N{company_count}"
    else:
        market["cycle_basis"]=f"INTERNAL_CROSS_SECTION_MEDIAN_N{company_count}"
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
    filing_observations: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build a quarterly, point-in-time-aware factor validation panel.

    FinMind statement dates are reporting-period dates, not exact publication timestamps.
    To avoid obvious look-ahead, targets start after a conservative availability-date proxy:
    +60 calendar days for Q1-Q3 and +90 days for Q4 by default. The proxy is retained
    explicitly in the output and should be replaced by exact filing timestamps later.
    """
    income = _pivot_types(financial_statements, INCOME_ALIASES)
    balance = _pivot_types(balance_sheets, BALANCE_ALIASES)
    cash = _deaccumulate_cashflow(_pivot_types(cashflows, CASHFLOW_ALIASES))
    panel = income.merge(balance, on=["stock_id", "report_date"], how="outer")
    panel = panel.merge(cash, on=["stock_id", "report_date"], how="outer")
    panel = panel.merge(_quarterly_month_revenue(monthly_revenue), on=["stock_id", "report_date"], how="left")
    panel = panel.sort_values(["stock_id", "report_date"]).reset_index(drop=True)

    for column in ("revenue", "gross_profit", "operating_income", "pre_tax_income", "net_income", "eps", "cost_of_goods_sold", "operating_expenses", "non_operating_income_expense", "income_tax_expense", "inventory", "accounts_receivable", "accounts_payable", "total_equity", "operating_cash_flow", "capex", "depreciation", "amortization", "interest_expense", "property_plant_equipment"):
        _add_yoy(panel, column)
    if {"gross_profit", "revenue"}.issubset(panel.columns):
        panel["gross_margin"] = _safe_divide(panel["gross_profit"], panel["revenue"])
        panel["gross_margin_qoq"] = panel.groupby("stock_id")["gross_margin"].diff()
        panel["gross_margin_yoy_delta"] = panel.groupby("stock_id")["gross_margin"].diff(4)
    if {"operating_income", "revenue"}.issubset(panel.columns):
        panel["operating_margin"] = _safe_divide(panel["operating_income"], panel["revenue"])
    if {"operating_expenses","revenue"}.issubset(panel.columns):
        panel["opex_to_revenue"]=_safe_divide(panel["operating_expenses"].abs(),panel["revenue"])
    if {"non_operating_income_expense","pre_tax_income"}.issubset(panel.columns):
        panel["non_operating_share_of_pretax"]=_safe_divide(panel["non_operating_income_expense"],panel["pre_tax_income"])
    if {"income_tax_expense","pre_tax_income"}.issubset(panel.columns):
        panel["effective_tax_rate"]=_safe_divide(panel["income_tax_expense"],panel["pre_tax_income"])
    if {"depreciation","revenue"}.issubset(panel.columns):
        panel["depreciation_to_revenue"]=_safe_divide(panel["depreciation"].abs(),panel["revenue"])
    if {"depreciation","amortization"}.issubset(panel.columns):
        panel["depreciation_amortization"]=pd.to_numeric(panel["depreciation"],errors="coerce").fillna(0)+pd.to_numeric(panel["amortization"],errors="coerce").fillna(0)
    if {"capex","depreciation"}.issubset(panel.columns):
        panel["capex_to_depreciation"]=_safe_divide(panel["capex"].abs(),panel["depreciation"].abs())
    if {"property_plant_equipment","revenue"}.issubset(panel.columns):
        panel["asset_turnover_quarterly"]=_safe_divide(panel["revenue"],panel["property_plant_equipment"])
    if {"interest_expense","operating_income"}.issubset(panel.columns):
        panel["interest_coverage_proxy"]=_safe_divide(panel["operating_income"],panel["interest_expense"].abs())
    if {"net_income", "revenue"}.issubset(panel.columns):
        panel["net_margin"] = _safe_divide(panel["net_income"], panel["revenue"])
    if {"total_liabilities", "total_equity"}.issubset(panel.columns):
        panel["debt_to_equity"] = _safe_divide(panel["total_liabilities"], panel["total_equity"])
    if {"net_income", "total_equity"}.issubset(panel.columns):
        panel["roe_proxy"] = _safe_divide(panel["net_income"], panel["total_equity"])
        panel["net_income_ttm"] = _rolling_ttm(panel.groupby("stock_id",sort=False)["net_income"])
        prior_equity = panel.groupby("stock_id",sort=False)["total_equity"].shift(4)
        panel["average_equity_ttm"] = (pd.to_numeric(panel["total_equity"],errors="coerce") + pd.to_numeric(prior_equity,errors="coerce")) / 2.0
        panel["roe_ttm"] = _safe_divide(panel["net_income_ttm"], panel["average_equity_ttm"])
        panel["roe_basis"] = "TTM_NET_INCOME_OVER_AVG_BEGIN_END_EQUITY"
    if {"operating_cash_flow", "revenue"}.issubset(panel.columns):
        panel["ocf_margin"] = _safe_divide(panel["operating_cash_flow"], panel["revenue"])
    if {"capex", "revenue"}.issubset(panel.columns):
        panel["capex_to_revenue"] = _safe_divide(panel["capex"].abs(), panel["revenue"])
    if {"operating_cash_flow","capex","revenue"}.issubset(panel.columns):
        panel["free_cash_flow"] = pd.to_numeric(panel["operating_cash_flow"],errors="coerce") - pd.to_numeric(panel["capex"],errors="coerce").abs()
        panel["fcf_margin"] = _safe_divide(panel["free_cash_flow"], panel["revenue"])
    if {"operating_cash_flow","net_income"}.issubset(panel.columns):
        panel["cfo_to_net_income"] = _safe_divide(panel["operating_cash_flow"], panel["net_income"])
    if {"net_income","operating_cash_flow","total_assets"}.issubset(panel.columns):
        prior_assets=panel.groupby("stock_id",sort=False)["total_assets"].shift(1)
        average_assets=(pd.to_numeric(panel["total_assets"],errors="coerce")+pd.to_numeric(prior_assets,errors="coerce"))/2.0
        panel["accrual_ratio"]=_safe_divide(pd.to_numeric(panel["net_income"],errors="coerce")-pd.to_numeric(panel["operating_cash_flow"],errors="coerce"), average_assets)
    if {"inventory","revenue_yoy","inventory_yoy"}.issubset(panel.columns):
        panel["inventory_revenue_growth_gap"]=pd.to_numeric(panel["inventory_yoy"],errors="coerce")-pd.to_numeric(panel["revenue_yoy"],errors="coerce")
    if {"accounts_receivable_yoy","revenue_yoy"}.issubset(panel.columns):
        panel["ar_revenue_growth_gap"]=pd.to_numeric(panel["accounts_receivable_yoy"],errors="coerce")-pd.to_numeric(panel["revenue_yoy"],errors="coerce")
    if {"accounts_receivable","revenue"}.issubset(panel.columns):
        panel["dso_days"]=_safe_divide(panel["accounts_receivable"],panel["revenue"])*90.0
    if {"inventory","cost_of_goods_sold"}.issubset(panel.columns):
        panel["dio_days"]=_safe_divide(panel["inventory"],pd.to_numeric(panel["cost_of_goods_sold"],errors="coerce").abs())*90.0
    if {"accounts_payable","cost_of_goods_sold"}.issubset(panel.columns):
        panel["dpo_days"]=_safe_divide(panel["accounts_payable"],pd.to_numeric(panel["cost_of_goods_sold"],errors="coerce").abs())*90.0
    if {"dso_days","dio_days","dpo_days"}.issubset(panel.columns):
        panel["cash_conversion_cycle_days"]=panel["dso_days"]+panel["dio_days"]-panel["dpo_days"]
    panel["earnings_growth_basis"]="NET_INCOME_YOY_PREFERRED__REPORTED_EPS_YOY_REFERENCE"

    panel["available_date"] = panel["report_date"].apply(lambda value: _availability_date(pd.Timestamp(value), availability_policy))
    panel["availability_method"] = panel["report_date"].dt.quarter.map(lambda q: "report_date+90d_proxy" if q == 4 else "report_date+60d_proxy")
    panel["filing_published_at"] = pd.NA
    panel["filing_source_url"] = pd.NA
    panel["filing_document_name"] = pd.NA
    if filing_observations is not None and not filing_observations.empty:
        filings = verified_filing_times(filing_observations)
        filings["report_date"] = pd.to_datetime(filings["report_date"])
        panel = panel.merge(
            filings[["stock_id", "report_date", "published_at", "source_url", "document_name", "available_date"]],
            on=["stock_id", "report_date"], how="left", suffixes=("", "_filing"), validate="many_to_one",
        )
        exact = panel["available_date_filing"].notna()
        panel.loc[exact, "available_date"] = panel.loc[exact, "available_date_filing"]
        panel.loc[exact, "availability_method"] = "official_filing_timestamp_next_day"
        panel.loc[exact, "filing_published_at"] = panel.loc[exact, "published_at"]
        panel.loc[exact, "filing_source_url"] = panel.loc[exact, "source_url"]
        panel.loc[exact, "filing_document_name"] = panel.loc[exact, "document_name"]
        panel = panel.drop(columns=["available_date_filing", "published_at", "source_url", "document_name"])

    company_map = companies.copy()
    company_map["stock_id"] = company_map["ticker"].astype(str).str.extract(r"(\d{4})", expand=False)
    company_map = company_map[["stock_id", "name", "ticker", "sector", "industry"]].dropna(subset=["stock_id"]).drop_duplicates("stock_id")
    panel = panel.merge(company_map, on="stock_id", how="left")
    panel = _attach_market_targets(panel, prices, valuation if valuation is not None else pd.DataFrame())
    panel = _attach_feature_return_targets(panel, prices, availability_column="monthly_revenue_available_date", prefix="monthly_revenue")
    panel = _assign_cycle(panel)
    panel["fundamental_source"] = "FinMind: TaiwanStockFinancialStatements/BalanceSheet/CashFlows/MonthRevenue"
    panel["market_source"] = "FinMind: price series supplied to builder + TaiwanStockPER"
    panel["report_date"] = pd.to_datetime(panel["report_date"]).dt.date.astype(str)
    panel["available_date"] = pd.to_datetime(panel["available_date"]).dt.date.astype(str)
    if "monthly_revenue_available_date" in panel:
        panel["monthly_revenue_available_date"]=pd.to_datetime(panel["monthly_revenue_available_date"],errors="coerce").dt.date.astype("string")

    preferred = [
        "name", "ticker", "stock_id", "sector", "industry", "report_date", "available_date", "availability_method", "filing_published_at", "filing_source_url", "filing_document_name", "cycle",
        "revenue", "revenue_yoy", "monthly_revenue_3m", "monthly_revenue_3m_yoy", "monthly_revenue_available_date", "monthly_revenue_availability_method", "gross_margin", "gross_margin_qoq", "gross_margin_yoy_delta",
        "operating_margin", "opex_to_revenue", "net_margin", "pre_tax_income", "non_operating_income_expense", "non_operating_share_of_pretax", "income_tax_expense", "effective_tax_rate",
        "eps", "eps_yoy", "earnings_growth_basis", "net_income", "net_income_yoy",
        "inventory", "inventory_yoy", "inventory_revenue_growth_gap", "accounts_receivable", "accounts_receivable_yoy", "ar_revenue_growth_gap", "accounts_payable", "accounts_payable_yoy",
        "dso_days", "dio_days", "dpo_days", "cash_conversion_cycle_days",
        "roe_proxy", "roe_ttm", "roe_basis", "debt_to_equity", "operating_cash_flow", "operating_cash_flow_ytd", "cashflow_basis", "ocf_margin",
        "capex", "capex_ytd", "capex_to_revenue", "depreciation", "depreciation_ytd", "amortization", "amortization_ytd", "depreciation_amortization", "depreciation_to_revenue", "capex_to_depreciation",
        "interest_expense", "interest_expense_ytd", "interest_coverage_proxy", "free_cash_flow", "fcf_margin", "cfo_to_net_income", "accrual_ratio",
        "property_plant_equipment", "property_plant_equipment_yoy", "asset_turnover_quarterly",
        "pe", "pb", "dividend_yield", "price_at_available", "return_basis", *TARGET_COLUMNS,
        "monthly_revenue_price_at_available", "monthly_revenue_return_basis", "monthly_revenue_future_3m_return", "monthly_revenue_future_6m_return", "monthly_revenue_future_12m_return",
        "universe_revenue_yoy", "universe_revenue_yoy_delta", "cycle_basis",
        "fundamental_source", "market_source",
    ]
    ordered = [column for column in preferred if column in panel.columns]
    extras = [column for column in panel.columns if column not in ordered]
    return panel[ordered + extras].sort_values(["ticker", "report_date"]).reset_index(drop=True)
