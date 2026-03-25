from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DatasetSchema:
    dataset_id: str
    required_columns: tuple[str, ...]
    primary_key: tuple[str, ...]
    description: str


@dataclass(frozen=True)
class CompanyMasterRecord:
    name: str
    ticker: str
    country: str
    sector: str
    industry: str
    description: str
    key_drivers: str


@dataclass(frozen=True)
class ProductMasterRecord:
    name: str
    category: str
    application: str
    description: str


@dataclass(frozen=True)
class CompanyRelationshipRecord:
    source_company: str
    relation: str
    target_company: str
    weight: float


@dataclass(frozen=True)
class CompanyProductRelationshipRecord:
    company: str
    relation: str
    product: str
    weight: float


@dataclass(frozen=True)
class ProductSupplyChainMappingRecord:
    source_company: str
    source_product: str
    direction: str
    related_company: str
    relation: str
    weight: float
    rationale: str
    updated_at: str


@dataclass(frozen=True)
class FinancialFieldDefinitionRecord:
    field_name: str
    display_name: str
    unit: str
    frequency: str
    description: str


@dataclass(frozen=True)
class ExternalFundamentalSourceRecord:
    source_id: str
    dataset: str
    provider: str
    frequency: str
    format: str
    status: str
    notes: str


@dataclass(frozen=True)
class MacroFactorRecord:
    factor_id: str
    display_name: str
    category: str
    unit: str
    description: str


@dataclass(frozen=True)
class MacroExposureRecord:
    factor_id: str
    entity_type: str
    entity_name: str
    exposure_direction: str
    weight: float
    rationale: str


@dataclass(frozen=True)
class EventSeedRule:
    match: dict[str, str]
    impact_on: str
    sentiment: str
    base_score: float
    sensitivity: float
    reason: str
    start_lag: int = 0
    allow_backflow: bool = False


@dataclass(frozen=True)
class EventTemplate:
    event_id: str
    name: str
    description: str
    severity: float
    max_layers: int
    seed_rules: tuple[EventSeedRule, ...]
    industry_sensitivity: dict[str, float] = field(default_factory=dict)
    sector_sensitivity: dict[str, float] = field(default_factory=dict)
    relation_overrides: dict[str, dict[str, float | int]] = field(default_factory=dict)
