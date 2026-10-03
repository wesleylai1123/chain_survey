from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT=Path(__file__).resolve().parents[1]


def validate_live_evidence() -> list[dict]:
    status=json.loads((ROOT/"artifacts/free_evidence_collection_status.json").read_text(encoding="utf-8"))
    evidence=pd.read_csv(ROOT/"artifacts/free_evidence_latest.csv")
    sources_ok=int(status.get("sources_ok",0))
    sources_stale=int(status.get("sources_stale",0))
    sources_usable=int(status.get("sources_usable",sources_ok+sources_stale))
    retrieval=set(evidence.get("retrieval_status",pd.Series(dtype=str)).dropna().astype(str))
    stale_status=[s for s in status.get("sources",[]) if s.get("status")=="stale_fallback"]
    stale_within_limit=all(
        float(s.get("stale_age_hours",1e99)) <= float(s.get("max_stale_hours",-1))
        for s in stale_status
    )
    checks=[
        {"name":"live_sources_minimum","passed":sources_usable>=4,"severity":"FAIL","detail":f"usable={sources_usable}/{status['sources_total']} fresh={sources_ok} stale={sources_stale}"},
        {"name":"live_fresh_sources_reasonable","passed":sources_ok>=4,"severity":"DEGRADED","detail":f"fresh={sources_ok}/{status['sources_total']} stale={sources_stale}"},
        {"name":"live_stale_within_limit","passed":stale_within_limit,"severity":"FAIL","detail":f"stale_sources={len(stale_status)}"},
        {"name":"live_evidence_nonempty","passed":len(evidence)>=1,"severity":"FAIL","detail":str(len(evidence))},
        {"name":"live_pit_policy","passed":set(evidence["availability_policy"])=={"collection_time_conservative"},"severity":"FAIL","detail":"collection_time_conservative"},
        {"name":"live_raw_trace","passed":evidence["raw_sha256"].astype(str).str.len().eq(64).all(),"severity":"FAIL","detail":"raw sha256 required"},
        {"name":"live_run_trace","passed":evidence["pipeline_run_id"].astype(str).str.len().gt(0).all(),"severity":"FAIL","detail":"pipeline_run_id required"},
        {"name":"live_retrieval_status","passed":bool(retrieval) and retrieval.issubset({"FRESH","STALE_FALLBACK"}),"severity":"FAIL","detail":" | ".join(sorted(retrieval))},
        {"name":"live_reliability_prior","passed":set(evidence["reliability_basis"])=={"SOURCE_CLASS_PRIOR"},"severity":"FAIL","detail":"prior only"},
    ]
    return checks


def validate_abf() -> list[dict]:
    h=pd.read_csv(ROOT/"artifacts/abf_source_health.csv",dtype={"stock_id":str})
    s=pd.read_csv(ROOT/"artifacts/abf_document_extract_status.csv",dtype={"stock_id":str})
    c=pd.read_csv(ROOT/"artifacts/abf_operating_candidates.csv",dtype={"stock_id":str})
    company_ok=all(h[(h["stock_id"]==stock)&h["healthy"].fillna(False)].shape[0]>=1 for stock in ("3037","3189","8046"))
    ok_docs=s[s["status"]=="OK"]
    checks=[
        {"name":"abf_each_company_has_healthy_source","passed":company_ok,"severity":"FAIL","detail":"3037/3189/8046"},
        {"name":"abf_documents_processed","passed":len(ok_docs)>=1,"severity":"FAIL","detail":str(len(ok_docs))},
        {"name":"abf_document_sha_trace","passed":ok_docs["sha256"].astype(str).str.len().eq(64).all(),"severity":"FAIL","detail":"raw sha required"},
        {"name":"abf_candidate_review_gate","passed":c.empty or set(c["review_status"])=={"CANDIDATE"},"severity":"FAIL","detail":"no auto-promotion"},
        {"name":"abf_raw_trace","passed":c.empty or c["raw_sha256"].astype(str).str.len().eq(64).all(),"severity":"FAIL","detail":"candidate raw sha required"},
        {"name":"abf_run_trace","passed":c.empty or c["pipeline_run_id"].astype(str).str.len().gt(0).all(),"severity":"FAIL","detail":"pipeline run required"},
    ]
    failed_docs=s[s["status"]!="OK"]
    checks.append({
        "name":"abf_document_failure_rate",
        "passed":len(failed_docs)/max(len(s),1)<=0.35,
        "severity":"DEGRADED",
        "detail":f"{len(failed_docs)}/{len(s)}"
    })
    return checks



def validate_history() -> list[dict]:
    panel=pd.read_csv(ROOT/"data/history/free_industry_history_panel.csv")
    coverage=pd.read_csv(ROOT/"data/history/free_industry_history_coverage.csv")
    published=pd.to_datetime(panel["published_at"],utc=True,errors="coerce")
    periods=pd.to_datetime(panel["period_date"],utc=True,errors="coerce")
    mops=panel[panel["source_id"]=="mops_abf_monthly_revenue"]
    tpca=panel[panel["source_id"]=="tpca_public_industry"]
    tf=panel[panel["source_id"]=="trendforce_public_dram"]
    return [
        {"name":"history_multiple_sources","passed":panel["source_id"].nunique()>=3,"severity":"FAIL","detail":str(panel["source_id"].nunique())},
        {"name":"history_abf_three_companies","passed":mops["entity"].nunique()==3,"severity":"FAIL","detail":str(mops["entity"].nunique())},
        {"name":"history_abf_min_periods","passed":mops["period"].nunique()>=18,"severity":"FAIL","detail":str(mops["period"].nunique())},
        {"name":"history_tpca_min_periods","passed":tpca["period"].nunique()>=6,"severity":"FAIL","detail":str(tpca["period"].nunique())},
        {"name":"history_trendforce_nonempty","passed":len(tf)>=1,"severity":"DEGRADED","detail":str(len(tf))},
        {"name":"history_no_future_leakage","passed":published.notna().all() and periods.notna().all() and (published>=periods).all(),"severity":"FAIL","detail":"published_at >= period_date"},
        {"name":"history_coverage_nonempty","passed":len(coverage)>=1,"severity":"FAIL","detail":str(len(coverage))},
    ]


def _normalize_checks(checks: list[dict]) -> list[dict]:
    normalized=[]
    for check in checks:
        item=dict(check)
        item["passed"]=bool(item.get("passed",False))
        item["severity"]=str(item.get("severity","FAIL"))
        item["name"]=str(item.get("name",""))
        item["detail"]=str(item.get("detail",""))
        normalized.append(item)
    return normalized


def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument("--pipeline",choices=["live","abf","history"],required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    checks=_normalize_checks(validate_live_evidence() if args.pipeline=="live" else (validate_abf() if args.pipeline=="abf" else validate_history()))
    payload={
        "pipeline":args.pipeline,
        "validated_at":pd.Timestamp.now(tz="UTC").isoformat(),
        "status":"FAIL" if any((not c["passed"]) and c["severity"]=="FAIL" for c in checks) else ("DEGRADED" if any(not c["passed"] for c in checks) else "PASS"),
        "checks":checks,
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"PIPELINE_VALIDATION_{payload['status']} pipeline={args.pipeline}")
    for check in checks:
        print(check)
    if payload["status"]=="FAIL":
        raise SystemExit(2)


if __name__=="__main__":
    main()
