from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

ROOT=Path(__file__).resolve().parents[1]


def _check(name: str, passed: bool, severity: str, detail: str) -> dict[str, Any]:
    return {"name":name,"passed":bool(passed),"severity":severity,"detail":str(detail)}


def _status(checks: list[dict[str,Any]]) -> str:
    if any((not c["passed"]) and c["severity"]=="FAIL" for c in checks):
        return "FAIL"
    if any(not c["passed"] for c in checks):
        return "DEGRADED"
    return "PASS"


def _read_csv(path: Path, **kwargs) -> pd.DataFrame:
    return pd.read_csv(path, **kwargs) if path.exists() else pd.DataFrame()


def validate_live(baseline: Path, current_root: Path) -> list[dict[str,Any]]:
    old_status_path=baseline/"free_evidence_collection_status.json"
    old_evidence_path=baseline/"free_evidence_latest.csv"
    new_status_path=current_root/"artifacts"/"free_evidence_collection_status.json"
    new_evidence_path=current_root/"artifacts"/"free_evidence_latest.csv"
    if not old_status_path.exists() or not old_evidence_path.exists():
        return [_check("live_continuity_baseline",True,"INFO","no prior validated live baseline; bootstrap run")]

    old_status=json.loads(old_status_path.read_text(encoding="utf-8"))
    new_status=json.loads(new_status_path.read_text(encoding="utf-8"))
    old=_read_csv(old_evidence_path)
    new=_read_csv(new_evidence_path)

    old_ok={str(x["source_id"]) for x in old_status.get("sources",[]) if x.get("status")=="ok"}
    new_ok={str(x["source_id"]) for x in new_status.get("sources",[]) if x.get("status")=="ok"}
    lost=sorted(old_ok-new_ok)
    ratio=len(new)/max(len(old),1)

    old_dates=old.assign(_published=pd.to_datetime(old["published_at"],utc=True,errors="coerce")).groupby("source_id")["_published"].max() if not old.empty else pd.Series(dtype="datetime64[ns, UTC]")
    new_dates=new.assign(_published=pd.to_datetime(new["published_at"],utc=True,errors="coerce")).groupby("source_id")["_published"].max() if not new.empty else pd.Series(dtype="datetime64[ns, UTC]")
    regress=[]
    for source_id,old_date in old_dates.items():
        new_date=new_dates.get(source_id,pd.NaT)
        if pd.isna(new_date) or (pd.notna(old_date) and new_date < old_date):
            regress.append(str(source_id))

    return [
        _check("live_previously_healthy_sources_present",not lost,"DEGRADED",f"lost={lost or 'none'}"),
        _check("live_row_count_not_collapsed",ratio>=0.5,"FAIL",f"current={len(new)} baseline={len(old)} ratio={ratio:.3f}"),
        _check("live_row_count_reasonable",ratio>=0.8,"DEGRADED",f"current={len(new)} baseline={len(old)} ratio={ratio:.3f}"),
        _check("live_latest_availability_not_regressed",not regress,"FAIL",f"regressed={regress or 'none'}"),
    ]


