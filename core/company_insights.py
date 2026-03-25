from __future__ import annotations

import pandas as pd

from core.data_loader import (
    load_companies,
    load_company_product_relationships,
    load_product_market_relationships,
    load_product_relationships,
)
from core.impact_engine import list_event_names, simulate_event
from core.product_supply_chain_service import get_chain_context, get_managed_mappings_for_product, load_merged_company_relationships


def _company_dimension() -> pd.DataFrame:
    return load_companies()[["name", "ticker", "country", "sector", "industry"]].copy()


def _product_map() -> pd.DataFrame:
    rel = load_company_product_relationships().copy()
    aggregated = rel.groupby("company", as_index=False).agg(products=("product", lambda values: ", ".join(sorted(set(values)))))
    return aggregated


def get_upstream_partners(company_name: str) -> pd.DataFrame:
    company_rels = load_merged_company_relationships().copy()
    company_dim = _company_dimension()
    products = _product_map()

    upstream = company_rels[(company_rels["target_company"] == company_name) & (company_rels["relation"] == "supplier_of")].copy()
    upstream = upstream.merge(company_dim, left_on="source_company", right_on="name", how="left")
    upstream = upstream.merge(products, left_on="source_company", right_on="company", how="left")
    return upstream[
        ["source_company", "ticker", "country", "sector", "industry", "products", "relation", "weight", "source_dataset", "mapped_products"]
    ].rename(columns={"source_company": "company"}).fillna("-")


def get_downstream_partners(company_name: str) -> pd.DataFrame:
    company_rels = load_merged_company_relationships().copy()
    company_dim = _company_dimension()
    products = _product_map()

    downstream = company_rels[(company_rels["source_company"] == company_name) & (company_rels["relation"] == "customer_of")].copy()
    downstream = downstream.merge(company_dim, left_on="target_company", right_on="name", how="left")
    downstream = downstream.merge(products, left_on="target_company", right_on="company", how="left")
    return downstream[
        ["target_company", "ticker", "country", "sector", "industry", "products", "relation", "weight", "source_dataset", "mapped_products"]
    ].rename(columns={"target_company": "company"}).fillna("-")


def get_company_product_dependency_view(company_name: str) -> pd.DataFrame:
    company_products = load_company_product_relationships().copy()
    product_dependencies = load_product_relationships().copy()
    product_markets = load_product_market_relationships().copy()

    selected_products = company_products[company_products["company"] == company_name][["product"]].drop_duplicates()
    dependency_view = selected_products.merge(product_dependencies, left_on="product", right_on="source_product", how="left")
    dependency_view["target_type"] = "product"
    dependency_view["target"] = dependency_view["target_product"]

    market_view = selected_products.merge(product_markets, on="product", how="left")
    market_view["target_type"] = "market"
    market_view["target"] = market_view["market"]
    market_view["relation"] = market_view["relation"]

    unified = pd.concat(
        [
            dependency_view[["product", "relation", "target_type", "target", "weight"]],
            market_view[["product", "relation", "target_type", "target", "weight"]],
        ],
        ignore_index=True,
    )
    unified["source_dataset"] = "curated"

    producer_map = (
        company_products.groupby("product", as_index=False)
        .agg(related_companies=("company", lambda values: ", ".join(sorted(set(values)))))
        .rename(columns={"product": "target"})
    )
    unified = unified.merge(producer_map, on="target", how="left")
    unified["related_companies"] = unified["related_companies"].fillna("-")

    managed = get_managed_mappings_for_product(company_name)
    if not managed.empty:
        managed_view = managed.rename(columns={"source_product": "product", "related_company": "target"})
        managed_view["target_type"] = "company"
        managed_view["related_companies"] = managed_view["target"]
        managed_view = managed_view[["product", "relation", "target_type", "target", "related_companies", "weight", "source_dataset"]]
        unified = pd.concat([unified, managed_view], ignore_index=True)

    return unified.fillna("-")


def get_product_supply_chain_context(company_name: str) -> pd.DataFrame:
    return get_chain_context(company_name).fillna("-")


def get_company_event_summary(company_name: str) -> pd.DataFrame:
    rows: list[dict] = []
    for event_name in list_event_names():
        result = simulate_event(event_name)
        company_result = result[result["company"] == company_name].copy()
        if company_result.empty:
            rows.append(
                {
                    "event": event_name,
                    "direction": "-",
                    "impact_score": 0.0,
                    "signed_score": 0.0,
                    "max_layer": "-",
                    "fundamental_multiplier": 1.0,
                    "seed_source": "-",
                    "macro_factor": "-",
                    "reason": "-",
                }
            )
            continue

        dominant = company_result.sort_values("impact_score", ascending=False).iloc[0]
        rows.append(
            {
                "event": event_name,
                "direction": dominant["direction"],
                "impact_score": round(company_result["impact_score"].sum(), 4),
                "signed_score": round(company_result["signed_score"].sum(), 4),
                "max_layer": int(company_result["layer"].max()),
                "fundamental_multiplier": round(company_result["fundamental_multiplier"].mean(), 4),
                "seed_source": dominant.get("seed_source", "-"),
                "macro_factor": dominant.get("macro_factor", "-") or "-",
                "reason": dominant["reason"],
            }
        )

    return pd.DataFrame(rows)


def get_supply_chain_impact_view(company_name: str) -> pd.DataFrame:
    upstream = get_upstream_partners(company_name)
    downstream = get_downstream_partners(company_name)

    role_map = {company_name: "self"}
    role_map.update({name: "upstream" for name in upstream["company"].tolist()})
    role_map.update({name: "downstream" for name in downstream["company"].tolist()})

    rows: list[dict] = []
    for event_name in list_event_names():
        result = simulate_event(event_name)
        subset = result[result["company"].isin(role_map.keys())].copy()
        for _, row in subset.iterrows():
            rows.append(
                {
                    "event": event_name,
                    "role": role_map[row["company"]],
                    "company": row["company"],
                    "seed_source": row.get("seed_source", "edge_rule"),
                    "macro_factor": row.get("macro_factor", "-") or "-",
                    "direction": row["direction"],
                    "layer": row["layer"],
                    "impact_score": row["impact_score"],
                    "sector": row["sector"],
                    "industry": row["industry"],
                    "reason": row["reason"],
                }
            )

    if not rows:
        return pd.DataFrame(columns=["event", "role", "company", "seed_source", "macro_factor", "direction", "layer", "impact_score", "sector", "industry", "reason"])

    out = pd.DataFrame(rows)
    return out.sort_values(["event", "role", "impact_score"], ascending=[True, True, False]).reset_index(drop=True)
