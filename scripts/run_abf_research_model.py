from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from core.abf_sensitivity_engine import SensitivityConfig, estimate_company_revenue_sensitivities
from core.indicator_taxonomy import indicator_table

HISTORY=ROOT/"data"/"history"/"free_industry_history_panel.csv"
OUT=ROOT/"artifacts"


def main() -> None:
    history=pd.read_csv(HISTORY)
    sensitivities=estimate_company_revenue_sensitivities(
        history,
        config=SensitivityConfig(),
    )
    indicators=indicator_table()

    OUT.mkdir(parents=True,exist_ok=True)
    sensitivities.to_csv(OUT/"abf_revenue_sensitivity.csv",index=False)
    indicators.to_csv(OUT/"abf_indicator_timing.csv",index=False)

    basket=sensitivities[sensitivities["ticker"]=="ABF"].iloc[0]
    revenue_status=(
        "DIRECTION_AND_MAGNITUDE_VALIDATED"
        if bool(basket["magnitude_validation_pass"])
        else "DIRECTION_VALIDATED_MAGNITUDE_CANDIDATE"
    )

    snapshot={
        "schema_version":"ABFResearchSnapshotV1",
        "industry_model_id":"ic_substrate_abf_bt",
        "leading_indicator":{
            "indicator_id":"tpca_pcb_revenue_yoy",
            "timing_class":"LEADING",
            "relative_to":"abf_revenue_yoy_basket",
            "validated_lag_months":1
        },
        "driver":{
            "driver_id":"end_demand",
            "meaning":"Compute / networking end-demand state",
            "source_indicator":"tpca_pcb_revenue_yoy",
            "relation_status":"VALIDATED"
        },
        "sensitivity":{
            "model_type":"linear_beta_v1",
            "source_units":"TPCA PCB Revenue YoY percentage points",
            "target_units":"ABF company revenue YoY percentage points",
            "rows":sensitivities.where(pd.notna(sensitivities),None).to_dict("records")
        },
        "downstream":{
            "revenue":revenue_status,
            "gross_margin":"NOT_YET_CALIBRATED",
            "operating_margin":"NOT_YET_CALIBRATED",
            "eps":"NOT_YET_CALIBRATED"
        },
        "interaction":{
            "indicator":"Observed point-in-time metric. Timing class is relative to a target.",
            "driver":"Economic state inferred from one or more indicators. A driver score is not itself a financial beta.",
            "sensitivity":"Empirical translation from a validated observable driver metric into a downstream operating metric.",
            "model":"Structural industry equations that determine where each driver and sensitivity belongs in the revenue/margin/EPS chain."
        }
    }
    (OUT/"abf_research_snapshot.json").write_text(json.dumps(snapshot,ensure_ascii=False,indent=2,default=str)+"\n",encoding="utf-8")
    print("ABF_RESEARCH_MODEL_OK",len(sensitivities),len(indicators))
    print(sensitivities[["company","beta","beta_ci_low","beta_ci_high","r2","oos_r2","impact_per_10ppt_driver"]].to_string(index=False))


if __name__=="__main__":
    main()
