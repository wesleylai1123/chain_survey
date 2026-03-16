from __future__ import annotations

import pandas as pd

from core.data_loader import load_companies, load_edges, load_events



def list_event_names() -> list[str]:
    return [e["name"] for e in load_events()]



def get_event(event_name: str) -> dict:
    for event in load_events():
        if event["name"] == event_name:
            return event
    raise ValueError(f"Event not found: {event_name}")



def simulate_event(event_name: str) -> pd.DataFrame:
    event = get_event(event_name)
    edges = load_edges().copy()
    companies = load_companies()[["name", "sector", "industry"]].copy()

    affected_rows = []
    rules = event.get("rules", [])
    severity = float(event.get("severity", 1.0))

    for rule in rules:
        relation = rule.get("relation")
        target_type = rule.get("target_type")
        direction = rule.get("direction")
        base_score = float(rule.get("base_score", 0.5))
        reason = rule.get("reason", "")

        df = edges.copy()
        if relation:
            df = df[df["relation"] == relation]
        if target_type:
            df = df[df["target_type"] == target_type]
        if rule.get("target"):
            df = df[df["target"] == rule["target"]]
        if rule.get("source"):
            df = df[df["source"] == rule["source"]]

        for _, row in df.iterrows():
            exposure = float(row.get("weight", 1.0))
            sensitivity = float(rule.get("sensitivity", 1.0))
            score = round(severity * base_score * exposure * sensitivity, 3)
            affected_rows.append(
                {
                    "company": row["source"] if row["source_type"] == "company" else row["target"],
                    "direction": direction,
                    "impact_score": score,
                    "path": f"{row['source']} -> {row['relation']} -> {row['target']}",
                    "reason": reason,
                }
            )

    if not affected_rows:
        return pd.DataFrame(columns=["company", "direction", "impact_score", "path", "reason"])

    result = pd.DataFrame(affected_rows)
    result = result.groupby(["company", "direction", "reason"], as_index=False).agg(
        impact_score=("impact_score", "sum"),
        path=("path", lambda x: " | ".join(list(dict.fromkeys(x))[:3])),
    )
    result = result.merge(companies, left_on="company", right_on="name", how="left").drop(columns=["name"])
    result = result.sort_values("impact_score", ascending=False).reset_index(drop=True)
    return result
