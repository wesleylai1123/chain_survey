from __future__ import annotations

from collections import deque

import pandas as pd

from core.data_loader import load_companies, load_edges, load_event_templates, load_macro_exposures, load_macro_factors
from core.fundamental_signals import get_company_signal_lookup

RELATION_PROPAGATION_RULES: dict[str, dict[str, float | int]] = {
    "supplier_of": {"forward_decay": 0.88, "reverse_decay": 0.72, "forward_lag": 1, "reverse_lag": 1, "forward_sign": 1, "reverse_sign": 1},
    "customer_of": {"forward_decay": 0.8, "reverse_decay": 0.78, "forward_lag": 1, "reverse_lag": 1, "forward_sign": 1, "reverse_sign": 1},
    "depends_on": {"forward_decay": 0.84, "reverse_decay": 0.64, "forward_lag": 1, "reverse_lag": 1, "forward_sign": 1, "reverse_sign": 1},
    "produces": {"forward_decay": 0.9, "reverse_decay": 0.86, "forward_lag": 0, "reverse_lag": 0, "forward_sign": 1, "reverse_sign": 1},
    "exposed_to": {"forward_decay": 0.76, "reverse_decay": 0.58, "forward_lag": 1, "reverse_lag": 1, "forward_sign": 1, "reverse_sign": 1},
    "belongs_to": {"forward_decay": 0.7, "reverse_decay": 0.7, "forward_lag": 0, "reverse_lag": 0, "forward_sign": 1, "reverse_sign": 1},
}

MIN_PROPAGATION_SCORE = 0.03
RESULT_COLUMNS = [
    "company",
    "direction",
    "impact_score",
    "signed_score",
    "layer",
    "cumulative_lag",
    "path",
    "reason",
    "sector",
    "industry",
    "fundamental_signal",
    "fundamental_multiplier",
    "seed_source",
    "macro_factor",
    "macro_factor_id",
    "exposure_direction",
    "exposure_rationale",
]


def list_event_names() -> list[str]:
    return [event["name"] for event in load_event_templates()]


def get_event(event_name: str) -> dict:
    for event in load_event_templates():
        if event["name"] == event_name:
            return event
    raise ValueError(f"Event not found: {event_name}")


def _merged_relation_rules(event: dict) -> dict[str, dict[str, float | int]]:
    merged = {relation: values.copy() for relation, values in RELATION_PROPAGATION_RULES.items()}
    for relation, override_values in event.get("relation_overrides", {}).items():
        base = merged.get(relation, {}).copy()
        base.update(override_values)
        merged[relation] = base
    return merged


def _matches_rule(row: pd.Series, match: dict[str, str]) -> bool:
    for key, expected in match.items():
        if expected in ("*", "", None):
            continue
        if str(row.get(key)) != str(expected):
            return False
    return True


def _company_multiplier(company_name: str, companies: pd.DataFrame, event: dict) -> float:
    row = companies.loc[companies["name"] == company_name]
    if row.empty:
        return 1.0

    industry = row.iloc[0]["industry"]
    sector = row.iloc[0]["sector"]
    industry_map = event.get("industry_sensitivity", {})
    sector_map = event.get("sector_sensitivity", {})
    return float(industry_map.get(industry, 1.0)) * float(sector_map.get(sector, 1.0))


def _company_fundamental_adjustment(company_name: str, signed_score: float, signal_lookup: dict[str, dict[str, float | str | None]]) -> tuple[float, float]:
    info = signal_lookup.get(company_name)
    if not info:
        return 1.0, 0.0
    multiplier_key = "positive_multiplier" if signed_score >= 0 else "negative_multiplier"
    multiplier = float(info[multiplier_key])
    signal = float(info["fundamental_signal"])
    return multiplier, signal


def _seed_row(
    *,
    node: str,
    node_type: str,
    signed_score: float,
    start_lag: int,
    reason: str,
    path: str,
    last_edge: tuple[str, str, str] | None,
    fundamental_multiplier: float,
    fundamental_signal: float,
    seed_source: str,
    macro_factor: str | None = None,
    macro_factor_id: str | None = None,
    exposure_direction: str | None = None,
    exposure_rationale: str | None = None,
) -> dict:
    return {
        "node": node,
        "node_type": node_type,
        "signed_score": round(signed_score, 4),
        "layer": 1,
        "cumulative_lag": start_lag,
        "direction": "positive" if signed_score > 0 else "negative",
        "reason": reason,
        "path": path,
        "last_edge": last_edge,
        "fundamental_multiplier": round(fundamental_multiplier, 4),
        "fundamental_signal": round(fundamental_signal, 4),
        "seed_source": seed_source,
        "macro_factor": macro_factor,
        "macro_factor_id": macro_factor_id,
        "exposure_direction": exposure_direction,
        "exposure_rationale": exposure_rationale,
    }


