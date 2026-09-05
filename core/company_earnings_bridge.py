from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from core.data_loader import load_quarterly_financials


@dataclass(frozen=True)
class CompanyBridgeAssumptions:
    """Assumptions used to translate product-level changes into company EPS.

    variable_opex_pct_of_revenue_change models the portion of incremental
    revenue change that flows into operating expenses. A value of 10 means
    10% of revenue delta becomes incremental (or reduced) operating expense.

    effective_tax_rate_pct and diluted_shares can be overridden when better
    analyst estimates are available. Otherwise both are inferred from the
    company baseline quarterly financials.
    """

    variable_opex_pct_of_revenue_change: float = 0.0
    non_operating_income_change: float = 0.0
    effective_tax_rate_pct: float | None = None
    diluted_shares: float | None = None


def get_company_financial_snapshot(company: str, period: str) -> dict:
    financials = load_quarterly_financials()
    rows = financials[(financials["company"] == company) & (financials["period"] == period)]
    if rows.empty:
        raise ValueError(f"No quarterly financial snapshot for {company} / {period}")
    if len(rows) > 1:
        raise ValueError(f"Multiple quarterly financial snapshots for {company} / {period}")
    return rows.iloc[0].to_dict()


def _infer_effective_tax_rate_pct(snapshot: Mapping[str, object]) -> float:
    pre_tax_income = float(snapshot["pre_tax_income"])
    net_income = float(snapshot["net_income"])
    if pre_tax_income <= 0:
        raise ValueError("Cannot infer effective tax rate when baseline pre-tax income is not positive")
    rate = (pre_tax_income - net_income) / pre_tax_income * 100.0
    return max(0.0, min(100.0, rate))


def _infer_diluted_shares(snapshot: Mapping[str, object]) -> float:
    net_income = float(snapshot["net_income"])
    eps = float(snapshot["eps"])
    if eps == 0:
        raise ValueError("Cannot infer diluted shares when baseline EPS is zero")
    shares = net_income / eps
    if shares <= 0:
        raise ValueError("Inferred diluted shares must be positive")
    return shares


def _resolve_bridge_inputs(snapshot: Mapping[str, object], assumptions: CompanyBridgeAssumptions) -> tuple[float, float]:
    tax_rate_pct = (
        assumptions.effective_tax_rate_pct
        if assumptions.effective_tax_rate_pct is not None
        else _infer_effective_tax_rate_pct(snapshot)
    )
    if not 0.0 <= tax_rate_pct <= 100.0:
        raise ValueError("effective_tax_rate_pct must be between 0 and 100")

    diluted_shares = assumptions.diluted_shares or _infer_diluted_shares(snapshot)
    if diluted_shares <= 0:
        raise ValueError("diluted_shares must be positive")
    return tax_rate_pct, diluted_shares


def attribute_product_contributions(
    company: str,
    period: str,
    product_impacts: Iterable[Mapping[str, object]],
    assumptions: CompanyBridgeAssumptions | None = None,
) -> list[dict]:
    """Calculate each product's standalone contribution to company earnings.

    Variable OPEX is allocated to each product using that product's revenue
    delta. Company-level non-operating changes are intentionally excluded from
    product attribution and are surfaced separately by the aggregate bridge.
    """

    assumptions = assumptions or CompanyBridgeAssumptions()
    snapshot = get_company_financial_snapshot(company, period)
    impacts = list(product_impacts)
    if not impacts:
        raise ValueError("At least one product impact is required")

    tax_rate_pct, diluted_shares = _resolve_bridge_inputs(snapshot, assumptions)
    base_eps = float(snapshot["eps"])

    rows: list[dict] = []
    for index, impact in enumerate(impacts):
        if impact.get("company") != company or impact.get("period") != period:
            raise ValueError("All product impacts must match the requested company and period")

        product = str(impact.get("product") or f"product_{index + 1}")
        revenue_change = float(impact["revenue_change"])
        gross_profit_change = float(impact["gross_profit_change"])
        variable_opex_change = revenue_change * assumptions.variable_opex_pct_of_revenue_change / 100.0
        operating_income_change = gross_profit_change - variable_opex_change
        net_income_change = operating_income_change * (1.0 - tax_rate_pct / 100.0)
        eps_change = net_income_change / diluted_shares

        rows.append(
            {
                "company": company,
                "period": period,
                "product": product,
                "revenue_change": revenue_change,
                "gross_profit_change": gross_profit_change,
                "variable_opex_change": variable_opex_change,
                "operating_income_change": operating_income_change,
                "net_income_change": net_income_change,
                "eps_change": eps_change,
                "eps_change_pct_vs_base": (eps_change / base_eps * 100.0) if base_eps != 0 else None,
            }
        )

    total_eps_change = sum(row["eps_change"] for row in rows)
    total_abs_eps_change = sum(abs(row["eps_change"]) for row in rows)
    for row in rows:
        row["eps_contribution_pct"] = (
            row["eps_change"] / total_eps_change * 100.0 if total_eps_change != 0 else None
        )
        row["absolute_eps_contribution_pct"] = (
            abs(row["eps_change"]) / total_abs_eps_change * 100.0 if total_abs_eps_change != 0 else None
        )

    rows.sort(key=lambda row: abs(row["eps_change"]), reverse=True)
    return rows


