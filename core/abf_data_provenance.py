from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
SOURCE_MAP=ROOT/"data"/"abf_data_source_map.csv"

HISTORY_METRICS={
    "pcb_revenue_yoy":["pcb_revenue_yoy"],
    "rigid_pcb_export_yoy":["rigid_pcb_export_yoy"],
    "pcb_material_revenue_yoy":["pcb_material_revenue_yoy"],
    "ccl_import_export":["ccl_import_yoy","ccl_export_yoy"],
}

REGULATOR_TOKENS=("TWSE","MOPS")
PAID_TOKENS=("TEJ","Bloomberg","FactSet","LSEG")


def _source_class(best_source: str, directness: str) -> str:
    source=str(best_source)
    direct=str(directness).upper()
    if any(x in source for x in PAID_TOKENS):
        return "PAID_PIT_VENDOR"
    if any(x in source for x in REGULATOR_TOKENS):
        return "REGULATOR_OFFICIAL"
    if "tpca" in source.lower():
        return "INDUSTRY_ASSOCIATION"
    if "moea" in source.lower() or "World Bank" in source or "FRED" in source:
        return "OFFICIAL_MACRO"
    if "ajinomoto" in source.lower():
        return "SUPPLIER_PRIMARY"
    if any(x in source.lower() for x in ("company","investor","annual report","webpro","nypcb","kinsus")):
        return "COMPANY_PRIMARY"
    return "MAPPED_SOURCE"


def _eligibility(status: str, directness: str, data_form: str) -> str:
    direct=str(directness).upper()
    form=str(data_form).lower()
    if "PAID" in direct:
        return "PAID_SOURCE_REQUIRED"
    if "PROXY" in direct or direct in {"PARTIAL","MACRO_PROXY","COMPANY_EXPECTATION_PROXY"}:
        return "SUPPORT_ONLY"
    if "event" in form or "EVENT" in direct:
        return "EVENT_STUDY_ONLY"
    if status=="AVAILABLE" and direct=="DIRECT":
        return "CALIBRATION_ELIGIBLE"
    if status in {"MISSING","NOT_CONNECTED","INSUFFICIENT_HISTORY"}:
        return "NOT_YET_ELIGIBLE"
    return "VALIDATE_BEFORE_USE"


def _period_summary(values: pd.Series, frequency: str) -> tuple[int,str,str,int,str]:
    parsed=pd.to_datetime(values,errors="coerce").dropna().sort_values().drop_duplicates()
    if parsed.empty:
        return 0,"","",0,"MISSING"
    first,last=parsed.iloc[0],parsed.iloc[-1]
    n=len(parsed)
    if frequency=="monthly":
        expected=len(pd.period_range(first.to_period("M"),last.to_period("M"),freq="M"))
    elif frequency=="quarterly":
        expected=len(pd.period_range(first.to_period("Q"),last.to_period("Q"),freq="Q"))
    else:
        return n,str(first.date()),str(last.date()),0,"EVENT_OR_IRREGULAR"
    gaps=max(0,expected-n)
    ratio=n/expected if expected else 0
    continuity="CONTINUOUS" if gaps==0 else ("MOSTLY_CONTINUOUS" if ratio>=0.85 else "GAPPY")
    return n,str(first.date()),str(last.date()),gaps,continuity


