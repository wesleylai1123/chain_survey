from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_CATALOG=ROOT/"data"/"abf_indicator_timing_catalog.json"
VALID_CLASSES={"LEADING","COINCIDENT","LAGGING"}
VALID_ORIENTATIONS={"HIGHER_IS_BETTER","LOWER_IS_BETTER"}


def load_indicator_catalog(path: str | Path=DEFAULT_CATALOG) -> dict[str,Any]:
    payload=json.loads(Path(path).read_text(encoding="utf-8"))
    indicators=payload.get("indicators",[])
    ids=set()
    for item in indicators:
        iid=str(item["indicator_id"])
        if iid in ids:
            raise ValueError(f"Duplicate indicator_id: {iid}")
        ids.add(iid)
        if item.get("timing_class") not in VALID_CLASSES:
            raise ValueError(f"Invalid timing_class for {iid}: {item.get('timing_class')}")
        if not item.get("relative_to"):
            raise ValueError(f"Indicator {iid} must declare relative_to")
        if item.get("economic_orientation") not in VALID_ORIENTATIONS:
            raise ValueError(f"Indicator {iid} must declare economic_orientation")
    return payload


def indicator_table(path: str | Path=DEFAULT_CATALOG) -> pd.DataFrame:
    payload=load_indicator_catalog(path)
    rows=[]
    for item in payload["indicators"]:
        lag=item.get("lead_lag") or {}
        rows.append({
            "indicator_id":item["indicator_id"],
            "name":item["name"],
            "timing_class":item["timing_class"],
            "relative_to":item["relative_to"],
            "lag_value":lag.get("value"),
            "lag_unit":lag.get("unit"),
            "evidence_status":item.get("evidence_status",""),
            "economic_orientation":item.get("economic_orientation",""),
            "positive_case":item.get("positive_case",""),
            "negative_case":item.get("negative_case",""),
            "role":item.get("role",""),
            "use_in_model":item.get("use_in_model",""),
            "note":item.get("note",""),
        })
    return pd.DataFrame(rows)


def classify_indicator(indicator_id: str, path: str | Path=DEFAULT_CATALOG) -> dict[str,Any]:
    payload=load_indicator_catalog(path)
    for item in payload["indicators"]:
        if item["indicator_id"]==indicator_id:
            return item
    raise KeyError(indicator_id)
