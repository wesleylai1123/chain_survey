from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in __import__('sys').path:
    __import__('sys').path.append(str(ROOT))

from core.factor_validation_dataset import build_factor_validation_dataset
from core.full_universe_cache import CacheManifest, cache_csv_path, load_cached_universe, merge_cached_frame


API_URL = "https://api.finmindtrade.com/api/v4/data"
DEFAULT_STOCKS = ("2330", "2454", "3037", "3189", "3711", "8046")
DATASETS = {
    "financial_statements": "TaiwanStockFinancialStatements",
    "balance_sheets": "TaiwanStockBalanceSheet",
    "cashflows": "TaiwanStockCashFlowsStatement",
    "monthly_revenue": "TaiwanStockMonthRevenue",
    "prices": "TaiwanStockPrice",
    "valuation": "TaiwanStockPER",
}


def fetch_finmind(dataset: str, stock_id: str, start_date: str, end_date: str, token: str | None = None) -> pd.DataFrame:
    params = {"dataset": dataset, "data_id": stock_id, "start_date": start_date, "end_date": end_date}
    if token:
        params["token"] = token
    url = f"{API_URL}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": "chain-survey-factor-validation/2.0"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"FinMind HTTP {exc.code} dataset={dataset} stock={stock_id}: {detail[:500]}") from exc
    if payload.get("status") not in (200, None):
        raise RuntimeError(f"FinMind {dataset} {stock_id}: {payload.get('msg') or payload}")
    return pd.DataFrame(payload.get("data", []))


