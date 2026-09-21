from __future__ import annotations

import csv
import io
import json
import re
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "data" / "free_evidence_sources.json"
DATA_GOV_METADATA = "https://data.gov.tw/api/v2/rest/dataset/{dataset_id}"

MONTHLY_REVENUE_ALIASES = {
    "period": ["資料年月", "資料月份", "年月"],
    "ticker": ["公司代號", "公司代碼"],
    "company": ["公司名稱", "公司簡稱"],
    "industry": ["產業別", "產業別名稱"],
    "revenue": ["營業收入-當月營收", "當月營收", "本月營業收入"],
    "yoy": ["營業收入-去年同月增減(%)", "去年同月增減(%)", "去年同月增減"],
    "mom": ["營業收入-上月比較增減(%)", "上月比較增減(%)", "上月比較增減"],
}

TPCA_PATTERNS = [
    ("pcb_revenue_yoy", "PCB", "financial_confirmation", re.compile(r"PCB上市櫃.*?YoY\s*([+-]?\d+(?:\.\d+)?)%", re.I)),
    ("pcb_material_revenue_yoy", "CCL", "financial_confirmation", re.compile(r"PCB原物料營收.*?YoY\s*([+-]?\d+(?:\.\d+)?)%", re.I)),
    ("rigid_pcb_export_yoy", "Networking", "physical_throughput", re.compile(r"硬板出口.*?YoY\s*([+-]?\d+(?:\.\d+)?)%", re.I)),
    ("ccl_import_yoy", "CCL", "physical_throughput", re.compile(r"CCL\s*進口.*?YoY\s*([+-]?\d+(?:\.\d+)?)%", re.I)),
]


@dataclass(frozen=True)
class FetchResult:
    url: str
    collected_at: pd.Timestamp
    payload: bytes


def utc_now() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")


def fetch_bytes(url: str, timeout: int = 30) -> FetchResult:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "chain-survey/1.0 (+public-research; point-in-time evidence)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = resp.read()
        final_url = resp.geturl()
    return FetchResult(final_url, utc_now(), payload)


