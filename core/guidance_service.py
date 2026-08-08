from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

import pandas as pd

from core import data_loader
from core.data_validation import validate_dataframe

VALID_CATEGORIES = {"revenue_growth", "gross_margin", "product_line", "capex", "other"}
VALID_DIRECTIONS = {"up", "down", "flat"}
VALID_STATUSES = {"pending_review", "confirmed", "rejected"}

PERIOD_PATTERN = re.compile(r"^(\d+)Q([1-4])$")

SOURCE_DOCUMENT_COLUMNS = ("doc_id", "ticker", "file_path", "source_quarter", "call_date")
GUIDANCE_CLAIM_COLUMNS = (
    "claim_id",
    "doc_id",
    "ticker",
    "source_quarter",
    "target_period",
    "category",
    "product_or_segment",
    "direction",
    "quant_low",
    "quant_high",
    "raw_text",
    "status",
    "reviewed_by",
    "reviewed_at",
)


def parse_period(period: str) -> tuple[int, int]:
    match = PERIOD_PATTERN.match(str(period))
    if not match:
        raise ValueError(f"Invalid period format: '{period}', expected e.g. '114Q3'")
    return int(match.group(1)), int(match.group(2))


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _known_tickers() -> set[str]:
    return set(data_loader.load_companies()["ticker"].astype(str))


# ---------------------------------------------------------------------------
# source_documents
# ---------------------------------------------------------------------------

def load_source_documents() -> pd.DataFrame:
    return data_loader.load_source_documents()


def register_source_document(*, ticker: str, file_path: str, source_quarter: str, call_date: str) -> dict[str, object]:
    if ticker not in _known_tickers():
        raise ValueError(f"Unknown ticker: '{ticker}'")
    parse_period(source_quarter)
    if not file_path.strip():
        raise ValueError("file_path cannot be empty")

    row = {
        "doc_id": uuid.uuid4().hex[:12],
        "ticker": ticker,
        "file_path": file_path,
        "source_quarter": source_quarter,
        "call_date": call_date,
    }
    current = load_source_documents()
    combined = pd.concat([current, pd.DataFrame([row])], ignore_index=True) if not current.empty else pd.DataFrame([row])
    validate_dataframe("source_documents", combined)
    combined.to_csv(data_loader.DATA_DIR / "source_documents.csv", index=False)
    data_loader.clear_data_caches()
    return row


# ---------------------------------------------------------------------------
# guidance_claims
# ---------------------------------------------------------------------------

def load_guidance_claims(status: str | None = None) -> pd.DataFrame:
    df = data_loader.load_guidance_claims()
    if status is not None and not df.empty:
        df = df[df["status"] == status].copy()
    return df


def _validate_claim_fields(
    *,
    ticker: str,
    source_quarter: str,
    target_period: str,
    category: str,
    direction: str,
    quant_low: float | None,
    quant_high: float | None,
    raw_text: str,
) -> None:
    if ticker not in _known_tickers():
        raise ValueError(f"Unknown ticker: '{ticker}'")
    parse_period(source_quarter)
    parse_period(target_period)
    if category not in VALID_CATEGORIES:
        raise ValueError(f"Invalid category '{category}', expected one of {sorted(VALID_CATEGORIES)}")
    if direction not in VALID_DIRECTIONS:
        raise ValueError(f"Invalid direction '{direction}', expected one of {sorted(VALID_DIRECTIONS)}")
    if quant_low is not None and quant_high is not None and float(quant_low) > float(quant_high):
        raise ValueError("quant_low cannot be greater than quant_high")
    if not raw_text.strip():
        raise ValueError("raw_text cannot be empty")


