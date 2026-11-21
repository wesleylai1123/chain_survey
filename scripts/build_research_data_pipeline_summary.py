from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd


PIPELINES=("live","abf","history")


def _load_json(path: Path) -> dict[str,Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_summary(evidence_root: Path, run_id: str) -> tuple[dict[str,Any],pd.DataFrame]:
    rows=[]
    detail={}
    for pipeline in PIPELINES:
        root=evidence_root/"persistent"/"run_manifests"/pipeline
        manifest_path=root/f"{run_id}.json"
        validation_path=root/f"{run_id}.validation.json"
        continuity_path=root/f"{run_id}.continuity.json"
        missing=[str(p) for p in (manifest_path,validation_path,continuity_path) if not p.exists()]
        if missing:
            rows.append({
                "pipeline":pipeline,
                "manifest_status":"MISSING",
                "validation_status":"MISSING",
                "continuity_status":"MISSING",
                "checks_total":0,
                "checks_failed":0,
                "checks_degraded":0,
                "code_revision":"",
                "missing_files":" | ".join(missing),
            })
            detail[pipeline]={"missing_files":missing}
            continue

        manifest=_load_json(manifest_path)
        validation=_load_json(validation_path)
        continuity=_load_json(continuity_path)
        checks=list(manifest.get("checks",[]))
        failed=[c for c in checks if not bool(c.get("passed",False)) and str(c.get("severity","")).upper()=="FAIL"]
        degraded=[c for c in checks if not bool(c.get("passed",False)) and str(c.get("severity","")).upper()!="FAIL"]
        rows.append({
            "pipeline":pipeline,
            "manifest_status":manifest.get("status","UNKNOWN"),
            "validation_status":validation.get("status","UNKNOWN"),
            "continuity_status":continuity.get("status","UNKNOWN"),
            "checks_total":len(checks),
            "checks_failed":len(failed),
            "checks_degraded":len(degraded),
            "code_revision":manifest.get("code_revision",""),
            "missing_files":"",
        })
        detail[pipeline]={
            "manifest":manifest,
            "validation":validation,
            "continuity":continuity,
        }

    frame=pd.DataFrame(rows)
    if frame.empty:
        overall="FAIL"
    elif (
        frame["manifest_status"].isin(["PASS","DEGRADED"]).all()
        and frame["validation_status"].isin(["PASS","DEGRADED"]).all()
        and frame["continuity_status"].isin(["PASS","DEGRADED"]).all()
        and frame["checks_failed"].eq(0).all()
    ):
        overall="DEGRADED" if (
            frame["manifest_status"].eq("DEGRADED").any()
            or frame["validation_status"].eq("DEGRADED").any()
            or frame["continuity_status"].eq("DEGRADED").any()
            or frame["checks_degraded"].gt(0).any()
        ) else "PASS"
    else:
        overall="FAIL"

    payload={
        "schema_version":"ResearchDataPipelineSummaryV1",
        "run_id":run_id,
        "overall_status":overall,
        "pipelines":detail,
    }
    return payload,frame


def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument("--evidence-root",type=Path,required=True)
    p.add_argument("--run-id",required=True)
    p.add_argument("--json-output",type=Path,required=True)
    p.add_argument("--csv-output",type=Path,required=True)
    args=p.parse_args()

    payload,frame=build_summary(args.evidence_root,args.run_id)
    args.json_output.parent.mkdir(parents=True,exist_ok=True)
    args.csv_output.parent.mkdir(parents=True,exist_ok=True)
    args.json_output.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    frame.to_csv(args.csv_output,index=False)

    print(frame.to_string(index=False))
    print(f"RESEARCH_DATA_PIPELINE_SUMMARY status={payload['overall_status']} run_id={args.run_id}")
    if payload["overall_status"]=="FAIL":
        raise SystemExit(2)


if __name__=="__main__":
    main()
