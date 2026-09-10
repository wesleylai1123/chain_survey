from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd


DEFAULT_MARKETS = ("twse", "tpex")


def normalize_taiwan_stock_info(
    frame: pd.DataFrame,
    *,
    markets: Iterable[str] = DEFAULT_MARKETS,
    exclude_industries: Iterable[str] = ("ETF", "ETN"),
) -> pd.DataFrame:
    """Normalize FinMind TaiwanStockInfo into the active factor-research universe.

    FinMind defines ``date`` as the stock-info update date. When multiple snapshots
    are returned, only the latest global snapshot is retained so delisted/stale rows
    do not leak into the current research universe.

    Common stocks are then kept conservatively as four-digit numeric IDs starting
    with 1-9. This excludes ETF-style 00xx identifiers and most non-common securities.
    """
    required = {"stock_id", "stock_name", "industry_category", "type"}
    missing = required - set(frame.columns)
    if missing:
        raise KeyError(f"TaiwanStockInfo missing columns: {sorted(missing)}")

    work = frame.copy()
    if "date" in work.columns:
        parsed_dates = pd.to_datetime(work["date"], errors="coerce")
        if parsed_dates.notna().any():
            latest_date = parsed_dates.max()
            work = work.loc[parsed_dates == latest_date].copy()

    work["stock_id"] = work["stock_id"].astype(str).str.strip()
    work["type"] = work["type"].astype(str).str.lower().str.strip()
    work["industry_category"] = work["industry_category"].fillna("Unknown").astype(str).str.strip()
    work["stock_name"] = work["stock_name"].fillna(work["stock_id"]).astype(str).str.strip()

    market_set = {str(value).lower() for value in markets}
    excluded = {str(value) for value in exclude_industries}
    work = work[
        work["type"].isin(market_set)
        & work["stock_id"].str.fullmatch(r"[1-9]\d{3}")
        & ~work["industry_category"].isin(excluded)
    ].copy()
    work = work.drop_duplicates("stock_id", keep="last")

    work["name"] = work["stock_name"]
    work["market"] = work["type"]
    work["sector"] = work["industry_category"]
    work["industry"] = work["industry_category"]
    work["ticker"] = work.apply(
        lambda row: f"{row['stock_id']}.TW" if row["market"] == "twse" else f"{row['stock_id']}.TWO",
        axis=1,
    )
    if "date" in work.columns:
        work["universe_source_date"] = work["date"].astype(str)
    else:
        work["universe_source_date"] = ""
    work["universe_source"] = "FinMind: TaiwanStockInfo"

    columns = [
        "stock_id",
        "ticker",
        "name",
        "market",
        "sector",
        "industry",
        "universe_source_date",
        "universe_source",
    ]
    return work[columns].sort_values("stock_id").reset_index(drop=True)


def select_research_sample(
    universe: pd.DataFrame,
    *,
    industries: int = 6,
    per_industry: int = 2,
) -> pd.DataFrame:
    """Select a deterministic multi-industry sample for CI/research smoke tests.

    The largest industries are chosen first, then the lowest stock IDs inside each
    industry. At least two names per industry makes industry-neutral residuals
    meaningful in validation smoke tests.
    """
    if industries < 1 or per_industry < 1:
        raise ValueError("industries and per_industry must be >= 1")
    if "industry" not in universe.columns:
        raise KeyError("industry")

    counts = (
        universe.groupby("industry", dropna=False)["stock_id"]
        .count()
        .sort_values(ascending=False)
    )
    chosen_industries = counts.head(industries).index.tolist()
    pieces = []
    for industry in chosen_industries:
        group = universe[universe["industry"] == industry].sort_values("stock_id")
        pieces.append(group.head(per_industry))
    if not pieces:
        return universe.iloc[0:0].copy()
    return pd.concat(pieces, ignore_index=True).sort_values(["industry", "stock_id"]).reset_index(drop=True)


def slice_batch(universe: pd.DataFrame, batch_size: int, batch_index: int) -> pd.DataFrame:
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")
    if batch_index < 0:
        raise ValueError("batch_index must be >= 0")
    start = batch_index * batch_size
    return universe.iloc[start : start + batch_size].copy().reset_index(drop=True)


def merge_factor_batches(frames: Iterable[pd.DataFrame]) -> pd.DataFrame:
    parts = [frame.copy() for frame in frames if frame is not None and not frame.empty]
    if not parts:
        return pd.DataFrame()
    merged = pd.concat(parts, ignore_index=True, sort=False)
    keys = [column for column in ("stock_id", "report_date") if column in merged.columns]
    if len(keys) != 2:
        raise KeyError("Factor batch requires stock_id and report_date")
    merged = merged.drop_duplicates(keys, keep="last")
    sort_columns = [column for column in ("ticker", "stock_id", "report_date") if column in merged.columns]
    return merged.sort_values(sort_columns).reset_index(drop=True)


def read_and_merge_factor_batches(paths: Iterable[str | Path]) -> pd.DataFrame:
    frames = [pd.read_csv(Path(path)) for path in paths]
    return merge_factor_batches(frames)
