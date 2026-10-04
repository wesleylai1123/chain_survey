"""Point-in-time export of reported monthly revenue YoY observations."""

from __future__ import annotations

import calendar
from datetime import datetime, timezone
import math
import re
from typing import Iterable, Mapping
from urllib.parse import urlsplit


MODEL_VERSION = "monthly-revenue-yoy-v1"
DEFAULT_STOCK_IDS = ("3037", "3189", "8046")
_PERIOD = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_SHA = re.compile(r"^[0-9a-f]{7,40}$")
_PUBLICATION_METHODS = {"regulatory_deadline_proxy", "source_reported", "actual_publication_time"}
_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\Z")


def _timestamp(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not _TIMESTAMP.fullmatch(value):
        raise ValueError(f"{field} requires a timezone-aware RFC3339 timestamp")
    if not value.endswith("Z") and (int(value[-5:-3]) >= 24 or int(value[-2:]) >= 60):
        raise ValueError(f"{field} has an invalid timezone offset")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} has an invalid timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} requires a timezone")
    return parsed


def _text(row: Mapping[str, object], field: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _source_url(row: Mapping[str, object]) -> str:
    value = _text(row, "source_url")
    try:
        parts = urlsplit(value)
        host = parts.hostname
        port = parts.port
    except ValueError as exc:
        raise ValueError("source_url must be an HTTP(S) URL with a host") from exc
    if parts.scheme not in {"http", "https"} or not host or any(char.isspace() for char in value):
        raise ValueError("source_url must be an HTTP(S) URL with a host")
    return value


def _reviewed(row: Mapping[str, object]) -> bool:
    for key in ("review_status", "status", "quality_status"):
        if key in row and str(row[key]).strip().lower() not in {"accepted", "approved", "reviewed", "published", "reported"}:
            return False
    for key in ("accepted", "is_accepted"):
        if key in row and str(row[key]).strip().lower() not in {"true", "1", "yes", "accepted"}:
            return False
    return True


def _prepare(
    rows: Iterable[Mapping[str, object]],
    *,
    snapshot_acquired_at: str,
    as_of: str,
    commit_sha: str,
    input_snapshot_id: str,
    stock_ids: Iterable[str],
) -> tuple[list[dict], dict]:
    acquired = _timestamp(snapshot_acquired_at, "snapshot_acquired_at")
    cutoff = _timestamp(as_of, "as_of")
    if cutoff < acquired:
        raise ValueError("as_of cannot precede snapshot_acquired_at")
    if not isinstance(commit_sha, str) or not _SHA.fullmatch(commit_sha):
        raise ValueError("commit_sha must be 7 to 40 lowercase hex characters")
    if not isinstance(input_snapshot_id, str) or not input_snapshot_id.strip():
        raise ValueError("input_snapshot_id is required")
    requested = tuple(str(code).strip() for code in stock_ids)
    if not requested or len(set(requested)) != len(requested) or any(not re.fullmatch(r"\d{4}", code) for code in requested):
        raise ValueError("stock_ids must contain distinct four-digit codes")

    selected: dict[str, tuple[str, dict, float, datetime]] = {}
    seen: dict[tuple[str, str], dict] = {}
    skipped = {"unrelated_ticker": 0, "unreviewed_or_unaccepted": 0, "future_publication": 0}
    for row in rows:
        ticker = str(row.get("ticker", "")).strip()
        code = ticker.split(".", 1)[0]
        if code not in requested or ticker != f"{code}.TW":
            skipped["unrelated_ticker"] += 1
            continue
        if not _reviewed(row):
            skipped["unreviewed_or_unaccepted"] += 1
            continue
        _text(row, "company")
        period = _text(row, "period")
        if not _PERIOD.fullmatch(period):
            raise ValueError(f"invalid period: {period}")
        year, month = map(int, period.split("-"))
        if year < 1:
            raise ValueError(f"invalid period: {period}")
        period_end = f"{period}-{calendar.monthrange(year, month)[1]:02d}"
        period_date = _timestamp(row.get("period_date"), "period_date")
        if period_date.date().isoformat() != period_end:
            raise ValueError(f"period_date does not match {period}")
        published = _timestamp(row.get("published_at"), "published_at")
        if published.date() < period_date.date():
            raise ValueError("publication precedes observation period end")
        source = _text(row, "source")
        source_url = _source_url(row)
        method = _text(row, "knowledge_time_method")
        if method not in _PUBLICATION_METHODS:
            raise ValueError(f"knowledge_time_method is not recognized: {method}")
        transport = _text(row, "transport")
        raw_yoy = row.get("yoy_pct")
        if isinstance(raw_yoy, bool):
            raise ValueError("yoy_pct must be finite numeric data")
        try:
            yoy = float(raw_yoy)
        except (TypeError, ValueError) as exc:
            raise ValueError("yoy_pct must be finite numeric data") from exc
        if not math.isfinite(yoy):
            raise ValueError("yoy_pct must be finite numeric data")
        raw_revenue = row.get("monthly_revenue")
        if isinstance(raw_revenue, bool):
            raise ValueError("monthly_revenue must be finite numeric data")
        try:
            revenue = float(raw_revenue)
        except (TypeError, ValueError) as exc:
            raise ValueError("monthly_revenue must be finite numeric data") from exc
        if not math.isfinite(revenue):
            raise ValueError("monthly_revenue must be finite numeric data")
        normalized = {
            "company": _text(row, "company"),
            "monthly_revenue": revenue,
            "period_date": period_date.isoformat(),
            "published_at": published.isoformat(),
            "yoy_pct": yoy,
            "source": source,
            "source_url": source_url,
            "knowledge_time_method": method,
            "transport": transport,
        }
        key = (code, period)
        if key in seen and seen[key] != normalized:
            raise ValueError(f"conflicting duplicate for {code} {period}")
        seen[key] = normalized
        if published > cutoff:
            skipped["future_publication"] += 1
            continue
        if code not in selected or period > selected[code][0]:
            selected[code] = (period, normalized, yoy, published)

    missing = sorted(set(requested) - selected.keys())
    if missing:
        raise ValueError(f"no eligible monthly revenue row for: {', '.join(missing)}")

    records: list[dict] = []
    details: list[dict] = []
    warnings: set[str] = set()
    for code, (period, row, yoy, published) in selected.items():
        is_proxy = row["knowledge_time_method"] == "regulatory_deadline_proxy"
        if is_proxy:
            warnings.add("PROXY_PUBLICATION_TIME")
        available = max(acquired, published)
        period_end = f"{period}-{calendar.monthrange(int(period[:4]), int(period[5:]))[1]:02d}"
        record = {
            "contract": "ResearchSignalV1",
            "schema_version": "1.0.0",
            "entity_id": f"TWSE:{code}",
            "market": "TW",
            "signal_id": "monthly_revenue.yoy",
            "signal_value": yoy,
            "observation_period": {"start": f"{period}-01", "end": period_end},
            "available_at": available.astimezone(timezone.utc).isoformat(),
            "source": row["source"],
            "source_version": f"knowledge_time_method={row['knowledge_time_method']};transport={row['transport']};published_at={row['published_at']}",
            "model_version": MODEL_VERSION,
            "confidence": 0.65 if is_proxy else 1.0,
            "is_estimate": is_proxy,
            "lineage": {
                "input_snapshot_id": input_snapshot_id,
                "commit_sha": commit_sha,
                "inputs": [f"input_snapshot_id:{input_snapshot_id}", f"source_url:{row['source_url']}"],
            },
        }
        records.append(record)
        details.append({"entity_id": record["entity_id"], "period": period, "source_url": row["source_url"], "knowledge_time_method": row["knowledge_time_method"], "published_at": row["published_at"]})
    records.sort(key=lambda signal: (-signal["signal_value"], signal["entity_id"]))
    for rank, record in enumerate(records, 1):
        record["rank"] = rank
    details.sort(key=lambda item: item["entity_id"])
    return records, {"signals": details, "quality_warnings": sorted(warnings), "skipped_counts": skipped}


def build_research_signals(
    rows: Iterable[Mapping[str, object]],
    *,
    snapshot_acquired_at: str,
    as_of: str,
    commit_sha: str,
    input_snapshot_id: str,
    stock_ids: Iterable[str] = DEFAULT_STOCK_IDS,
) -> list[dict]:
    """Return latest eligible reported monthly YoY signal for every requested stock."""
    return _prepare(
        rows,
        snapshot_acquired_at=snapshot_acquired_at,
        as_of=as_of,
        commit_sha=commit_sha,
        input_snapshot_id=input_snapshot_id,
        stock_ids=stock_ids,
    )[0]
