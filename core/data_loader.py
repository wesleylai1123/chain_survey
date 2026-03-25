from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import pandas as pd

from core.data_validation import validate_dataframe, validate_event_templates

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"


def _read_csv(preferred_name: str, fallback_name: str | None = None) -> pd.DataFrame:
    preferred_path = DATA_DIR / preferred_name
    if preferred_path.exists():
        return pd.read_csv(preferred_path)
    if fallback_name:
        return pd.read_csv(DATA_DIR / fallback_name)
    raise FileNotFoundError(preferred_path)


def _read_json(preferred_name: str, fallback_name: str | None = None) -> list[dict]:
    preferred_path = DATA_DIR / preferred_name
    if preferred_path.exists():
        with open(preferred_path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    if fallback_name:
        with open(DATA_DIR / fallback_name, "r", encoding="utf-8") as handle:
            return json.load(handle)
    raise FileNotFoundError(preferred_path)


def _empty_dataframe(columns: tuple[str, ...]) -> pd.DataFrame:
    return pd.DataFrame(columns=list(columns))


@lru_cache(maxsize=1)
def load_companies() -> pd.DataFrame:
    df = _read_csv("company_master.csv", "companies.csv")
    validate_dataframe("company_master", df)
    return df


@lru_cache(maxsize=1)
def load_products() -> pd.DataFrame:
    df = _read_csv("product_master.csv", "products.csv")
    validate_dataframe("product_master", df)
    return df


@lru_cache(maxsize=1)
def load_company_relationships() -> pd.DataFrame:
    df = _read_csv("company_relationships.csv")
    validate_dataframe("company_relationships", df)
    return df


@lru_cache(maxsize=1)
def load_company_product_relationships() -> pd.DataFrame:
    df = _read_csv("company_product_relationships.csv")
    validate_dataframe("company_product_relationships", df)
    return df


@lru_cache(maxsize=1)
def load_product_relationships() -> pd.DataFrame:
    df = _read_csv("product_relationships.csv")
    validate_dataframe("product_relationships", df)
    return df


@lru_cache(maxsize=1)
def load_product_supply_chain_mappings() -> pd.DataFrame:
    path = DATA_DIR / "product_supply_chain_mappings.csv"
    if not path.exists():
        return _empty_dataframe(
            (
                "source_company",
                "source_product",
                "direction",
                "related_company",
                "relation",
                "weight",
                "rationale",
                "updated_at",
            )
        )
    df = pd.read_csv(path)
    validate_dataframe("product_supply_chain_mappings", df)
    return df


@lru_cache(maxsize=1)
def load_product_market_relationships() -> pd.DataFrame:
    df = _read_csv("product_market_relationships.csv")
    validate_dataframe("product_market_relationships", df)
    return df


@lru_cache(maxsize=1)
def load_edges() -> pd.DataFrame:
    company_edges = load_company_relationships().rename(
        columns={"source_company": "source", "target_company": "target"}
    )
    company_edges["source_type"] = "company"
    company_edges["target_type"] = "company"
    company_edges["source_dataset"] = "curated"

    company_product_edges = load_company_product_relationships().rename(
        columns={"company": "source", "product": "target"}
    )
    company_product_edges["source_type"] = "company"
    company_product_edges["target_type"] = "product"
    company_product_edges["source_dataset"] = "curated"

    product_edges = load_product_relationships().rename(
        columns={"source_product": "source", "target_product": "target"}
    )
    product_edges["source_type"] = "product"
    product_edges["target_type"] = "product"
    product_edges["source_dataset"] = "curated"

    product_market_edges = load_product_market_relationships().rename(
        columns={"product": "source", "market": "target"}
    )
    product_market_edges["source_type"] = "product"
    product_market_edges["target_type"] = "market"
    product_market_edges["source_dataset"] = "curated"

    managed_mappings = load_product_supply_chain_mappings().copy()
    managed_edges = _empty_dataframe(("source", "source_type", "relation", "target", "target_type", "weight", "source_dataset"))
    if not managed_mappings.empty:
        upstream = managed_mappings[managed_mappings["direction"] == "upstream"].copy()
        upstream["source"] = upstream["related_company"]
        upstream["source_type"] = "company"
        upstream["target"] = upstream["source_product"]
        upstream["target_type"] = "product"
        upstream["source_dataset"] = "analyst_managed"

        downstream = managed_mappings[managed_mappings["direction"] == "downstream"].copy()
        downstream["source"] = downstream["source_product"]
        downstream["source_type"] = "product"
        downstream["target"] = downstream["related_company"]
        downstream["target_type"] = "company"
        downstream["source_dataset"] = "analyst_managed"

        managed_edges = pd.concat(
            [
                upstream[["source", "source_type", "relation", "target", "target_type", "weight", "source_dataset"]],
                downstream[["source", "source_type", "relation", "target", "target_type", "weight", "source_dataset"]],
            ],
            ignore_index=True,
        )

    edge_frames = [
        company_edges[["source", "source_type", "relation", "target", "target_type", "weight", "source_dataset"]],
        company_product_edges[["source", "source_type", "relation", "target", "target_type", "weight", "source_dataset"]],
        product_edges[["source", "source_type", "relation", "target", "target_type", "weight", "source_dataset"]],
        product_market_edges[["source", "source_type", "relation", "target", "target_type", "weight", "source_dataset"]],
    ]
    if not managed_edges.empty:
        edge_frames.append(managed_edges[["source", "source_type", "relation", "target", "target_type", "weight", "source_dataset"]])

    return pd.concat(edge_frames, ignore_index=True)


@lru_cache(maxsize=1)
def load_financials() -> pd.DataFrame:
    quarterly_path = DATA_DIR / "quarterly_financials.csv"
    if quarterly_path.exists():
        quarterly = pd.read_csv(quarterly_path)
        validate_dataframe("quarterly_financials", quarterly)
        df = quarterly.copy()
        df["gross_margin"] = (df["gross_profit"] / df["revenue"] * 100).round(2)
        df["inventory"] = pd.NA
        df["capex"] = pd.NA
        return df[["company", "period", "revenue", "gross_margin", "inventory", "capex", "eps"]]

    df = pd.read_csv(DATA_DIR / "financials.csv")
    validate_dataframe("financial_snapshots", df)
    return df


@lru_cache(maxsize=1)
def load_monthly_revenue() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "monthly_revenue.csv")
    validate_dataframe("monthly_revenue", df)
    return df