def normalize_price(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    result = frame.copy()
    for candidate in ("close", "close_price"):
        if candidate in result.columns:
            if candidate != "close":
                result = result.rename(columns={candidate: "close"})
            break
    if "close" not in result.columns:
        raise ValueError(f"Price dataset missing close column; columns={list(result.columns)}")
    return result


def normalize_valuation(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    result = frame.copy()
    aliases = {"PER": ("PER", "pe_ratio", "PE"), "PBR": ("PBR", "pb_ratio", "PB"), "dividend_yield": ("dividend_yield", "DividendYield")}
    for output, candidates in aliases.items():
        if output in result.columns:
            continue
        for candidate in candidates:
            if candidate in result.columns:
                result = result.rename(columns={candidate: output})
                break
    return result


def load_universe(stocks_arg: str, universe_file: str | None, batch_size: int | None, batch_index: int) -> tuple[tuple[str, ...], pd.DataFrame]:
    companies = pd.read_csv(universe_file) if universe_file else pd.read_csv(ROOT / "data" / "company_master.csv")
    if "stock_id" in companies.columns:
        companies["stock_id"] = companies["stock_id"].astype(str).str.extract(r"(\d{4})", expand=False)
    elif "ticker" in companies.columns:
        companies["stock_id"] = companies["ticker"].astype(str).str.extract(r"(\d{4})", expand=False)
    else:
        raise ValueError("Universe file requires ticker or stock_id column")
    companies = companies.dropna(subset=["stock_id"]).drop_duplicates("stock_id")
    if stocks_arg:
        requested = {value.strip() for value in stocks_arg.split(",") if value.strip()}
        companies = companies[companies["stock_id"].isin(requested)]
    companies = companies.sort_values("stock_id").reset_index(drop=True)
    if batch_size and batch_size > 0:
        start = batch_index * batch_size
        companies = companies.iloc[start : start + batch_size].copy()
    stocks = tuple(companies["stock_id"].astype(str).tolist())
    if not stocks:
        raise ValueError("Universe selection produced no stocks")
    return stocks, companies


def fetch_universe_cached(
    stocks: tuple[str, ...], start_date: str, end_date: str, *, cache_dir: str | Path,
    manifest: CacheManifest, token: str | None = None, sleep_seconds: float = 0.2,
    retry_failed_only: bool = False,
) -> dict[str, pd.DataFrame]:
    cache_dir = Path(cache_dir)
    for stock_id in stocks:
        for key, dataset in DATASETS.items():
            previous = manifest.get(stock_id, key)
            if retry_failed_only and (previous is None or previous.status != "failed"):
                continue
            pending = manifest.pending_range(stock_id, key, start_date, end_date)
            if pending is None:
                print(f"CACHE_HIT dataset={dataset} stock={stock_id} range={start_date}:{end_date}")
                continue
            fetch_start, fetch_end = pending
            try:
                frame = fetch_finmind(dataset, stock_id, fetch_start, fetch_end, token)
                if not frame.empty and "stock_id" not in frame.columns:
                    frame["stock_id"] = stock_id
                if key == "prices":
                    frame = normalize_price(frame)
                elif key == "valuation":
                    frame = normalize_valuation(frame)
                path = cache_csv_path(cache_dir, stock_id, key)
                merged = merge_cached_frame(path, frame)
                path.parent.mkdir(parents=True, exist_ok=True)
                merged.to_csv(path, index=False)
                effective_start = min(pd.Timestamp(start_date), pd.Timestamp(previous.start_date)) if previous else pd.Timestamp(start_date)
                effective_end = max(pd.Timestamp(end_date), pd.Timestamp(previous.end_date)) if previous else pd.Timestamp(end_date)
                manifest.mark_success(stock_id, key, effective_start.date().isoformat(), effective_end.date().isoformat(), len(merged))
                manifest.save()
                print(f"FETCH_OK dataset={dataset} stock={stock_id} fetch={fetch_start}:{fetch_end} new_rows={len(frame)} cached_rows={len(merged)}")
            except Exception as exc:
                manifest.mark_failed(stock_id, key, fetch_start, fetch_end, str(exc))
                manifest.save()
                print(f"FETCH_FAILED dataset={dataset} stock={stock_id} error={exc}")
            time.sleep(sleep_seconds)
    return load_cached_universe(cache_dir, stocks, DATASETS.keys())


def main() -> None:
    parser = argparse.ArgumentParser(description="Build/refresh the quarterly Factor Validation Dataset with persistent per-stock cache.")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default=pd.Timestamp.today().strftime("%Y-%m-%d"))
    parser.add_argument("--stocks", default=",".join(DEFAULT_STOCKS))
    parser.add_argument("--universe-file", default=None)
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--batch-index", type=int, default=0)
    parser.add_argument("--sleep-seconds", type=float, default=0.2)
    parser.add_argument("--token", default=None)
    parser.add_argument("--cache-dir", default=str(ROOT / "artifacts" / "factor_cache"))
    parser.add_argument("--manifest", default=str(ROOT / "artifacts" / "factor_cache_manifest.json"))
    parser.add_argument("--retry-failed-only", action="store_true")
    parser.add_argument("--output", default=str(ROOT / "artifacts" / "factor_validation_dataset.csv"))
    parser.add_argument("--raw-dir", default=str(ROOT / "artifacts" / "factor_validation_raw"))
    args = parser.parse_args()

    stocks, companies = load_universe(args.stocks, args.universe_file, args.batch_size, args.batch_index)
    manifest = CacheManifest(args.manifest)
    print(f"UNIVERSE_OK companies={len(stocks)} batch_index={args.batch_index} batch_size={args.batch_size or 'all'}")
    raw = fetch_universe_cached(
        stocks, args.start, args.end, cache_dir=args.cache_dir, manifest=manifest, token=args.token,
        sleep_seconds=args.sleep_seconds, retry_failed_only=args.retry_failed_only,
    )

    raw_dir = Path(args.raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    for key, frame in raw.items():
        frame.to_csv(raw_dir / f"{key}.csv", index=False)

    if "name" not in companies.columns:
        companies["name"] = companies.get("ticker", companies["stock_id"])
    if "ticker" not in companies.columns:
        companies["ticker"] = companies["stock_id"].astype(str) + ".TW"
    if "sector" not in companies.columns:
        companies["sector"] = "Unknown"
    if "industry" not in companies.columns:
        companies["industry"] = companies["sector"]

    dataset = build_factor_validation_dataset(companies, raw["financial_statements"], raw["balance_sheets"], raw["cashflows"], raw["monthly_revenue"], raw["prices"], raw["valuation"])
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(output, index=False)

    expected = len(stocks) * len(DATASETS)
    print(f"CACHE_SUMMARY={manifest.summary(expected)}")
    valid_targets = dataset[[column for column in ("future_3m_return", "future_6m_return", "future_12m_return") if column in dataset]].notna().sum().to_dict()
    print(f"FACTOR_DATASET_OK rows={len(dataset)} companies={dataset['stock_id'].nunique() if not dataset.empty else 0}")
    print(f"TARGET_COUNTS={valid_targets}")
    print(f"FACTOR_DATASET={output}")


if __name__ == "__main__":
    main()
