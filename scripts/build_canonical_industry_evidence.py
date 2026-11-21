from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from scripts.build_real_point_in_time_evidence import DEFAULT_RAW, build_real_evidence
from scripts.build_free_industry_evidence import build_free_evidence

OUTPUT = ROOT / "data" / "evidence_observations_canonical.csv"


def build_canonical_evidence() -> pd.DataFrame:
    official = build_real_evidence(pd.read_csv(DEFAULT_RAW)).copy()
    official = official.rename(columns={"yoy_pct": "change_pct"})
    free = build_free_evidence().copy()

    columns = [
        "evidence_id","theme","dimension","chain","evidence_group","indicator",
        "period_date","published_at","as_of_date","raw_value","raw_unit","change_pct",
        "signal","source_type","reliability","half_life_days","source",
        "transform","transform_version","provenance","collected_at",
    ]
    for frame in (official, free):
        for col in columns:
            if col not in frame.columns:
                frame[col] = pd.NA

    combined = pd.concat([official[columns], free[columns]], ignore_index=True)
    combined["published_at"] = pd.to_datetime(combined["published_at"], utc=True, format="mixed")
    combined["as_of_date"] = pd.to_datetime(combined["as_of_date"], utc=True, format="mixed")
    combined = combined.sort_values(["published_at","evidence_id"]).drop_duplicates("evidence_id", keep="last")
    return combined.reset_index(drop=True)


def main() -> None:
    frame = build_canonical_evidence()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(OUTPUT, index=False)
    print(
        "CANONICAL_EVIDENCE_OK "
        f"rows={len(frame)} "
        f"chains={','.join(sorted(frame['chain'].dropna().astype(str).unique()))} "
        f"provenance={','.join(sorted(frame['provenance'].dropna().astype(str).unique()))}"
    )


if __name__ == "__main__":
    main()
