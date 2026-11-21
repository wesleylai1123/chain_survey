from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from core.data_loader import load_product_financials, load_product_operating_metrics


@dataclass(frozen=True)
class ProductScenario:
    volume_change_pct: float = 0.0
    asp_change_pct: float = 0.0
    gross_margin_change_ppt: float = 0.0


def _find_metric(metrics: pd.DataFrame, metric: str) -> float | None:
    rows = metrics[metrics["metric"] == metric]
    if rows.empty:
        return None
    return float(rows.iloc[-1]["value"])


def get_product_snapshot(company: str, product: str, period: str) -> dict:
    financials = load_product_financials()
    rows = financials[(financials["company"] == company) & (financials["product"] == product) & (financials["period"] == period)]
    if rows.empty:
        raise ValueError(f"No product financial snapshot for {company} / {product} / {period}")
    return rows.iloc[0].to_dict()


def simulate_product_scenario(company: str, product: str, period: str, scenario: ProductScenario) -> dict:
    base = get_product_snapshot(company, product, period)
    base_revenue = float(base["revenue"])
    base_margin = float(base["gross_margin_pct"])

    revenue_multiplier = (1 + scenario.volume_change_pct / 100.0) * (1 + scenario.asp_change_pct / 100.0)
    new_revenue = base_revenue * revenue_multiplier
    new_margin = base_margin + scenario.gross_margin_change_ppt
    new_gross_profit = new_revenue * new_margin / 100.0
    base_gross_profit = float(base["gross_profit"])

    return {
        "company": company,
        "product": product,
        "period": period,
        "base_revenue": base_revenue,
        "scenario_revenue": new_revenue,
        "revenue_change": new_revenue - base_revenue,
        "base_gross_margin_pct": base_margin,
        "scenario_gross_margin_pct": new_margin,
        "base_gross_profit": base_gross_profit,
        "scenario_gross_profit": new_gross_profit,
        "gross_profit_change": new_gross_profit - base_gross_profit,
    }


def infer_revenue_from_operating_metrics(company: str, product: str, period: str) -> dict:
    metrics = load_product_operating_metrics()
    subset = metrics[(metrics["company"] == company) & (metrics["product"] == product) & (metrics["period"] == period)]
    volume = _find_metric(subset, "volume")
    asp = _find_metric(subset, "asp")
    if volume is None or asp is None:
        raise ValueError(f"Both volume and asp are required for {company} / {product} / {period}")
    return {
        "company": company,
        "product": product,
        "period": period,
        "volume": volume,
        "asp": asp,
        "implied_revenue": volume * asp,
    }