def _first(row: dict[str, Any], aliases: Iterable[str]) -> Any:
    for key in aliases:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).replace(",", "").replace("%", "").strip()
    if text in {"", "-", "--", "N/A", "nan"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_monthly_revenue_json(
    payload: bytes | str,
    *,
    source_id: str,
    market: str,
    collected_at: pd.Timestamp,
    source_url: str,
) -> pd.DataFrame:
    text = payload.decode("utf-8-sig") if isinstance(payload, bytes) else payload
    rows = json.loads(text)
    if not isinstance(rows, list):
        raise ValueError("Monthly revenue endpoint did not return a list")

    out: list[dict[str, Any]] = []
    for row in rows:
        ticker = _first(row, MONTHLY_REVENUE_ALIASES["ticker"])
        period = _first(row, MONTHLY_REVENUE_ALIASES["period"])
        if not ticker or not period:
            continue
        yoy = _to_float(_first(row, MONTHLY_REVENUE_ALIASES["yoy"]))
        revenue = _to_float(_first(row, MONTHLY_REVENUE_ALIASES["revenue"]))
        mom = _to_float(_first(row, MONTHLY_REVENUE_ALIASES["mom"]))
        out.append({
            "source_id": source_id,
            "provider": market,
            "ticker": str(ticker).strip(),
            "company": str(_first(row, MONTHLY_REVENUE_ALIASES["company"]) or "").strip(),
            "industry": str(_first(row, MONTHLY_REVENUE_ALIASES["industry"]) or "").strip(),
            "period": str(period).strip(),
            "raw_value": revenue,
            "raw_unit": "TWD thousand",
            "yoy_pct": yoy,
            "mom_pct": mom,
            "published_at": collected_at,
            "collected_at": collected_at,
            "source": source_url,
            "availability_policy": "collection_time_conservative",
            "provenance": "LIVE_OFFICIAL_SNAPSHOT",
        })
    return pd.DataFrame(out)


def _walk_for_urls(value: Any) -> list[str]:
    urls: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in {"resourcedownloadurl", "resourcedownload_url", "downloadurl"} and isinstance(child, str):
                urls.append(child)
            urls.extend(_walk_for_urls(child))
    elif isinstance(value, list):
        for child in value:
            urls.extend(_walk_for_urls(child))
    return urls


def extract_data_gov_resource_url(metadata: Any) -> str:
    urls = [u for u in _walk_for_urls(metadata) if u.startswith("http")]
    if not urls:
        raise ValueError("No resource download URL found in data.gov.tw metadata")
    csv_urls = [u for u in urls if "csv" in u.lower()]
    return csv_urls[0] if csv_urls else urls[0]


def parse_moea_export_orders_csv(
    payload: bytes | str,
    *,
    source_id: str,
    chain: str,
    dimension: str,
    collected_at: pd.Timestamp,
    source_url: str,
) -> pd.DataFrame:
    text = payload.decode("utf-8-sig") if isinstance(payload, bytes) else payload
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        raise ValueError("MOEA export-order CSV is empty")

    def pick(row: dict[str, str], names: list[str]) -> str | None:
        for name in names:
            if name in row and row[name] not in (None, ""):
                return row[name]
        return None

    parsed: list[dict[str, Any]] = []
    for row in rows:
        period = pick(row, ["資料期", "資料期(民國年)", "時間", "年月"])
        value = pick(row, ["統計值", "統計值(金額)", "統計值(美元)", "數值"])
        item = pick(row, ["統計項目", "貨品別", "項目"]) or source_id
        number = _to_float(value)
        if period is None or number is None:
            continue
        parsed.append({
            "source_id": source_id,
            "provider": "MOEA",
            "period": str(period).strip(),
            "indicator": str(item).strip(),
            "chain": chain,
            "dimension": dimension,
            "raw_value": number,
            "raw_unit": pick(row, ["計量單位", "計量單位(美元)", "單位"]) or "",
            "published_at": collected_at,
            "collected_at": collected_at,
            "source": source_url,
            "availability_policy": "collection_time_conservative",
            "provenance": "LIVE_OFFICIAL_SNAPSHOT",
        })
    frame = pd.DataFrame(parsed)
    if frame.empty:
        raise ValueError("MOEA parser found no usable observations")
    return frame


def parse_tpca_listing(
    html: bytes | str,
    *,
    collected_at: pd.Timestamp,
    source_url: str,
) -> pd.DataFrame:
    text = html.decode("utf-8", errors="ignore") if isinstance(html, bytes) else html
    clean = re.sub(r"<script.*?</script>|<style.*?</style>", " ", text, flags=re.I | re.S)
    clean = unescape(re.sub(r"<[^>]+>", " ", clean))
    clean = re.sub(r"\s+", " ", clean)

    rows: list[dict[str, Any]] = []
    for metric_id, chain, dimension, pattern in TPCA_PATTERNS:
        for match in pattern.finditer(clean):
            yoy = float(match.group(1))
            start = max(0, match.start() - 80)
            end = min(len(clean), match.end() + 80)
            context = clean[start:end].strip()
            rows.append({
                "source_id": "tpca_monthly_industry",
                "provider": "TPCA",
                "indicator": metric_id,
                "chain": chain,
                "dimension": dimension,
                "yoy_pct": yoy,
                "context": context,
                "published_at": collected_at,
                "collected_at": collected_at,
                "source": source_url,
                "availability_policy": "collection_time_conservative",
                "provenance": "LIVE_PUBLIC_ASSOCIATION_SNAPSHOT",
            })
    return pd.DataFrame(rows).drop_duplicates(subset=["indicator", "yoy_pct"]).reset_index(drop=True)


def load_source_config(path: str | Path = DEFAULT_CONFIG) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
