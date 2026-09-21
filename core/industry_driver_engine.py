from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from core.evidence_demand_engine import deduplicate_evidence, score_evidence

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_PATH = ROOT / "data" / "industry_driver_models.json"


def load_industry_models(path: str | Path = DEFAULT_MODEL_PATH) -> dict[str, dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    models = payload.get("models", [])
    result: dict[str, dict[str, Any]] = {}
    for model in models:
        model_id = str(model["model_id"])
        if model_id in result:
            raise ValueError(f"Duplicate model_id: {model_id}")
        result[model_id] = model
    return result


def _neutral_score(signal: float) -> float:
    return max(0.0, min(100.0, 50.0 + 50.0 * signal))


def _driver_signal(groups: pd.DataFrame, driver: Mapping[str, Any]) -> dict[str, Any]:
    chains = set(map(str, driver.get("chains", [])))
    dimensions = set(map(str, driver.get("dimensions", [])))
    selected = groups.copy()
    if chains:
        selected = selected[selected["chain"].astype(str).isin(chains)]
    if dimensions:
        selected = selected[selected["dimension"].astype(str).isin(dimensions)]
    if selected.empty:
        return {
            "driver_id": driver["driver_id"],
            "driver_name": driver["name"],
            "score": 50.0,
            "signal": 0.0,
            "confidence": 0.0,
            "evidence_groups": 0,
            "weight": float(driver.get("weight", 0.0)),
            "polarity": int(driver.get("polarity", 1)),
        }

    confidence_weights = selected["group_confidence"].clip(lower=0.05)
    raw = float((selected["group_signal"] * confidence_weights).sum() / confidence_weights.sum())
    polarity = int(driver.get("polarity", 1))
    signal = raw * polarity
    confidence = float(1.0 - (1.0 - selected["group_confidence"].clip(0, 0.95)).prod())
    return {
        "driver_id": driver["driver_id"],
        "driver_name": driver["name"],
        "score": round(_neutral_score(signal), 2),
        "signal": round(signal, 4),
        "confidence": round(confidence * 100.0, 1),
        "evidence_groups": int(len(selected)),
        "weight": float(driver.get("weight", 0.0)),
        "polarity": polarity,
    }


def evaluate_industry_model(
    evidence: pd.DataFrame,
    model_id: str,
    *,
    model_path: str | Path = DEFAULT_MODEL_PATH,
    as_of_date: str | pd.Timestamp | None = None,
) -> dict[str, Any]:
    models = load_industry_models(model_path)
    if model_id not in models:
        raise KeyError(f"Unknown industry model: {model_id}")
    model = models[model_id]

    scored = score_evidence(evidence, as_of_date=as_of_date)
    groups = deduplicate_evidence(scored)
    driver_rows = [_driver_signal(groups, driver) for driver in model.get("drivers", [])]
    drivers = pd.DataFrame(driver_rows)

    usable = drivers[drivers["evidence_groups"] > 0].copy()
    if usable.empty:
        overall_signal = 0.0
        coverage = 0.0
    else:
        total_configured_weight = float(drivers["weight"].sum())
        used_weight = float(usable["weight"].sum())
        overall_signal = float((usable["signal"] * usable["weight"]).sum() / used_weight) if used_weight else 0.0
        coverage = used_weight / total_configured_weight if total_configured_weight else 0.0

    score = round(_neutral_score(overall_signal), 2)
    confidence_components = usable["confidence"] / 100.0 if not usable.empty else pd.Series(dtype=float)
    evidence_confidence = float(1.0 - (1.0 - confidence_components.clip(0, 0.95)).prod()) if not usable.empty else 0.0
    confidence = round(100.0 * evidence_confidence * coverage, 1)

    if score >= 68:
        state = "Strong tailwind"
    elif score >= 56:
        state = "Improving"
    elif score <= 32:
        state = "Strong headwind"
    elif score <= 44:
        state = "Deteriorating"
    else:
        state = "Mixed"

    bridge = model.get("financial_bridge", {})
    driver_lookup = {row["driver_id"]: row for row in driver_rows}
    volume = driver_lookup.get(bridge.get("volume_driver"), {"score": 50.0})["score"]
    asp = driver_lookup.get(bridge.get("asp_driver"), {"score": 50.0})["score"]
    margin_ids = bridge.get("margin_drivers", [])
    margin_scores = [driver_lookup[d]["score"] for d in margin_ids if d in driver_lookup]
    margin = sum(margin_scores) / len(margin_scores) if margin_scores else 50.0

    return {
        "model_id": model_id,
        "model_name": model["name"],
        "products": list(model.get("products", [])),
        "score": score,
        "state": state,
        "confidence": confidence,
        "coverage": round(coverage * 100.0, 1),
        "drivers": drivers.sort_values(["score", "confidence"], ascending=[False, False]).reset_index(drop=True),
        "product_economics": {
            "volume_score": round(float(volume), 1),
            "asp_score": round(float(asp), 1),
            "margin_score": round(float(margin), 1),
        },
        "equations": {
            key: model[key]
            for key in ("demand_equation", "supply_equation", "revenue_equation", "margin_equation")
            if key in model
        },
        "evidence_groups": groups,
    }


def evaluate_all_industry_models(
    evidence: pd.DataFrame,
    *,
    model_path: str | Path = DEFAULT_MODEL_PATH,
    as_of_date: str | pd.Timestamp | None = None,
) -> pd.DataFrame:
    models = load_industry_models(model_path)
    rows = []
    for model_id in models:
        result = evaluate_industry_model(
            evidence,
            model_id,
            model_path=model_path,
            as_of_date=as_of_date,
        )
        rows.append(
            {
                "model_id": model_id,
                "model_name": result["model_name"],
                "products": ", ".join(result["products"]),
                "score": result["score"],
                "state": result["state"],
                "confidence": result["confidence"],
                "coverage": result["coverage"],
                "volume_score": result["product_economics"]["volume_score"],
                "asp_score": result["product_economics"]["asp_score"],
                "margin_score": result["product_economics"]["margin_score"],
            }
        )
    return pd.DataFrame(rows).sort_values(["score", "confidence"], ascending=False).reset_index(drop=True)


def map_models_to_companies(
    model_results: pd.DataFrame,
    company_product_relationships: pd.DataFrame,
    *,
    model_path: str | Path = DEFAULT_MODEL_PATH,
) -> pd.DataFrame:
    models = load_industry_models(model_path)
    rows: list[dict[str, Any]] = []
    rel = company_product_relationships.copy()
    rel["weight"] = pd.to_numeric(rel.get("weight"), errors="coerce").fillna(1.0)

    for _, model_row in model_results.iterrows():
        model = models[str(model_row["model_id"])]
        products = set(map(str, model.get("products", [])))
        matches = rel[rel["product"].astype(str).isin(products)]
        for _, match in matches.iterrows():
            exposure = float(match["weight"])
            rows.append(
                {
                    "company": match["company"],
                    "product": match["product"],
                    "model_id": model_row["model_id"],
                    "model_name": model_row["model_name"],
                    "industry_score": float(model_row["score"]),
                    "exposure_weight": exposure,
                    "exposure_adjusted_signal": round((float(model_row["score"]) - 50.0) * exposure, 2),
                    "state": model_row["state"],
                    "confidence": float(model_row["confidence"]),
                }
            )
    if not rows:
        return pd.DataFrame(columns=[
            "company", "product", "model_id", "model_name", "industry_score",
            "exposure_weight", "exposure_adjusted_signal", "state", "confidence"
        ])
    return pd.DataFrame(rows).sort_values("exposure_adjusted_signal", ascending=False).reset_index(drop=True)
