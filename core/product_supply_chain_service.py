from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from core import data_loader
from core.data_validation import validate_dataframe

MANAGED_RELATION_BY_DIRECTION = {
    "upstream": "supplier_of",
    "downstream": "customer_of",
}

MANAGED_MAPPING_COLUMNS = (
    "source_company",
    "source_product",
    "direction",
    "related_company",
    "relation",
    "weight",
    "rationale",
    "updated_at",
)


def _empty_managed_mapping_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=list(MANAGED_MAPPING_COLUMNS))


def load_managed_mappings() -> pd.DataFrame:
    df = data_loader.load_product_supply_chain_mappings().copy()
    if df.empty:
        return _empty_managed_mapping_frame()
    return df


def validate_managed_mappings(df: pd.DataFrame) -> None:
    validate_dataframe("product_supply_chain_mappings", df)
    if df.empty:
        return

    companies = set(data_loader.load_companies()["name"].astype(str))
    company_products = data_loader.load_company_product_relationships()[["company", "product"]].drop_duplicates()
    valid_company_products = set(company_products.itertuples(index=False, name=None))
    errors: list[str] = []

    for idx, row in df.reset_index(drop=True).iterrows():
        prefix = f"row {idx + 1}"
        source_company = str(row["source_company"])
        source_product = str(row["source_product"])
        direction = str(row["direction"]).strip().lower()
        related_company = str(row["related_company"])
        relation = str(row["relation"]).strip()
        rationale = str(row["rationale"]).strip()

        if source_company not in companies:
            errors.append(f"{prefix}: unknown source_company '{source_company}'")
        if related_company not in companies:
            errors.append(f"{prefix}: unknown related_company '{related_company}'")
        if (source_company, source_product) not in valid_company_products:
            errors.append(f"{prefix}: product '{source_product}' is not associated with '{source_company}'")
        if source_company == related_company:
            errors.append(f"{prefix}: source_company and related_company cannot be the same")
        if direction not in MANAGED_RELATION_BY_DIRECTION:
            errors.append(f"{prefix}: invalid direction '{direction}'")
        elif relation != MANAGED_RELATION_BY_DIRECTION[direction]:
            errors.append(
                f"{prefix}: relation '{relation}' does not match direction '{direction}' "
                f"(expected '{MANAGED_RELATION_BY_DIRECTION[direction]}')"
            )
        try:
            weight = float(row["weight"])
        except (TypeError, ValueError):
            errors.append(f"{prefix}: weight must be numeric")
        else:
            if not 0.0 < weight <= 1.0:
                errors.append(f"{prefix}: weight must be between 0 and 1")
        if not rationale:
            errors.append(f"{prefix}: rationale cannot be empty")
        if not str(row["updated_at"]).strip():
            errors.append(f"{prefix}: updated_at cannot be empty")

    if errors:
        raise ValueError("; ".join(errors[:8]))


def _write_managed_mappings(df: pd.DataFrame) -> None:
    output = df.copy()
    validate_managed_mappings(output)
    output = output.sort_values(
        ["source_company", "source_product", "direction", "related_company"],
        kind="stable",
    ).reset_index(drop=True)
    path = data_loader.DATA_DIR / "product_supply_chain_mappings.csv"
    output.to_csv(path, index=False)
    data_loader.clear_data_caches()


def upsert_managed_mapping(
    *,
    source_company: str,
    source_product: str,
    direction: str,
    related_company: str,
    weight: float,
    rationale: str,
    original_key: tuple[str, str, str, str] | None = None,
) -> dict[str, object]:
    normalized_direction = direction.strip().lower()
    if normalized_direction not in MANAGED_RELATION_BY_DIRECTION:
        raise ValueError(f"Unsupported direction: {direction}")

    relation = MANAGED_RELATION_BY_DIRECTION[normalized_direction]
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    current = load_managed_mappings()

    if original_key is not None:
        original_mask = (
            (current["source_company"] == original_key[0])
            & (current["source_product"] == original_key[1])
            & (current["direction"] == original_key[2])
            & (current["related_company"] == original_key[3])
        )
        current = current.loc[~original_mask].copy()

    new_row = pd.DataFrame(
        [
            {
                "source_company": source_company,
                "source_product": source_product,
                "direction": normalized_direction,
                "related_company": related_company,
                "relation": relation,
                "weight": float(weight),
                "rationale": rationale.strip(),
                "updated_at": timestamp,
            }
        ]
    )
    combined = new_row if current.empty else pd.concat([current, new_row], ignore_index=True)
    _write_managed_mappings(combined)
    return new_row.iloc[0].to_dict()


