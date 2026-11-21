from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in __import__('sys').path:
    __import__('sys').path.append(str(ROOT))

from core.taiwan_universe import normalize_taiwan_stock_info, select_research_sample

API_URL = "https://api.finmindtrade.com/api/v4/data"


def fetch_stock_info(token: str | None = None) -> pd.DataFrame:
    params = {"dataset": "TaiwanStockInfo"}
    if token:
        params["token"] = token
    request = urllib.request.Request(
        f"{API_URL}?{urllib.parse.urlencode(params)}",
        headers={"User-Agent": "chain-survey-taiwan-universe/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"FinMind HTTP {exc.code} TaiwanStockInfo: {detail[:500]}") from exc
    if payload.get("status") not in (200, None):
        raise RuntimeError(f"FinMind TaiwanStockInfo: {payload.get('msg') or payload}")
    return pd.DataFrame(payload.get("data", []))


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a normalized TWSE/TPEx common-stock universe from FinMind TaiwanStockInfo.")
    parser.add_argument("--token", default=None)
    parser.add_argument("--output", default=str(ROOT / "artifacts" / "taiwan_stock_universe.csv"))
    parser.add_argument("--sample-output", default=str(ROOT / "artifacts" / "taiwan_research_sample.csv"))
    parser.add_argument("--sample-industries", type=int, default=6)
    parser.add_argument("--sample-per-industry", type=int, default=2)
    args = parser.parse_args()

    raw = fetch_stock_info(args.token)
    universe = normalize_taiwan_stock_info(raw)
    sample = select_research_sample(
        universe,
        industries=args.sample_industries,
        per_industry=args.sample_per_industry,
    )

    output = Path(args.output)
    sample_output = Path(args.sample_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    sample_output.parent.mkdir(parents=True, exist_ok=True)
    universe.to_csv(output, index=False)
    sample.to_csv(sample_output, index=False)

    print(f"TAIWAN_UNIVERSE_OK rows={len(universe)} industries={universe['industry'].nunique()} markets={universe['market'].nunique()}")
    print(f"TAIWAN_RESEARCH_SAMPLE_OK rows={len(sample)} industries={sample['industry'].nunique()}")
    print(f"TAIWAN_UNIVERSE={output}")
    print(f"TAIWAN_RESEARCH_SAMPLE={sample_output}")


if __name__ == "__main__":
    main()
