from __future__ import annotations

from typing import Iterable

import pandas as pd

from core.data_models import DatasetSchema

SCHEMA_REGISTRY: dict[str, DatasetSchema] = {
    "company_master": DatasetSchema("company_master", ("name", "ticker", "country", "sector", "industry", "description", "key_drivers"), ("name",), "Master list of companies covered by the platform."),
    "product_master": DatasetSchema("product_master", ("name", "category", "application", "description"), ("name",), "Master list of products and platforms."),
    "company_relationships": DatasetSchema("company_relationships", ("source_company", "relation", "target_company", "weight"), ("source_company", "relation", "target_company"), "Directed company-to-company relationship graph."),
    "company_product_relationships": DatasetSchema("company_product_relationships", ("company", "relation", "product", "weight"), ("company", "relation", "product"), "Directed company-to-product relationship graph."),
    "product_relationships": DatasetSchema("product_relationships", ("source_product", "relation", "target_product", "weight"), ("source_product", "relation", "target_product"), "Directed product-to-product dependency graph."),
    "product_supply_chain_mappings": DatasetSchema("product_supply_chain_mappings", ("source_company", "source_product", "direction", "related_company", "relation", "weight", "rationale", "updated_at"), ("source_company", "source_product", "direction", "related_company"), "Analyst-managed product-level upstream/downstream company mappings."),
    "product_market_relationships": DatasetSchema("product_market_relationships", ("product", "relation", "market", "weight"), ("product", "relation", "market"), "Directed product-to-market exposure graph."),
    "product_financials": DatasetSchema("product_financials", ("company", "ticker", "product", "period", "revenue", "currency", "revenue_mix_pct", "gross_margin_pct", "gross_profit", "source_type", "source", "confidence"), ("ticker", "product", "period"), "Product-level revenue and gross-profit bridge with provenance and confidence."),
    "product_operating_metrics": DatasetSchema("product_operating_metrics", ("company", "ticker", "product", "period", "metric", "value", "unit", "source_type", "source", "confidence"), ("ticker", "product", "period", "metric"), "Product-level operating drivers such as ASP, volume, utilization, backlog, capacity and inventory."),
    "financial_field_definitions": DatasetSchema("financial_field_definitions", ("field_name", "display_name", "unit", "frequency", "description"), ("field_name",), "Canonical definition of supported financial attributes."),
    "financial_snapshots": DatasetSchema("financial_snapshots", ("company", "period", "revenue", "gross_margin", "inventory", "capex", "eps"), ("company", "period"), "Company-level financial history used by the desktop app and impact views."),
    "monthly_revenue": DatasetSchema("monthly_revenue", ("company", "ticker", "period", "monthly_revenue", "previous_month_revenue", "last_year_monthly_revenue", "mom_pct", "yoy_pct", "ytd_revenue", "last_year_ytd_revenue", "ytd_yoy_pct", "source_date", "source"), ("ticker", "period"), "Canonical monthly revenue history ingested from official TWSE/MOPS open data."),
    "quarterly_financials": DatasetSchema("quarterly_financials", ("company", "ticker", "period", "revenue", "gross_profit", "operating_income", "pre_tax_income", "net_income", "eps", "total_assets", "total_liabilities", "total_equity", "book_value_per_share", "source_date", "source"), ("ticker", "period"), "Canonical quarterly financial table merged from official income statement and balance sheet datasets."),
    "external_data_sources": DatasetSchema("external_data_sources", ("source_id", "dataset", "provider", "frequency", "format", "status", "notes"), ("source_id",), "Registry of real-world data connectors planned for ingestion."),
    "macro_factors": DatasetSchema("macro_factors", ("factor_id", "display_name", "category", "unit", "description"), ("factor_id",), "Canonical reference data for supported macro factors."),
    "macro_exposures": DatasetSchema("macro_exposures", ("factor_id", "entity_type", "entity_name", "exposure_direction", "weight", "rationale"), ("factor_id", "entity_type", "entity_name"), "Mappings from macro factors to directly exposed entities."),
}


def validate_dataframe(dataset_id: str, df: pd.DataFrame) -> None:
    schema = SCHEMA_REGISTRY[dataset_id]
    missing = [column for column in schema.required_columns if column not in df.columns]
    if missing:
        raise ValueError(f"{dataset_id} missing required columns: {missing}")
    if df.empty:
        return
    duplicates = df.duplicated(list(schema.primary_key), keep=False)
    if duplicates.any():
        raise ValueError(f"{dataset_id} contains duplicate primary keys for columns {schema.primary_key}: {df.loc[duplicates, list(schema.primary_key)].head(5).to_dict(orient='records')}")


def validate_event_templates(templates: Iterable[dict]) -> None:
    seen_ids: set[str] = set()
    for template in templates:
        event_id = template.get("event_id")
        if not event_id:
            raise ValueError("event_templates contains a template without event_id")
        if event_id in seen_ids:
            raise ValueError(f"Duplicate event_id found: {event_id}")
        seen_ids.add(event_id)
        for key in ("name", "description", "severity", "max_layers"):
            if key not in template:
                raise ValueError(f"Event template '{event_id}' missing required field: {key}")
        seed_rules = template.get("seed_rules", [])
        macro_seed_rules = template.get("macro_seed_rules", [])
        if not isinstance(seed_rules, list) or not isinstance(macro_seed_rules, list):
            raise ValueError(f"Event template '{event_id}' seed rules must be lists")
        if not seed_rules and not macro_seed_rules:
            raise ValueError(f"Event template '{event_id}' must define at least one seed rule")
        for idx, rule in enumerate(seed_rules, start=1):
            for rule_key in ("match", "impact_on", "sentiment", "base_score", "sensitivity", "reason"):
                if rule_key not in rule:
                    raise ValueError(f"Event template '{event_id}' seed rule {idx} missing field: {rule_key}")
        for idx, rule in enumerate(macro_seed_rules, start=1):
            for rule_key in ("factor_id", "sentiment", "base_score", "sensitivity", "reason"):
                if rule_key not in rule:
                    raise ValueError(f"Event template '{event_id}' macro seed rule {idx} missing field: {rule_key}")
