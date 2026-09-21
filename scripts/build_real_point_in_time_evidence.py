from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW = ROOT / "data" / "point_in_time_evidence_raw.csv"
DEFAULT_OUTPUT = ROOT / "data" / "evidence_observations_real.csv"

REQUIRED = {
    "evidence_id", "theme", "dimension", "chain", "evidence_group", "indicator",
    "period_date", "published_at", "raw_value", "raw_unit", "yoy_pct",
    "source_type", "source",
}


def normalize_yoy_to_signal(yoy_pct: float) -> float:
    """Map YoY percentage change to [-1, 1] transparently.

    v1 deliberately avoids learned weights: +100% YoY => +1.0, -100% => -1.0,
    with clipping beyond those bounds. This transform is versioned in output so
    historical backtests can be reproduced when calibration changes later.
    """
    return max(-1.0, min(1.0, float(yoy_pct) / 100.0))


def build_real_evidence(raw: pd.DataFrame) -> pd.DataFrame:
    missing = REQUIRED - set(raw.columns)
    if missing:
        raise ValueError(f"Missing raw evidence columns: {sorted(missing)}")
    frame = raw.copy()
    frame["period_date"] = pd.to_datetime(frame["period_date"], errors="raise")
    frame["published_at"] = pd.to_datetime(frame["published_at"], errors="raise", utc=True, format="mixed")
    frame["raw_value"] = pd.to_numeric(frame["raw_value"], errors="raise")
    frame["yoy_pct"] = pd.to_numeric(frame["yoy_pct"], errors="raise")
    frame["signal"] = frame["yoy_pct"].map(normalize_yoy_to_signal)
    frame["as_of_date"] = frame["published_at"]
    frame["transform"] = "clip(yoy_pct / 100, -1, 1)"
    frame["transform_version"] = "yoy_linear_v1"
    frame["provenance"] = "REAL_POINT_IN_TIME"
    frame["collected_at"] = pd.Timestamp.now(tz="UTC")

    output_columns = [
        "evidence_id", "theme", "dimension", "chain", "evidence_group", "indicator",
        "period_date", "published_at", "as_of_date", "raw_value", "raw_unit", "yoy_pct",
        "signal", "source_type", "reliability", "half_life_days", "source", "notes",
        "transform", "transform_version", "provenance", "collected_at",
    ]
    return frame[output_columns].sort_values(["published_at", "evidence_id"]).reset_index(drop=True)


def build_files(raw_path: Path = DEFAULT_RAW, output_path: Path = DEFAULT_OUTPUT) -> pd.DataFrame:
    raw = pd.read_csv(raw_path)
    result = build_real_evidence(raw)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_path, index=False)
    return result


if __name__ == "__main__":
    frame = build_files()
    print(f"REAL_POINT_IN_TIME_EVIDENCE_OK rows={len(frame)}")