def add_claim(
    *,
    doc_id: str,
    ticker: str,
    source_quarter: str,
    target_period: str,
    category: str,
    product_or_segment: str | None,
    direction: str,
    quant_low: float | None,
    quant_high: float | None,
    raw_text: str,
) -> dict[str, object]:
    _validate_claim_fields(
        ticker=ticker,
        source_quarter=source_quarter,
        target_period=target_period,
        category=category,
        direction=direction,
        quant_low=quant_low,
        quant_high=quant_high,
        raw_text=raw_text,
    )

    row = {
        "claim_id": uuid.uuid4().hex[:12],
        "doc_id": doc_id,
        "ticker": ticker,
        "source_quarter": source_quarter,
        "target_period": target_period,
        "category": category,
        "product_or_segment": product_or_segment or "",
        "direction": direction,
        "quant_low": quant_low,
        "quant_high": quant_high,
        "raw_text": raw_text.strip(),
        "status": "pending_review",
        "reviewed_by": "",
        "reviewed_at": "",
    }
    _append_claim_row(row)
    return row


def _append_claim_row(row: dict[str, object]) -> None:
    current = data_loader.load_guidance_claims()
    combined = pd.concat([current, pd.DataFrame([row])], ignore_index=True) if not current.empty else pd.DataFrame([row])
    validate_dataframe("guidance_claims", combined)
    combined.to_csv(data_loader.DATA_DIR / "guidance_claims.csv", index=False)
    data_loader.clear_data_caches()


def _get_claim_row(claim_id: str) -> pd.Series:
    claims = data_loader.load_guidance_claims()
    matches = claims[claims["claim_id"] == claim_id]
    if matches.empty:
        raise ValueError(f"No claim found with claim_id '{claim_id}'")
    return matches.iloc[0]


def _write_all_claims(df: pd.DataFrame) -> None:
    validate_dataframe("guidance_claims", df)
    df.to_csv(data_loader.DATA_DIR / "guidance_claims.csv", index=False)
    data_loader.clear_data_caches()


def update_claim(claim_id: str, **fields: object) -> dict[str, object]:
    current_row = _get_claim_row(claim_id)
    if current_row["status"] != "pending_review":
        raise ValueError(f"Claim '{claim_id}' is '{current_row['status']}' and can no longer be edited")

    updated = current_row.to_dict()
    updated.update(fields)
    _validate_claim_fields(
        ticker=str(updated["ticker"]),
        source_quarter=str(updated["source_quarter"]),
        target_period=str(updated["target_period"]),
        category=str(updated["category"]),
        direction=str(updated["direction"]),
        quant_low=updated.get("quant_low"),
        quant_high=updated.get("quant_high"),
        raw_text=str(updated["raw_text"]),
    )

    claims = data_loader.load_guidance_claims()
    claims.loc[claims["claim_id"] == claim_id, list(updated.keys())] = list(updated.values())
    _write_all_claims(claims)
    return updated


def confirm_claim(claim_id: str, *, reviewed_by: str) -> dict[str, object]:
    return _set_review_status(claim_id, status="confirmed", reviewed_by=reviewed_by)


def reject_claim(claim_id: str, *, reviewed_by: str) -> dict[str, object]:
    return _set_review_status(claim_id, status="rejected", reviewed_by=reviewed_by)


def _set_review_status(claim_id: str, *, status: str, reviewed_by: str) -> dict[str, object]:
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status '{status}'")
    current_row = _get_claim_row(claim_id)
    if current_row["status"] != "pending_review":
        raise ValueError(f"Claim '{claim_id}' is already '{current_row['status']}'")

    claims = data_loader.load_guidance_claims()
    mask = claims["claim_id"] == claim_id
    # Ensure string columns have object dtype to avoid FutureWarning
    claims["reviewed_by"] = claims["reviewed_by"].astype(object)
    claims["reviewed_at"] = claims["reviewed_at"].astype(object)
    claims.loc[mask, "status"] = status
    claims.loc[mask, "reviewed_by"] = reviewed_by
    claims.loc[mask, "reviewed_at"] = _now_iso()
    _write_all_claims(claims)
    return claims.loc[mask].iloc[0].to_dict()


def delete_claim(claim_id: str) -> None:
    claims = data_loader.load_guidance_claims()
    mask = claims["claim_id"] == claim_id
    if not mask.any():
        raise ValueError(f"No claim found with claim_id '{claim_id}'")
    remaining = claims.loc[~mask].reset_index(drop=True)
    if remaining.empty:
        remaining = pd.DataFrame(columns=list(GUIDANCE_CLAIM_COLUMNS))
    _write_all_claims(remaining)
