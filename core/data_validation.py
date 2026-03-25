from __future__ import annotations

from typing import Iterable

import pandas as pd

from core.data_models import DatasetSchema

SCHEMA_REGISTRY: dict[str, DatasetSchema] = {
    "company_master": DatasetSchema(
        dataset_id="company_master",
        required_columns=("name", "ticker", "country", "sector", "industry", "description", "key_drivers"),
        primary_key=("name",),
        description="Master list of companies covered by the platform.",
    ),
    "product_master": DatasetSchema(
        dataset_id="product_master",
        required_columns=("name", "category", "application", "description"),
        primary_key=("name",),
        description="Master list of products and platforms.",
    ),
    "company_relationships": DatasetSchema(
        dataset_id="company_relationships",
        required_columns=("source_company", "relation", "target_company", "weight"),
        primary_key=("source_company", "relation", "target_company"),
        description="Directed company-to-company relationship graph.",
    ),
    "company_product_relationships": DatasetSchema(
        dataset_id="company_product_relationships",
        required_columns=("company", "relation", "product", "weight"),
        primary_key=("company", "relation", "product"),
        description="Directed company-to-product relationship graph.",
    ),
    "product_relationships": DatasetSchema(
        dataset_id="product_relationships",
        required_columns=("source_product", "relation", "target_product", "weight"),
        primary_key=("source_product", "relation", "target_product"),
        description="Directed product-to-product dependency graph.",
    ),
    "product_supply_chain_mappings": DatasetSchema(
        dataset_id="product_supply_chain_mappings",
        required_columns=(
            "source_company",
            "source_product",
            "direction",
            "related_company",
            "relation",
            "weight",
            "rationale",
            "updated_at",
        ),
        primary_key=("source_company", "source_product", "direction", "related_company"),
        description="Analyst-managed product-level upstream/downstream company mappings.",
    ),
    "product_market_relationships": DatasetSchema(
        dataset_id="product_market_relationships",
        required_columns=("product", "relation", "market", "weight"),
        primary_key=("product", "relation", "market"),
        description="Directed product-to-market exposure graph.",
    ),
    "financial_field_definitions": DatasetSchema(
        dataset_id="financial_field_definitions",
        required_columns=("field_name", "display_name", "unit", "frequency", "description"),
        primary_key=("field_name",),
        description="Canonical definition of supported financial attributes.",
    ),
    "financial_snapshots": DatasetSchema(
        dataset_id="financial_snapshots",
        required_columns=("company", "period", "revenue", "gross_margin", "inventory", "capex", "eps"),
        primary_key=("company", "period"),
        description="Company-level financial history used by the desktop app and impact views.",
    ),
    "monthly_revenue": DatasetSchema(
        dataset_id="monthly_revenue",
        required_columns=(
            "company",
            "ticker",
            "period",
            "monthly_revenue",
            "previous_month_revenue",
            "last_year_monthly_revenue",
            "mom_pct",
            "yoy_pct",
            "ytd_revenue",
            "last_year_ytd_revenue",
            "ytd_yoy_pct",
            "source_date",
            "source",
        ),
        primary_key=("ticker", "period"),
        description="Canonical monthly revenue history ingested from official TWSE/MOPS open data.",
    ),
    "quarterly_financials": DatasetSchema(
        dataset_id="quarterly_financials",
        required_columns=(
            "company",
            "ticker",
            "period",
            "revenue",
            "gross_profit",
            "operating_income",
            "pre_tax_income",
            "net_income",
            "eps",
            "total_assets",
            "total_liabilities",
            "total_equity",
            "book_value_per_share",
            "source_date",
            "source",
        ),
        primary_key=("ticker", "period"),
        description="Canonical quarterly financial table merged from official income statement and balance sheet datasets.",
    ),
    "external_data_sources": DatasetSchema(
        dataset_id="external_data_sources",
        required_columns=("source_id", "dataset", "provider", "frequency", "format", "status", "notes"),
        primary_key=("source_id",),
        description="Registry of real-world data connectors planned for ingestion.",
    ),
    "macro_factors": DatasetSchema(
        dataset_id="macro_factors",
        required_columns=("factor_id", "display_name", "category", "unit", "description"),
        primary_key=("factor_id",),
        description="Canonical reference data for supported macro factors.",
    ),
    "macro_exposures": DatasetSchema(
        dataset_id="macro_exposures",
        required_columns=("factor_id", "entity_type", "entity_name", "exposure_direction", "weight", "rationale"),
        primary_key=("factor_id", "entity_type", "entity_name"),
        description="Mappings from macro factors to directly exposed entities.",
    ),
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
        raise ValueError(
            f"{dataset_id} contains duplicate primary keys for columns {schema.primary_key}: "
            f"{df.loc[duplicates, list(schema.primary_key)].head(5).to_dict(orient='records')}"
        )


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
        if not isinstance(seed_rules, list):
            raise ValueError(f"Event template '{event_id}' field 'seed_rules' must be a list")
        if not isinstance(macro_seed_rules, list):
            raise ValueError(f"Event template '{event_id}' field 'macro_seed_rules' must be a list")
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
