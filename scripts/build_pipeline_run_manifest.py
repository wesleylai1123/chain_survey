from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

ROOT=Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()


def file_record(path: Path) -> dict[str,Any]:
    return {
        "path":str(path.relative_to(ROOT)),
        "exists":path.exists(),
        "bytes":path.stat().st_size if path.exists() else 0,
        "sha256":sha256_file(path) if path.exists() else "",
    }


def classify_status(checks: list[dict[str,Any]]) -> str:
    if any(c["severity"]=="FAIL" and not c["passed"] for c in checks):
        return "FAIL"
    if any(not c["passed"] for c in checks):
        return "DEGRADED"
    return "PASS"


def build_manifest(run_id: str, pipeline: str, inputs: list[Path], outputs: list[Path], checks: list[dict[str,Any]]) -> dict[str,Any]:
    return {
        "schema_version":"ResearchPipelineRunV1",
        "pipeline_run_id":run_id,
        "pipeline":pipeline,
        "status":classify_status(checks),
        "generated_at":pd.Timestamp.now(tz="UTC").isoformat(),
        "inputs":[file_record(p) for p in inputs],
        "outputs":[file_record(p) for p in outputs],
        "checks":checks,
    }


def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument("--run-id",required=True)
    p.add_argument("--pipeline",required=True)
    p.add_argument("--output-manifest",type=Path,required=True)
    p.add_argument("--input",action="append",default=[])
    p.add_argument("--output",action="append",default=[])
    p.add_argument("--check-json",action="append",default=[])
    args=p.parse_args()

    checks=[json.loads(x) for x in args.check_json]
    manifest=build_manifest(
        args.run_id,args.pipeline,
        [ROOT/x for x in args.input],
        [ROOT/x for x in args.output],
        checks,
    )
    args.output_manifest.parent.mkdir(parents=True,exist_ok=True)
    args.output_manifest.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"PIPELINE_RUN_MANIFEST_OK pipeline={args.pipeline} status={manifest['status']} checks={len(checks)}")
    if manifest["status"]=="FAIL":
        raise SystemExit(2)


if __name__=="__main__":
    main()