def _build_edge_seed_impacts(
    event: dict,
    edges: pd.DataFrame,
    companies: pd.DataFrame,
    signal_lookup: dict[str, dict[str, float | str | None]],
) -> list[dict]:
    seeds: list[dict] = []
    severity = float(event.get("severity", 1.0))

    for rule in event.get("seed_rules", []):
        match = rule.get("match", {})
        sentiment = str(rule.get("sentiment", "negative")).lower()
        sign = 1.0 if sentiment == "positive" else -1.0
        impact_on = rule.get("impact_on", "target")
        base_score = float(rule.get("base_score", 0.5))
        sensitivity = float(rule.get("sensitivity", 1.0))
        start_lag = int(rule.get("start_lag", 0))
        allow_backflow = bool(rule.get("allow_backflow", False))
        reason = rule.get("reason", "")

        matched = edges[edges.apply(lambda row: _matches_rule(row, match), axis=1)]
        for _, row in matched.iterrows():
            target_prefix = "source" if impact_on == "source" else "target"
            node = row[target_prefix]
            node_type = row[f"{target_prefix}_type"]
            score = severity * base_score * float(row.get("weight", 1.0)) * sensitivity
            fundamental_multiplier = 1.0
            fundamental_signal = 0.0
            if node_type == "company":
                score *= _company_multiplier(node, companies, event)
                fundamental_multiplier, fundamental_signal = _company_fundamental_adjustment(node, score * sign, signal_lookup)
                score *= fundamental_multiplier

            seeds.append(
                _seed_row(
                    node=node,
                    node_type=node_type,
                    signed_score=score * sign,
                    start_lag=start_lag,
                    reason=reason,
                    path=f"seed[{row['source']} -> {row['relation']} -> {row['target']}]",
                    last_edge=None if allow_backflow else (str(row["source"]), str(row["relation"]), str(row["target"])),
                    fundamental_multiplier=fundamental_multiplier,
                    fundamental_signal=fundamental_signal,
                    seed_source="edge_rule",
                )
            )

    return seeds


def _build_macro_seed_impacts(
    event: dict,
    companies: pd.DataFrame,
    signal_lookup: dict[str, dict[str, float | str | None]],
) -> list[dict]:
    seeds: list[dict] = []
    severity = float(event.get("severity", 1.0))
    macro_factors = load_macro_factors().copy()
    macro_exposures = load_macro_exposures().copy()
    macro_factor_lookup = macro_factors.set_index("factor_id").to_dict(orient="index")

    for rule in event.get("macro_seed_rules", []):
        factor_id = str(rule.get("factor_id"))
        if factor_id not in macro_factor_lookup:
            continue

        factor_info = macro_factor_lookup[factor_id]
        matched = macro_exposures[macro_exposures["factor_id"] == factor_id].copy()
        allowed_types = rule.get("entity_types")
        if allowed_types:
            matched = matched[matched["entity_type"].isin(allowed_types)]

        scenario_sentiment = str(rule.get("sentiment", "negative")).lower()
        scenario_sign = 1.0 if scenario_sentiment == "positive" else -1.0
        base_score = float(rule.get("base_score", 0.5))
        sensitivity = float(rule.get("sensitivity", 1.0))
        start_lag = int(rule.get("start_lag", 0))
        reason = str(rule.get("reason", "")).strip()

        for _, row in matched.iterrows():
            exposure_sign = 1.0 if str(row["exposure_direction"]).lower() == "positive" else -1.0
            node = str(row["entity_name"])
            node_type = str(row["entity_type"])
            score = severity * base_score * float(row["weight"]) * sensitivity
            signed_score = score * scenario_sign * exposure_sign

            fundamental_multiplier = 1.0
            fundamental_signal = 0.0
            if node_type == "company":
                signed_score *= _company_multiplier(node, companies, event)
                fundamental_multiplier, fundamental_signal = _company_fundamental_adjustment(node, signed_score, signal_lookup)
                signed_score *= fundamental_multiplier

            factor_name = str(factor_info["display_name"])
            exposure_rationale = str(row["rationale"])
            combined_reason = " | ".join(part for part in [factor_name, exposure_rationale, reason] if part)
            seeds.append(
                _seed_row(
                    node=node,
                    node_type=node_type,
                    signed_score=signed_score,
                    start_lag=start_lag,
                    reason=combined_reason,
                    path=f"macro_seed[{factor_name} -> {node}]",
                    last_edge=None,
                    fundamental_multiplier=fundamental_multiplier,
                    fundamental_signal=fundamental_signal,
                    seed_source="macro_exposure",
                    macro_factor=factor_name,
                    macro_factor_id=factor_id,
                    exposure_direction=str(row["exposure_direction"]),
                    exposure_rationale=exposure_rationale,
                )
            )

    return seeds


def _empty_result() -> pd.DataFrame:
    return pd.DataFrame(columns=RESULT_COLUMNS)


