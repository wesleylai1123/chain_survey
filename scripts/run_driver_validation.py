from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from core.driver_validation_engine import DriverValidationConfig, validate_candidate_table
from core.research_run_registry import build_research_run, write_run

HISTORY=ROOT/"data"/"history"/"free_industry_history_panel.csv"
OUT=ROOT/"artifacts"


def main() -> None:
    history=pd.read_csv(HISTORY)
    results,details=validate_candidate_table(history,top_n=12,config=DriverValidationConfig())
    if results.empty:
        raise RuntimeError("No driver validation results")

    OUT.mkdir(parents=True,exist_ok=True)
    results.to_csv(OUT/"validated_driver_candidates.csv",index=False)

    compact={}
    for key,value in details.items():
        compact[key]={
            "gates":value["gates"],
            "cross_company":value["cross_company"].to_dict("records"),
            "rolling":value["rolling"].to_dict("records"),
            "walk_forward":value["walk_forward"].to_dict("records"),
        }
    (OUT/"validated_driver_details.json").write_text(
        json.dumps(compact,indent=2,default=str)+"\n",encoding="utf-8"
    )

    run=build_research_run(
        results,
        question="Which existing TPCA indicators robustly lead ABF company revenue YoY?",
        history_path=HISTORY,
    )
    write_run(run,OUT/"research_run.json")
    print("VALIDATED_DRIVER_PIPELINE_OK",len(results),int((results["status"]=="VALIDATED").sum()))
    print(results.to_string(index=False))


if __name__=="__main__":
    main()
