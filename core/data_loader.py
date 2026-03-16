from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"


@lru_cache(maxsize=1)
def load_companies() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "companies.csv")


@lru_cache(maxsize=1)
def load_products() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "products.csv")


@lru_cache(maxsize=1)
def load_edges() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "edges.csv")


@lru_cache(maxsize=1)
def load_financials() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "financials.csv")


@lru_cache(maxsize=1)
def load_events() -> list[dict]:
    with open(DATA_DIR / "events.json", "r", encoding="utf-8") as f:
        return json.load(f)
