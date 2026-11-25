from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd

from core.correlation_engine import METHODS, _safe_corr
from core.operating_correlation_engine import _prepare


METRICS = {
    "pcb_revenue_yoy": "上市櫃 PCB 營收年增率",
    "pcb_material_revenue_yoy": "PCB 材料營收年增率",
    "rigid_pcb_export_yoy": "硬板出口年增率",
    "ccl_export_yoy": "CCL 出口年增率",
    "ccl_import_yoy": "CCL 進口年增率",
    "abf_company_revenue_yoy::3037.TW": "欣興 3037 · 營收年增率",
    "abf_company_revenue_yoy::3189.TW": "景碩 3189 · 營收年增率",
    "abf_company_revenue_yoy::8046.TW": "南電 8046 · 營收年增率",
}
LAGS = tuple(range(-3, 7))
MIN_SAMPLES = 8
ROLLING_WINDOW = 12
SOURCE_FIELDS = ("source", "source_url", "knowledge_time_method")
REQUIRED = {"metric_id", "period", "published_at", "change_pct", *SOURCE_FIELDS}
OBSERVED_TIME_METHODS = {"page_publication_date", "actual_release_time", "actual_publication_time"}


def metric_label(metric: str) -> str:
    return METRICS.get(metric, metric)


def _coefficient(pair: pd.DataFrame, method: str, minimum: int) -> float | None:
    if len(pair) < minimum:
        return None
    value = _safe_corr(pair, method)
    return value if np.isfinite(value) else None


def _uses_proxy(pair: pd.DataFrame) -> bool:
    return any(~pair[f"{side}_knowledge_time_method"].isin(OBSERVED_TIME_METHODS).all()
               for side in ("feature", "target"))


@dataclass
class PairReport:
    samples: pd.DataFrame
    coefficient: float | None
    earlier: float | None
    later: float | None
    rolling: pd.Series

    @property
    def uses_proxy(self) -> bool:
        return _uses_proxy(self.samples)


class ResearchDataset:
    @classmethod
    def from_csv(cls, source, label: str = "匯入資料") -> ResearchDataset:
        return cls(pd.read_csv(source, dtype={"metric_id": "string"}), label)

    def __init__(self, raw: pd.DataFrame, label: str = "匯入資料") -> None:
        missing = sorted(REQUIRED - set(raw.columns))
        if missing:
            raise ValueError("缺少欄位：" + "、".join(missing))
        # Keep monthly YoY series distinct from daily quotes and price snapshots.
        monthly = raw.loc[raw["period"].astype(str).str.fullmatch(r"\d{4}-(0[1-9]|1[0-2])")].copy()
        for column in ("metric_id", "published_at", *SOURCE_FIELDS):
            values = monthly[column].astype("string").str.strip()
            if (values.isna() | values.eq("")).any():
                raise ValueError(f"月度資料缺少識別或來源欄位內容：{column}")
            monthly[column] = values
        frame = _prepare(monthly)
        month_end = frame["period_m"].dt.to_timestamp("M").dt.tz_localize("Asia/Taipei").dt.tz_convert("UTC")
        if frame["published_at"].isna().any() or (frame["published_at"] < month_end).any():
            raise ValueError("月度資料的可用時間不得早於月底。")
        if frame.duplicated(["metric_id", "period_m"]).any():
            raise ValueError("同一指標的月份重複。")
        frame = frame.loc[np.isfinite(frame["change_pct"]) & frame["published_at"].notna()]
        if frame["metric_id"].nunique() < 2:
            raise ValueError("至少需要兩個有發布日期的月度指標。")
        self.label = label
        self.frame = frame
        self.metrics = tuple(dict.fromkeys(frame["metric_id"]))
        self.first_month = str(frame["period_m"].min())
        self.last_month = str(frame["period_m"].max())

    def align(self, feature: str, target: str, lag: int) -> pd.DataFrame:
        if feature == target or feature not in self.metrics or target not in self.metrics:
            raise ValueError("請選擇兩個不同的指標。")
        columns = ["period_m", "published_at", "change_pct", *SOURCE_FIELDS]
        x = self.frame.loc[self.frame["metric_id"] == feature, columns].rename(columns={
            "published_at": "feature_published_at", "change_pct": "x",
            **{field: f"feature_{field}" for field in SOURCE_FIELDS},
        })
        y = self.frame.loc[self.frame["metric_id"] == target, columns].rename(columns={
            "period_m": "target_period", "published_at": "target_published_at", "change_pct": "y",
            **{field: f"target_{field}" for field in SOURCE_FIELDS},
        })
        x["target_period"] = x["period_m"] + lag
        pairs = x.merge(y, on="target_period", validate="one_to_one")
        return pairs.loc[pairs["feature_published_at"] <= pairs["target_published_at"]].sort_values(
            "period_m"
        ).reset_index(drop=True)

    def analyze(self, feature: str, target: str, lag: int, method: str) -> PairReport:
        if method not in METHODS:
            raise ValueError("不支援此相關方法。")
        pair = self.align(feature, target, lag)
        split = len(pair) // 2
        rolling = pd.Series(
            [_coefficient(pair.iloc[max(0, i + 1 - ROLLING_WINDOW):i + 1], method, ROLLING_WINDOW)
             for i in range(len(pair))], dtype=float, index=pair["target_period"],
        )
        return PairReport(pair, _coefficient(pair, method, MIN_SAMPLES),
                          _coefficient(pair.iloc[:split], method, MIN_SAMPLES),
                          _coefficient(pair.iloc[split:], method, MIN_SAMPLES), rolling)

    def scan(self, target: str, method: str, features: tuple[str, ...] | None = None) -> list[tuple]:
        rows = []
        for feature in features if features is not None else self.metrics:
            if feature == target:
                continue
            for lag in LAGS:
                pair = self.align(feature, target, lag)
                value = _coefficient(pair, method, MIN_SAMPLES)
                rows.append((feature, lag, value, len(pair), _uses_proxy(pair)))
        return rows


def load_default_dataset(root: Path) -> ResearchDataset:
    path = Path("data/history/free_industry_history_panel.csv")
    if (root / path).is_file():
        return ResearchDataset.from_csv(root / path, "本機歷史資料")
    try:
        def read_object(ref):
            return subprocess.run(
                ["git", "show", f"{ref}:{path.as_posix()}"], cwd=root, capture_output=True,
                check=True, timeout=5,
            ).stdout

        try:
            content = read_object("origin/evidence-data")
        except subprocess.CalledProcessError:
            content = read_object("evidence-data")
    except (OSError, subprocess.SubprocessError):
        snapshot = root / "data/research_workspace_snapshot.csv"
        if not snapshot.is_file():
            raise ValueError("目前沒有歷史資料。可匯入月度證據 CSV。") from None
        return ResearchDataset.from_csv(snapshot, "內建歷史快照")
    return ResearchDataset.from_csv(BytesIO(content), "Evidence Data")
