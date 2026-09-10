from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd


@dataclass
class CacheEntry:
    stock_id: str
    dataset_key: str
    start_date: str
    end_date: str
    row_count: int
    status: str = "success"
    last_success: str | None = None
    error: str | None = None
    source: str = "FinMind"


class CacheManifest:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.entries: dict[str, CacheEntry] = {}
        self._load()

    @staticmethod
    def key(stock_id: str, dataset_key: str) -> str:
        return f"{stock_id}:{dataset_key}"

    def _load(self) -> None:
        if not self.path.exists():
            return
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        for key, value in payload.get("entries", {}).items():
            self.entries[key] = CacheEntry(**value)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "entries": {key: asdict(value) for key, value in sorted(self.entries.items())},
        }
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def get(self, stock_id: str, dataset_key: str) -> CacheEntry | None:
        return self.entries.get(self.key(stock_id, dataset_key))

    def mark_success(self, stock_id: str, dataset_key: str, start_date: str, end_date: str, row_count: int) -> None:
        self.entries[self.key(stock_id, dataset_key)] = CacheEntry(
            stock_id=str(stock_id), dataset_key=dataset_key, start_date=start_date, end_date=end_date,
            row_count=int(row_count), status="success", last_success=datetime.now(timezone.utc).isoformat(), error=None,
        )

    def mark_failed(self, stock_id: str, dataset_key: str, start_date: str, end_date: str, error: str) -> None:
        previous = self.get(stock_id, dataset_key)
        self.entries[self.key(stock_id, dataset_key)] = CacheEntry(
            stock_id=str(stock_id), dataset_key=dataset_key,
            start_date=previous.start_date if previous else start_date,
            end_date=previous.end_date if previous else end_date,
            row_count=previous.row_count if previous else 0,
            status="failed", last_success=previous.last_success if previous else None, error=str(error)[:1000],
        )

    def pending_range(self, stock_id: str, dataset_key: str, requested_start: str, requested_end: str) -> tuple[str, str] | None:
        entry = self.get(stock_id, dataset_key)
        if entry is None or entry.status == "failed":
            return requested_start, requested_end
        cached_start = pd.Timestamp(entry.start_date)
        cached_end = pd.Timestamp(entry.end_date)
        start = pd.Timestamp(requested_start)
        end = pd.Timestamp(requested_end)
        if cached_start <= start and cached_end >= end:
            return None
        if cached_start <= start <= cached_end < end:
            return (cached_end + pd.Timedelta(days=1)).date().isoformat(), end.date().isoformat()
        return requested_start, requested_end

    def summary(self, expected_items: int | None = None) -> dict[str, int]:
        values = list(self.entries.values())
        success = sum(item.status == "success" for item in values)
        failed = sum(item.status == "failed" for item in values)
        cached = len(values)
        pending = max((expected_items or cached) - success, 0)
        return {"cached": cached, "success": success, "failed": failed, "pending": pending}


def cache_csv_path(cache_dir: str | Path, stock_id: str, dataset_key: str) -> Path:
    return Path(cache_dir) / str(stock_id) / f"{dataset_key}.csv"


def merge_cached_frame(path: str | Path, new_frame: pd.DataFrame) -> pd.DataFrame:
    target = Path(path)
    old = pd.read_csv(target) if target.exists() and target.stat().st_size else pd.DataFrame()
    if old.empty:
        merged = new_frame.copy()
    elif new_frame.empty:
        merged = old
    else:
        merged = pd.concat([old, new_frame], ignore_index=True, sort=False)
    if merged.empty:
        return merged
    dedupe = [column for column in ("date", "stock_id", "type") if column in merged.columns]
    if "date" in merged.columns and len(dedupe) >= 2:
        merged = merged.drop_duplicates(dedupe, keep="last")
        merged = merged.sort_values([column for column in ("stock_id", "date", "type") if column in merged.columns])
    return merged.reset_index(drop=True)


def load_cached_universe(cache_dir: str | Path, stocks: Iterable[str], dataset_keys: Iterable[str]) -> dict[str, pd.DataFrame]:
    collected: dict[str, list[pd.DataFrame]] = {key: [] for key in dataset_keys}
    for stock_id in stocks:
        for key in dataset_keys:
            path = cache_csv_path(cache_dir, stock_id, key)
            if path.exists() and path.stat().st_size:
                collected[key].append(pd.read_csv(path))
    return {key: pd.concat(parts, ignore_index=True, sort=False) if parts else pd.DataFrame() for key, parts in collected.items()}
