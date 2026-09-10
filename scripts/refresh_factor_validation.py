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
    params = {
        "dataset": dataset,
        "data_id": stock_id,
        "start_date": start_date,
        "end_date": end_date,
    }
    if token:
        params["token"] = token
    url = f"{API_URL}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": "chain-survey-factor-validation/1.0"})
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
    aliases = {
        "PER": ("PER", "pe_ratio", "PE"),
        "PBR": ("PBR", "pb_ratio", "PB"),
        "dividend_yield": ("dividend_yield", "DividendYield"),
    }
    for output, candidates in aliases.items():
        if output in result.columns:
            continue
        for candidate in candidates:
            if candidate in result.columns:
                result = result.rename(columns={candidate: output})
                break
    return result


def fetch_universe(stocks: tuple[str, ...], start_date: str, end_date: str, token: str | None = None, sleep_seconds: float = 0.2) -> dict[str, pd.DataFrame]:
    collected: dict[str, list[pd.DataFrame]] = {key: [] for key in DATASETS}
    for stock_id in stocks:
        for key, dataset in DATASETS.items():
            frame = fetch_finmind(dataset, stock_id, start_date, end_date, token)
            if not frame.empty and "stock_id" not in frame.columns:
                frame["stock_id"] = stock_id
            if key == "prices":
                frame = normalize_price(frame)
            elif key == "valuation":
                frame = normalize_valuation(frame)
            collected[key].append(frame)
            print(f"FETCH_OK dataset={dataset} stock={stock_id} rows={len(frame)} columns={','.join(frame.columns)}")
            time.sleep(sleep_seconds)
    return {key: pd.concat(parts, ignore_index=True) if parts else pd.DataFrame() for key, parts in collected.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the real quarterly Factor Validation Dataset from FinMind historical data.")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default=pd.Timestamp.today().strftime("%Y-%m-%d"))
    parser.add_argument("--stocks", default=",".join(DEFAULT_STOCKS))
    parser.add_argument("--token", default=None, help="Optional FinMind token; public endpoints work without one subject to rate limits.")
    parser.add_argument("--output", default=str(ROOT / "artifacts" / "factor_validation_dataset.csv"))
    parser.add_argument("--raw-dir", default=str(ROOT / "artifacts" / "factor_validation_raw"))
    args = parser.parse_args()

    stocks = tuple(value.strip() for value in args.stocks.split(",") if value.strip())
    raw = fetch_universe(stocks, args.start, args.end, args.token)
    raw_dir = Path(args.raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    for key, frame in raw.items():
        frame.to_csv(raw_dir / f"{key}.csv", index=False)

    companies = pd.read_csv(ROOT / "data" / "company_master.csv")
    dataset = build_factor_validation_dataset(
        companies,
        raw["financial_statements"],
        raw["balance_sheets"],
        raw["cashflows"],
        raw["monthly_revenue"],
        raw["prices"],
        raw["valuation"],
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(output, index=False)

    valid_targets = dataset[[column for column in ("future_3m_return", "future_6m_return", "future_12m_return") if column in dataset]].notna().sum().to_dict()
    print(f"FACTOR_DATASET_OK rows={len(dataset)} companies={dataset['stock_id'].nunique() if not dataset.empty else 0}")
    print(f"TARGET_COUNTS={valid_targets}")
    print(f"FACTOR_DATASET={output}")


if __name__ == "__main__":
    main()
