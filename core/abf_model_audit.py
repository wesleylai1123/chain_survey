from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
MODEL_PATH=ROOT/"data"/"industry_driver_models.json"
REGISTRY_PATH=ROOT/"data"/"validated_driver_registry.json"


def build_abf_model_audit(
    sensitivity: pd.DataFrame,
    margin_scan: pd.DataFrame,
    scenarios: pd.DataFrame,
    *,
    model_path: str | Path=MODEL_PATH,
    registry_path: str | Path=REGISTRY_PATH,
) -> pd.DataFrame:
    models=json.loads(Path(model_path).read_text(encoding="utf-8"))["models"]
    model=next(m for m in models if m["model_id"]=="ic_substrate_abf_bt")
    registry=json.loads(Path(registry_path).read_text(encoding="utf-8"))
    validated={d["driver_id"]:d for d in registry.get("drivers",[]) if d.get("status") in {"VALIDATED","PRODUCTION"}}

    rows=[]
    for d in model["drivers"]:
        relation_ids=d.get("validated_relations",[])
        relations=[validated[r] for r in relation_ids if r in validated]
        if relations:
            r=relations[0]
            assessment="EMPIRICALLY_VALIDATED_DRIVER"
            empirical=f"ρ={r['validation']['spearman']:+.2f}, lag={r['expected_lag_months']}M, FDR q={r['validation']['fdr_q']:.3f}"
            why="Mechanism is plausible and the relation passed the validated-driver robustness gates."
        elif d["driver_id"]=="cost_risk":
            assessment="NEEDS_REFINEMENT"
            empirical="No validated raw-material cost relation yet"
            why="Current evidence bucket can mix product tightness with input-cost pressure; split raw-material cost from substrate pricing/tightness before calibration."
        else:
            assessment="STRUCTURAL_HYPOTHESIS"
            empirical="No validated relation registered"
            why="Economically plausible structural driver, but current configured weight is an assumption rather than an empirically calibrated sensitivity."
        rows.append({
            "component_type":"DRIVER",
            "component":d["name"],
            "input_or_feature":", ".join(d.get("dimensions",[])),
            "target":"industry state / financial bridge",
            "lag":"",
            "metric":"",
            "assessment":assessment,
            "model_use":"ACTIVE_STATE_SCORE",
            "weight_or_beta":f"weight={float(d.get('weight',0)):.2f}",
            "why":why,
            "empirical_evidence":empirical,
        })

    for _,r in sensitivity.iterrows():
        valid=bool(r.get("magnitude_validation_pass",False))
        rows.append({
            "component_type":"SENSITIVITY",
            "component":f"{r['company']} revenue beta",
            "input_or_feature":str(r["feature"]),
            "target":str(r["target"]),
            "lag":f"{int(r['lag_months'])}M",
            "metric":f"β={float(r['beta']):+.2f}; OOS R²={float(r['oos_r2']):+.2f}; OOS rank={float(r['oos_directional_corr']):+.2f}",
            "assessment":"MAGNITUDE_VALIDATED" if valid else "MAGNITUDE_CANDIDATE",
            "model_use":"MAGNITUDE_OK" if valid else "DO_NOT_USE_AS_FIXED_FORECAST_BETA",
            "weight_or_beta":f"β={float(r['beta']):+.2f}",
            "why":"Beta sign is supported by the validated leading relation, but magnitude requires positive OOS R² and stable out-of-sample direction.",
            "empirical_evidence":f"95% CI {float(r['beta_ci_low']):+.2f}..{float(r['beta_ci_high']):+.2f}; n={int(r['sample_size'])}",
        })

    if not margin_scan.empty:
        for _,r in margin_scan.iterrows():
            status=str(r["status"])
            rows.append({
                "component_type":"CORRELATION",
                "component":"Revenue → Gross Margin",
                "input_or_feature":str(r["feature"]),
                "target":str(r["target"]),
                "lag":f"{int(r['lag_quarters'])}Q",
                "metric":f"ρ={float(r['spearman']):+.2f}; OOS={float(r['oos_spearman']):+.2f}; FDR q={float(r['fdr_q']):.3f}",
                "assessment":"ROBUST_CANDIDATE" if status=="CANDIDATE" else "WEAK_OR_UNSTABLE",
                "model_use":"RESEARCH_CANDIDATE_ONLY" if status=="CANDIDATE" else "DO_NOT_USE",
                "weight_or_beta":"",
                "why":"Revenue and margin share cycle effects; positive lead-lag evidence is useful, but correlation alone is not causal and should not be converted directly into a margin beta.",
                "empirical_evidence":f"n={int(r['sample_size'])}; cross-company sign={float(r['cross_company_sign_share']):.0%}",
            })

    if not scenarios.empty:
        for _,r in scenarios.iterrows():
            rows.append({
                "component_type":"SCENARIO",
                "component":f"{r['scenario']} leading evidence",
                "input_or_feature":str(r["source_name"]),
                "target":str(r["target_metric"]),
                "lag":f"{int(r['lag_months'])}M",
                "metric":f"ρ={float(r['spearman']):+.2f}; hit={float(r['target_direction_hit_rate']):.0%}; OOS={float(r['oos_spearman']):+.2f}",
                "assessment":"VALIDATED" if str(r["status"])=="VALIDATED" else "CANDIDATE_ONLY",
                "model_use":"DIRECTIONAL_SCENARIO_EVIDENCE" if str(r["status"])=="VALIDATED" else "DO_NOT_PROMOTE",
                "weight_or_beta":"",
                "why":"Upside/downside subsets are separate hypotheses. A full-sample validated driver does not imply transformed scenario subsets are independently validated.",
                "empirical_evidence":f"FDR q={float(r['fdr_q']):.3f}; n={int(r['sample_size'])}",
            })

    return pd.DataFrame(rows)