def _actual_for_requirement(
    data_id: str,
    data_form: str,
    history: pd.DataFrame,
    factor: pd.DataFrame,
    operating: pd.DataFrame,
) -> dict:
    result={
        "observation_count":0,"first_period":"","last_period":"","gap_count":0,
        "continuity":"MISSING","actual_source_count":0,"actual_source_hosts":"",
        "actual_source_urls":"","knowledge_time_method":"",
    }
    form=str(data_form).lower()
    frequency="monthly" if "monthly" in form else ("quarterly" if "quarterly" in form else "event")

    if data_id in HISTORY_METRICS and not history.empty and "metric_id" in history:
        subset=history[history["metric_id"].isin(HISTORY_METRICS[data_id])].copy()
        date_col="period_date" if "period_date" in subset else ("period" if "period" in subset else None)
        if date_col:
            n,first,last,gaps,continuity=_period_summary(subset[date_col],frequency)
            result.update(observation_count=n,first_period=first,last_period=last,gap_count=gaps,continuity=continuity)
        if "source_url" in subset:
            urls=sorted(set(subset["source_url"].dropna().astype(str)))
            result["actual_source_count"]=len(urls)
            result["actual_source_urls"]=" | ".join(urls[:6])
            result["actual_source_hosts"]=", ".join(sorted({urlparse(u).hostname or "" for u in urls if u}))
        if "knowledge_time_method" in subset:
            result["knowledge_time_method"]=", ".join(sorted(set(subset["knowledge_time_method"].dropna().astype(str))))
        return result

    if data_id=="company_monthly_revenue" and not history.empty and "metric_id" in history:
        subset=history[history["metric_id"].astype(str).str.startswith("abf_company_revenue_yoy::")].copy()
        date_col="period_date" if "period_date" in subset else ("period" if "period" in subset else None)
        if date_col:
            # count unique company-period observations, while gap status is based on unique months.
            result["observation_count"]=len(subset)
            _,first,last,gaps,continuity=_period_summary(subset[date_col],"monthly")
            result.update(first_period=first,last_period=last,gap_count=gaps,continuity=continuity)
        if "source_url" in subset:
            urls=sorted(set(subset["source_url"].dropna().astype(str)))
            result["actual_source_count"]=len(urls)
            result["actual_source_urls"]=" | ".join(urls[:6])
            result["actual_source_hosts"]=", ".join(sorted({urlparse(u).hostname or "" for u in urls if u}))
        if "knowledge_time_method" in subset:
            result["knowledge_time_method"]=", ".join(sorted(set(subset["knowledge_time_method"].dropna().astype(str))))
        return result

    if data_id in {"quarterly_margin_history","company_inventory_history","quarterly_exact_filing_time"} and not factor.empty:
        subset=factor.copy()
        date_col="report_date" if "report_date" in subset else None
        if date_col:
            result["observation_count"]=len(subset)
            _,first,last,gaps,continuity=_period_summary(subset[date_col],"quarterly")
            result.update(first_period=first,last_period=last,gap_count=gaps,continuity=continuity)
        if data_id=="quarterly_exact_filing_time" and "filing_source_url" in subset:
            urls=sorted(set(subset["filing_source_url"].dropna().astype(str)))
            result["actual_source_count"]=len(urls)
            result["actual_source_urls"]=" | ".join(urls[:6])
            result["actual_source_hosts"]=", ".join(sorted({urlparse(u).hostname or "" for u in urls if u}))
        if "availability_method" in subset:
            result["knowledge_time_method"]=", ".join(sorted(set(subset["availability_method"].dropna().astype(str))))
        return result

    if not operating.empty and "data_id" in operating:
        subset=operating[operating["data_id"]==data_id].copy()
        result["observation_count"]=len(subset)
        if len(subset):
            n,first,last,gaps,continuity=_period_summary(subset["period_end"],frequency)
            result.update(first_period=first,last_period=last,gap_count=gaps,continuity=continuity)
            if frequency=="event":
                result["continuity"]="EVENT_OR_IRREGULAR"
            urls=sorted(set(subset["source_url"].dropna().astype(str))) if "source_url" in subset else []
            result["actual_source_count"]=len(urls)
            result["actual_source_urls"]=" | ".join(urls[:6])
            result["actual_source_hosts"]=", ".join(sorted({urlparse(u).hostname or "" for u in urls if u}))
            if "publication_precision" in subset:
                result["knowledge_time_method"]=", ".join(sorted(set(subset["publication_precision"].dropna().astype(str))))
        return result

    return result


def build_abf_data_provenance(
    coverage: pd.DataFrame,
    history: pd.DataFrame | None=None,
    factor: pd.DataFrame | None=None,
    operating: pd.DataFrame | None=None,
    *,
    source_map_path: str | Path=SOURCE_MAP,
) -> pd.DataFrame:
    source_map=pd.read_csv(source_map_path,dtype=str).fillna("")
    coverage=coverage.copy()
    history=pd.DataFrame() if history is None else history.copy()
    factor=pd.DataFrame() if factor is None else factor.copy()
    operating=pd.DataFrame() if operating is None else operating.copy()

    rows=[]
    cov_by=coverage.set_index("data_id",drop=False) if not coverage.empty else pd.DataFrame()
    for _,m in source_map.iterrows():
        data_id=m["data_id"]
        cov=cov_by.loc[data_id] if not coverage.empty and data_id in cov_by.index else None
        status=str(cov["status"]) if cov is not None else str(m.get("current_status","MISSING"))
        actual=_actual_for_requirement(data_id,m.get("data_form",""),history,factor,operating)
        source_class=_source_class(m.get("best_source",""),m.get("directness",""))
        rows.append({
            "data_id":data_id,
            "need_level":m.get("need_level",""),
            "model_role":m.get("model_role",""),
            "status":status,
            "source_class":source_class,
            "directness":m.get("directness",""),
            "model_eligibility":_eligibility(status,m.get("directness",""),m.get("data_form","")),
            "best_source":m.get("best_source",""),
            "alternate_source":m.get("alternate_source",""),
            "acquisition_method":m.get("collection_action",""),
            **actual,
        })
    return pd.DataFrame(rows)
