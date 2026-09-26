from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from core.abf_operating_observations import verified_operating_observations

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_REQUIREMENTS=ROOT/"data"/"abf_data_requirements.json"
ABF_STOCK_IDS=("3037","3189","8046")


def load_requirements(path: str | Path=DEFAULT_REQUIREMENTS) -> dict[str,Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _factor_status(panel: pd.DataFrame, columns: list[str], min_rows: int) -> tuple[str,str]:
    if panel.empty:
        return "NOT_CONNECTED","factor-data is not restored into the ABF workflow"
    missing=[c for c in columns if c not in panel.columns]
    if missing:
        return "MISSING",f"factor-data missing columns: {', '.join(missing)}"
    if "ticker" in panel:
        work=panel.copy()
        work["_stock_id"]=work["ticker"].astype(str).str.extract(r"(\d{4})",expand=False)
        abf=work[work["_stock_id"].isin(ABF_STOCK_IDS)].copy()
    elif "stock_id" in panel:
        work=panel.copy()
        work["_stock_id"]=work["stock_id"].astype(str).str.extract(r"(\d{4})",expand=False)
        abf=work[work["_stock_id"].isin(ABF_STOCK_IDS)].copy()
    else:
        abf=pd.DataFrame()
    if abf.empty:
        return "MISSING","factor-data has no ABF company rows"
    counts={}
    for stock_id in ABF_STOCK_IDS:
        rows=abf[abf["_stock_id"]==stock_id]
        usable=rows[columns].notna().all(axis=1).sum()
        counts[stock_id]=int(usable)
    if min(counts.values()) < min_rows:
        return "INSUFFICIENT_HISTORY","usable rows per company: "+", ".join(f"{k}={v}" for k,v in counts.items())
    return "AVAILABLE","usable rows per company: "+", ".join(f"{k}={v}" for k,v in counts.items())


def audit_abf_data_coverage(
    history: pd.DataFrame,
    factor_panel: pd.DataFrame | None=None,
    *,
    requirements_path: str | Path=DEFAULT_REQUIREMENTS,
    operating_observations: pd.DataFrame | None=None,
) -> pd.DataFrame:
    spec=load_requirements(requirements_path)
    factor=pd.DataFrame() if factor_panel is None else factor_panel.copy()
    external_ids={r["data_id"] for r in spec["requirements"] if r["kind"]=="missing_external"}
    observed=verified_operating_observations(
        pd.DataFrame() if operating_observations is None else operating_observations, external_ids,
    )
    rows=[]

    metric_counts={}
    if not history.empty and {"metric_id"}.issubset(history.columns):
        metric_counts=history.groupby("metric_id").size().to_dict()

    for req in spec["requirements"]:
        kind=req["kind"]
        status="MISSING"
        detail=""
        source=""

        if kind=="evidence_metric":
            n=int(metric_counts.get(req["metric_id"],0))
            status="AVAILABLE" if n>=int(req.get("minimum_observations",1)) else ("INSUFFICIENT_HISTORY" if n else "MISSING")
            detail=f"{n} observations"
            source="evidence-data / TPCA public history"
        elif kind=="evidence_metric_pair":
            counts=[int(metric_counts.get(mid,0)) for mid in req["metric_ids"]]
            minimum=int(req.get("minimum_observations",1))
            status="AVAILABLE" if counts and min(counts)>=minimum else ("INSUFFICIENT_HISTORY" if max(counts or [0]) else "MISSING")
            detail=", ".join(f"{mid}={n}" for mid,n in zip(req["metric_ids"],counts))
            source="evidence-data / TPCA public history"
        elif kind=="evidence_company_metrics":
            prefix=req["metric_prefix"]
            found={mid:int(n) for mid,n in metric_counts.items() if str(mid).startswith(prefix)}
            minimum=int(req.get("minimum_observations",1))
            status="AVAILABLE" if len(found)>=3 and min(found.values())>=minimum else ("INSUFFICIENT_HISTORY" if found else "MISSING")
            detail=", ".join(f"{k.split('::')[-1]}={v}" for k,v in sorted(found.items()))
            source="evidence-data / MOPS-derived monthly revenue"
        elif kind=="factor_columns":
            status,detail=_factor_status(factor,list(req["columns"]),int(req.get("minimum_rows_per_company",1)))
            source="factor-data / FinMind financial statements"
        elif kind=="factor_availability_exact":
            if factor.empty or "availability_method" not in factor.columns:
                status="NOT_CONNECTED"
                detail="factor-data not connected"
            else:
                abf=factor[factor.get("stock_id",factor.get("ticker",pd.Series(index=factor.index,dtype=str))).astype(str).str.contains(r"3037|3189|8046")]
                methods=sorted(set(abf["availability_method"].dropna().astype(str)))
                exact=abf["availability_method"].eq("official_filing_timestamp_next_day")
                sourced=(abf["filing_source_url"].notna() & abf["filing_published_at"].notna()) if {"filing_source_url","filing_published_at"} <= set(abf.columns) else pd.Series(False,index=abf.index)
                if methods and (not exact.all() or not sourced.all()):
                    status="PROXY"
                    detail=f"verified={int((exact & sourced).sum())}/{len(abf)} rows; " + "; ".join(methods)
                elif methods and len(abf):
                    status="AVAILABLE"
                    detail=f"verified={len(abf)}/{len(abf)} rows; " + "; ".join(methods)
                else:
                    status="MISSING"
                    detail="no availability method"
            source="factor-data"
        elif kind=="missing_external":
            subset=observed[observed["data_id"]==req["data_id"]] if not observed.empty else observed
            n=len(subset)
            status="INSUFFICIENT_HISTORY" if n else "MISSING"
            detail=f"{n} source-backed observations; historical validation pending" if n else "No historical dataset currently connected"
            source="ABF operating observations" if n else "not connected"
        else:
            raise ValueError(f"Unsupported requirement kind: {kind}")

        rows.append({
            "data_id":req["data_id"],
            "layer":req["layer"],
            "label":req["label"],
            "importance":req.get("importance",""),
            "status":status,
            "detail":detail,
            "source":source,
        })
    return pd.DataFrame(rows)