def delete_managed_mapping(*, source_company: str, source_product: str, direction: str, related_company: str) -> None:
    current = load_managed_mappings()
    if current.empty:
        raise ValueError("No managed mappings exist")

    mask = (
        (current["source_company"] == source_company)
        & (current["source_product"] == source_product)
        & (current["direction"] == direction)
        & (current["related_company"] == related_company)
    )
    if not mask.any():
        raise ValueError("Managed mapping not found")

    remaining = current.loc[~mask].copy()
    if remaining.empty:
        remaining = _empty_managed_mapping_frame()
    _write_managed_mappings(remaining)


def get_managed_mappings_for_product(company_name: str, product_name: str | None = None) -> pd.DataFrame:
    df = load_managed_mappings()
    if df.empty:
        out = _empty_managed_mapping_frame()
    else:
        out = df[df["source_company"] == company_name].copy()
        if product_name:
            out = out[out["source_product"] == product_name].copy()
    out["source_dataset"] = "analyst_managed"
    return out


def get_chain_context(company_name: str) -> pd.DataFrame:
    df = load_managed_mappings()
    if df.empty:
        return pd.DataFrame(
            columns=[
                "context_role",
                "counterparty_company",
                "counterparty_product",
                "direction",
                "relation",
                "weight",
                "rationale",
                "updated_at",
            ]
        )

    rows: list[dict[str, object]] = []
    for _, row in df.iterrows():
        if row["source_company"] == company_name:
            rows.append(
                {
                    "context_role": "configured_on_this_company",
                    "counterparty_company": row["related_company"],
                    "counterparty_product": row["source_product"],
                    "direction": row["direction"],
                    "relation": row["relation"],
                    "weight": row["weight"],
                    "rationale": row["rationale"],
                    "updated_at": row["updated_at"],
                }
            )
        if row["related_company"] == company_name:
            rows.append(
                {
                    "context_role": "referenced_by_other_company",
                    "counterparty_company": row["source_company"],
                    "counterparty_product": row["source_product"],
                    "direction": row["direction"],
                    "relation": row["relation"],
                    "weight": row["weight"],
                    "rationale": row["rationale"],
                    "updated_at": row["updated_at"],
                }
            )

    if not rows:
        return pd.DataFrame(
            columns=[
                "context_role",
                "counterparty_company",
                "counterparty_product",
                "direction",
                "relation",
                "weight",
                "rationale",
                "updated_at",
            ]
        )

    return pd.DataFrame(rows).sort_values(
        ["context_role", "counterparty_company", "counterparty_product"],
        kind="stable",
    ).reset_index(drop=True)


def load_merged_company_relationships() -> pd.DataFrame:
    curated = data_loader.load_company_relationships().copy()
    curated["source_dataset"] = "curated"
    curated["mapped_products"] = "-"
    curated["rationale"] = "-"

    managed = load_managed_mappings()
    if managed.empty:
        return curated

    managed_rows: list[dict[str, object]] = []
    for _, row in managed.iterrows():
        if row["direction"] == "upstream":
            source_company = row["related_company"]
            target_company = row["source_company"]
        else:
            source_company = row["source_company"]
            target_company = row["related_company"]

        managed_rows.append(
            {
                "source_company": source_company,
                "relation": row["relation"],
                "target_company": target_company,
                "weight": row["weight"],
                "source_dataset": "analyst_managed",
                "mapped_products": row["source_product"],
                "rationale": row["rationale"],
            }
        )

    managed_df = pd.DataFrame(managed_rows)
    managed_df = (
        managed_df.groupby(["source_company", "relation", "target_company", "source_dataset"], as_index=False)
        .agg(
            weight=("weight", "max"),
            mapped_products=("mapped_products", lambda values: ", ".join(sorted(set(map(str, values))))),
            rationale=("rationale", lambda values: " | ".join(list(dict.fromkeys(map(str, values)))[:3])),
        )
    )
    return pd.concat([curated, managed_df], ignore_index=True)