@lru_cache(maxsize=1)
def load_quarterly_financials() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "quarterly_financials.csv")
    validate_dataframe("quarterly_financials", df)
    return df


@lru_cache(maxsize=1)
def load_financial_field_definitions() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "financial_field_definitions.csv")
    validate_dataframe("financial_field_definitions", df)
    return df


@lru_cache(maxsize=1)
def load_external_data_sources() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "external_data_sources.csv")
    validate_dataframe("external_data_sources", df)
    return df


@lru_cache(maxsize=1)
def load_macro_factors() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "macro_factors.csv")
    validate_dataframe("macro_factors", df)
    return df


@lru_cache(maxsize=1)
def load_macro_exposures() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "macro_exposures.csv")
    validate_dataframe("macro_exposures", df)
    return df


@lru_cache(maxsize=1)
def load_event_templates() -> list[dict]:
    templates = _read_json("event_templates.json", "events.json")
    validate_event_templates(templates)
    return templates


@lru_cache(maxsize=1)
def load_events() -> list[dict]:
    return load_event_templates()


def clear_data_caches() -> None:
    load_companies.cache_clear()
    load_products.cache_clear()
    load_company_relationships.cache_clear()
    load_company_product_relationships.cache_clear()
    load_product_relationships.cache_clear()
    load_product_supply_chain_mappings.cache_clear()
    load_product_market_relationships.cache_clear()
    load_edges.cache_clear()
    load_financials.cache_clear()
    load_monthly_revenue.cache_clear()
    load_quarterly_financials.cache_clear()
    load_financial_field_definitions.cache_clear()
    load_external_data_sources.cache_clear()
    load_macro_factors.cache_clear()
    load_macro_exposures.cache_clear()
    load_event_templates.cache_clear()
    load_events.cache_clear()