def validate_abf(baseline: Path, current_root: Path) -> list[dict[str,Any]]:
    old_status=_read_csv(baseline/"abf_document_extract_status.csv",dtype={"stock_id":str})
    old_candidates=_read_csv(baseline/"abf_operating_candidates.csv",dtype={"stock_id":str})
    old_health=_read_csv(baseline/"abf_source_health.csv",dtype={"stock_id":str})
    if old_status.empty and old_candidates.empty and old_health.empty:
        return [_check("abf_continuity_baseline",True,"INFO","no prior validated ABF baseline; bootstrap run")]

    new_status=_read_csv(current_root/"artifacts"/"abf_document_extract_status.csv",dtype={"stock_id":str})
    new_candidates=_read_csv(current_root/"artifacts"/"abf_operating_candidates.csv",dtype={"stock_id":str})
    new_health=_read_csv(current_root/"artifacts"/"abf_source_health.csv",dtype={"stock_id":str})

    old_ok=int((old_status.get("status",pd.Series(dtype=str))=="OK").sum())
    new_ok=int((new_status.get("status",pd.Series(dtype=str))=="OK").sum())
    doc_ratio=new_ok/max(old_ok,1)

    old_healthy=set(old_health.loc[old_health.get("healthy",False).fillna(False),"source_id"].astype(str)) if not old_health.empty else set()
    new_healthy=set(new_health.loc[new_health.get("healthy",False).fillna(False),"source_id"].astype(str)) if not new_health.empty else set()
    lost_sources=sorted(old_healthy-new_healthy)

    old_count=len(old_candidates)
    new_count=len(new_candidates)
    candidate_ratio=new_count/max(old_count,1)

    old_types=set(old_candidates["data_id"].dropna().astype(str)) if "data_id" in old_candidates else set()
    new_types=set(new_candidates["data_id"].dropna().astype(str)) if "data_id" in new_candidates else set()
    lost_types=sorted(old_types-new_types)

    return [
        _check("abf_processed_document_count_not_collapsed",doc_ratio>=0.5,"FAIL",f"current_ok={new_ok} baseline_ok={old_ok} ratio={doc_ratio:.3f}"),
        _check("abf_processed_document_count_reasonable",doc_ratio>=0.8,"DEGRADED",f"current_ok={new_ok} baseline_ok={old_ok} ratio={doc_ratio:.3f}"),
        _check("abf_previously_healthy_sources_present",not lost_sources,"DEGRADED",f"lost={lost_sources or 'none'}"),
        _check("abf_candidate_count_reasonable",candidate_ratio>=0.5,"DEGRADED",f"current={new_count} baseline={old_count} ratio={candidate_ratio:.3f}"),
        _check("abf_candidate_types_preserved",not lost_types,"DEGRADED",f"lost={lost_types or 'none'}"),
    ]


def validate_history(baseline: Path, current_root: Path) -> list[dict[str,Any]]:
    old=_read_csv(baseline/"free_industry_history_panel.csv")
    new=_read_csv(current_root/"data"/"history"/"free_industry_history_panel.csv")
    if old.empty:
        return [_check("history_continuity_baseline",True,"INFO","no prior validated history baseline; bootstrap run")]

    keys=["source_id","metric_id","entity","period"]
    old_keys=set(map(tuple,old[keys].astype(str).itertuples(index=False,name=None)))
    new_keys=set(map(tuple,new[keys].astype(str).itertuples(index=False,name=None)))
    missing=old_keys-new_keys

    regress=[]
    for source_id,group in old.groupby("source_id"):
        old_max=str(group["period"].astype(str).max())
        ng=new[new["source_id"].astype(str)==str(source_id)]
        new_max=str(ng["period"].astype(str).max()) if not ng.empty else ""
        if not new_max or new_max < old_max:
            regress.append(f"{source_id}:{old_max}->{new_max or 'missing'}")

    merged=old.merge(new,on=keys,how="inner",suffixes=("_old","_new"))
    revision_count=0
    if not merged.empty and "value_old" in merged and "value_new" in merged:
        oldv=pd.to_numeric(merged["value_old"],errors="coerce")
        newv=pd.to_numeric(merged["value_new"],errors="coerce")
        revision_count=int(((oldv-newv).abs()>1e-12).fillna(False).sum())

    return [
        _check("history_append_only_keys_preserved",not missing,"FAIL",f"missing_keys={len(missing)}"),
        _check("history_row_count_non_decreasing",len(new)>=len(old),"FAIL",f"current={len(new)} baseline={len(old)}"),
        _check("history_latest_period_not_regressed",not regress,"FAIL",f"regressed={regress or 'none'}"),
        _check("history_value_revisions_recorded",True,"INFO",f"revised_existing_rows={revision_count}"),
    ]


def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument("--pipeline",choices=["live","abf","history"],required=True)
    p.add_argument("--baseline-dir",type=Path,required=True)
    p.add_argument("--current-root",type=Path,default=ROOT)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    fn={"live":validate_live,"abf":validate_abf,"history":validate_history}[args.pipeline]
    checks=fn(args.baseline_dir,args.current_root)
    payload={
        "schema_version":"PipelineContinuityV1",
        "pipeline":args.pipeline,
        "validated_at":pd.Timestamp.now(tz="UTC").isoformat(),
        "status":_status(checks),
        "checks":checks,
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"PIPELINE_CONTINUITY_{payload['status']} pipeline={args.pipeline}")
    for c in checks:
        print(c)
    if payload["status"]=="FAIL":
        raise SystemExit(2)


if __name__=="__main__":
    main()