def simulate_event(event_name: str, max_layers: int | None = None) -> pd.DataFrame:
    event = get_event(event_name)
    edges = load_edges().copy()
    companies = load_companies()[["name", "sector", "industry"]].copy()
    signal_lookup = get_company_signal_lookup()
    relation_rules = _merged_relation_rules(event)
    traversal_limit = max_layers or int(event.get("max_layers", 3))

    seeds = _build_edge_seed_impacts(event, edges, companies, signal_lookup)
    seeds.extend(_build_macro_seed_impacts(event, companies, signal_lookup))
    if not seeds:
        return _empty_result()

    queue = deque(seeds)
    impacts: list[dict] = []
    seen_best: dict[tuple[str, int], float] = {}

    while queue:
        current = queue.popleft()
        node = current["node"]
        node_type = current["node_type"]
        signed_score = float(current["signed_score"])
        layer = int(current["layer"])

        if node_type == "company":
            row = companies.loc[companies["name"] == node]
            sector = row.iloc[0]["sector"] if not row.empty else None
            industry = row.iloc[0]["industry"] if not row.empty else None
            impacts.append(
                {
                    "company": node,
                    "direction": "positive" if signed_score > 0 else "negative",
                    "impact_score": round(abs(signed_score), 4),
                    "signed_score": round(signed_score, 4),
                    "layer": layer,
                    "cumulative_lag": current["cumulative_lag"],
                    "path": current["path"],
                    "reason": current["reason"],
                    "sector": sector,
                    "industry": industry,
                    "fundamental_signal": current.get("fundamental_signal", 0.0),
                    "fundamental_multiplier": current.get("fundamental_multiplier", 1.0),
                    "seed_source": current.get("seed_source", "edge_rule"),
                    "macro_factor": current.get("macro_factor"),
                    "macro_factor_id": current.get("macro_factor_id"),
                    "exposure_direction": current.get("exposure_direction"),
                    "exposure_rationale": current.get("exposure_rationale"),
                }
            )

        if layer >= traversal_limit:
            continue

        related = edges[(edges["source"] == node) | (edges["target"] == node)]
        for _, edge in related.iterrows():
            edge_key = (str(edge["source"]), str(edge["relation"]), str(edge["target"]))
            if edge_key == current.get("last_edge"):
                continue

            relation = edge["relation"]
            config = relation_rules.get(relation)
            if config is None:
                continue

            if node == edge["source"]:
                next_node = edge["target"]
                next_type = edge["target_type"]
                decay = float(config["forward_decay"])
                lag = int(config["forward_lag"])
                relation_sign = float(config["forward_sign"])
                next_path = f"{current['path']} => {edge['source']} -> {relation} -> {edge['target']}"
            else:
                next_node = edge["source"]
                next_type = edge["source_type"]
                decay = float(config["reverse_decay"])
                lag = int(config["reverse_lag"])
                relation_sign = float(config["reverse_sign"])
                next_path = f"{current['path']} => {edge['target']} <- {relation} <- {edge['source']}"

            next_score = signed_score * float(edge.get("weight", 1.0)) * decay * relation_sign
            fundamental_multiplier = 1.0
            fundamental_signal = 0.0
            if next_type == "company":
                next_score *= _company_multiplier(next_node, companies, event)
                fundamental_multiplier, fundamental_signal = _company_fundamental_adjustment(next_node, next_score, signal_lookup)
                next_score *= fundamental_multiplier

            if abs(next_score) < MIN_PROPAGATION_SCORE:
                continue

            next_layer = layer + 1
            state_key = (str(next_node), next_layer)
            if abs(next_score) <= abs(seen_best.get(state_key, 0.0)):
                continue
            seen_best[state_key] = abs(next_score)

            queue.append(
                {
                    "node": next_node,
                    "node_type": next_type,
                    "signed_score": round(next_score, 4),
                    "layer": next_layer,
                    "cumulative_lag": int(current["cumulative_lag"]) + lag,
                    "direction": "positive" if next_score > 0 else "negative",
                    "reason": current["reason"],
                    "path": next_path,
                    "last_edge": edge_key,
                    "fundamental_multiplier": round(fundamental_multiplier, 4),
                    "fundamental_signal": round(fundamental_signal, 4),
                    "seed_source": current.get("seed_source", "edge_rule"),
                    "macro_factor": current.get("macro_factor"),
                    "macro_factor_id": current.get("macro_factor_id"),
                    "exposure_direction": current.get("exposure_direction"),
                    "exposure_rationale": current.get("exposure_rationale"),
                }
            )

    result = pd.DataFrame(impacts)
    if result.empty:
        return _empty_result()

    result = result.groupby(
        [
            "company",
            "direction",
            "layer",
            "cumulative_lag",
            "reason",
            "sector",
            "industry",
            "seed_source",
            "macro_factor",
            "macro_factor_id",
            "exposure_direction",
            "exposure_rationale",
        ],
        as_index=False,
        dropna=False,
    ).agg(
        impact_score=("impact_score", "sum"),
        signed_score=("signed_score", "sum"),
        path=("path", lambda values: " | ".join(list(dict.fromkeys(values))[:3])),
        fundamental_signal=("fundamental_signal", "mean"),
        fundamental_multiplier=("fundamental_multiplier", "mean"),
    )
    result["fundamental_signal"] = result["fundamental_signal"].round(4)
    result["fundamental_multiplier"] = result["fundamental_multiplier"].round(4)
    result = result.sort_values(["layer", "impact_score"], ascending=[True, False]).reset_index(drop=True)
    return result