def bridge_product_impacts_to_company(
    company: str,
    period: str,
    product_impacts: Iterable[Mapping[str, object]],
    assumptions: CompanyBridgeAssumptions | None = None,
) -> dict:
    """Roll product scenario deltas into a company-level P&L and EPS scenario.

    Each product impact must be produced from the same company and period and
    contain ``revenue_change`` and ``gross_profit_change`` fields, matching the
    output of ``simulate_product_scenario``.
    """

    assumptions = assumptions or CompanyBridgeAssumptions()
    snapshot = get_company_financial_snapshot(company, period)
    impacts = list(product_impacts)
    if not impacts:
        raise ValueError("At least one product impact is required")

    for impact in impacts:
        if impact.get("company") != company or impact.get("period") != period:
            raise ValueError("All product impacts must match the requested company and period")

    revenue_change = sum(float(impact["revenue_change"]) for impact in impacts)
    gross_profit_change = sum(float(impact["gross_profit_change"]) for impact in impacts)
    variable_opex_change = revenue_change * assumptions.variable_opex_pct_of_revenue_change / 100.0
    operating_income_change = gross_profit_change - variable_opex_change
    pre_tax_income_change = operating_income_change + assumptions.non_operating_income_change

    tax_rate_pct, diluted_shares = _resolve_bridge_inputs(snapshot, assumptions)
    net_income_change = pre_tax_income_change * (1.0 - tax_rate_pct / 100.0)

    base_revenue = float(snapshot["revenue"])
    base_gross_profit = float(snapshot["gross_profit"])
    base_operating_income = float(snapshot["operating_income"])
    base_pre_tax_income = float(snapshot["pre_tax_income"])
    base_net_income = float(snapshot["net_income"])
    base_eps = float(snapshot["eps"])

    scenario_revenue = base_revenue + revenue_change
    scenario_gross_profit = base_gross_profit + gross_profit_change
    scenario_operating_income = base_operating_income + operating_income_change
    scenario_pre_tax_income = base_pre_tax_income + pre_tax_income_change
    scenario_net_income = base_net_income + net_income_change
    scenario_eps = scenario_net_income / diluted_shares
    product_contributions = attribute_product_contributions(company, period, impacts, assumptions)
    product_net_income_change = sum(row["net_income_change"] for row in product_contributions)
    non_operating_net_income_change = net_income_change - product_net_income_change
    non_operating_eps_change = non_operating_net_income_change / diluted_shares

    return {
        "company": company,
        "period": period,
        "product_count": len(impacts),
        "base_revenue": base_revenue,
        "scenario_revenue": scenario_revenue,
        "revenue_change": revenue_change,
        "base_gross_profit": base_gross_profit,
        "scenario_gross_profit": scenario_gross_profit,
        "gross_profit_change": gross_profit_change,
        "variable_opex_change": variable_opex_change,
        "base_operating_income": base_operating_income,
        "scenario_operating_income": scenario_operating_income,
        "operating_income_change": operating_income_change,
        "non_operating_income_change": assumptions.non_operating_income_change,
        "base_pre_tax_income": base_pre_tax_income,
        "scenario_pre_tax_income": scenario_pre_tax_income,
        "pre_tax_income_change": pre_tax_income_change,
        "effective_tax_rate_pct": tax_rate_pct,
        "base_net_income": base_net_income,
        "scenario_net_income": scenario_net_income,
        "net_income_change": net_income_change,
        "diluted_shares": diluted_shares,
        "base_eps": base_eps,
        "scenario_eps": scenario_eps,
        "eps_change": scenario_eps - base_eps,
        "eps_change_pct": ((scenario_eps / base_eps) - 1.0) * 100.0 if base_eps != 0 else None,
        "product_eps_change": sum(row["eps_change"] for row in product_contributions),
        "non_operating_eps_change": non_operating_eps_change,
        "product_contributions": product_contributions,
    }
