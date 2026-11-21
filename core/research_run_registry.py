from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


def git_sha(ref: str="HEAD") -> str:
    try:
        return subprocess.check_output(["git","rev-parse",ref],text=True).strip()
    except Exception:
        return "unknown"


def build_research_run(
    results: pd.DataFrame,
    *,
    question: str,
    history_path: Path,
    evidence_ref: str="origin/evidence-data",
) -> dict[str,Any]:
    return {
        "schema_version":"ResearchRunV1",
        "research_run_id":f"driver-validation-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{git_sha()[:8]}",
        "created_at":datetime.now(timezone.utc).isoformat(),
        "question":question,
        "code_sha":os.getenv("GITHUB_SHA") or git_sha(),
        "evidence_snapshot_sha":git_sha(evidence_ref),
        "history_path":str(history_path),
        "methodology":{
            "point_in_time":True,
            "lags":"0-6M candidate scan",
            "correlations":["spearman","pearson"],
            "robustness":["rolling 12M/18M","chronological OOS","nested walk-forward","cross-company","moving-block bootstrap","block permutation","Benjamini-Hochberg FDR"],
            "promotion_rule":"VALIDATED only if all robustness gates and FDR q<=0.10 pass",
        },
        "candidate_count":int(len(results)),
        "validated_count":int((results["status"]=="VALIDATED").sum()) if not results.empty else 0,
        "results":results.where(pd.notna(results),None).to_dict("records"),
    }


def write_run(run: dict[str,Any], path: Path) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(run,ensure_ascii=False,indent=2,default=str)+"\n",encoding="utf-8")
