from __future__ import annotations

import re
from collections import defaultdict
from math import isfinite

from core.data_loader import (
    load_companies,
    load_company_product_relationships,
    load_company_relationships,
    load_edges,
    load_product_financials,
    load_product_relationships,
)
from core.fundamental_signals import get_company_signal_lookup
from core.impact_engine import _typed_edge, _walk_event, get_event
from core.product_supply_chain_service import get_managed_mappings_for_product


def _rank(path: dict) -> tuple:
    return (-abs(path["signed_score"]), path["layer"], path["cumulative_lag"], path["path"])


def _scores(paths: list[dict]) -> dict:
    positive = max((p["signed_score"] for p in paths if p["signed_score"] > 0), default=None)
    negative = min((p["signed_score"] for p in paths if p["signed_score"] < 0), default=None)
    if positive is not None and negative is not None:
        direction, score = "混合", None
    elif positive is not None:
        direction, score = "正面", positive
    elif negative is not None:
        direction, score = "負面", negative
    else:
        direction, score = "證據不足", None
    return {"direction": direction, "score": score, "positive_score": positive, "negative_score": negative}


def _evidence(paths: list[dict]) -> list[dict]:
    selected = {}
    for path in sorted(paths, key=_rank):
        key = (path["signed_score"] > 0, path["layer"] == 1)
        selected.setdefault(key, path)
    return [
        {k: path[k] for k in ("signed_score", "reason", "path", "layer", "cumulative_lag")}
        for path in selected.values()
    ]


def _revenue_mix(company: str) -> dict[str, tuple[float, str]]:
    financials = load_product_financials()
    financials = financials[financials["company"] == company]
    latest = {}
    for row in financials.itertuples(index=False):
        period = str(row.period)
        quarter = re.fullmatch(r"(\d{3,4})Q([1-4])", period)
        if quarter is None or row.revenue_mix_pct is None:
            continue
        year, q = map(int, quarter.groups())
        sort_key = (year + 1911 if year < 1911 else year, q)
        try:
            mix = float(row.revenue_mix_pct)
        except (TypeError, ValueError):
            continue
        if isfinite(mix) and 0 <= mix <= 100 and sort_key > latest.get(row.product, ((0, 0), 0, ""))[0]:
            latest[row.product] = (sort_key, mix, period)
    return {product: (mix, period) for product, (_, mix, period) in latest.items()}


def _managed_edge(edge) -> tuple:
    if edge.direction == "upstream":
        ends = (edge.related_company, "company", edge.relation, edge.source_product, "product")
    else:
        ends = (edge.source_product, "product", edge.relation, edge.related_company, "company")
    return _typed_edge(*ends, "analyst_managed")


def _chain_rows(company, owned, producers, mappings, paths):
    rows = []

    def add(partner, role, product, link, rationale="", hops=()):
        if partner == company:
            return
        candidates = paths.get(("company", partner), [])
        if hops:
            candidates = [p for p in candidates if p["edges"][-len(hops):] == hops]
        best = min(candidates, key=_rank, default=None)
        summary = _scores(candidates)
        rows.append({
            "company": partner, "role": role, "product": product, "link": link,
            **summary,
            "path": best["path"] if best else "",
            "reason": "｜".join(filter(None, (rationale, best["reason"] if best else ""))),
            "cumulative_lag": best["cumulative_lag"] if best else None,
            "paths": _evidence(candidates),
        })

    for edge in load_company_relationships().itertuples(index=False):
        if edge.relation == "supplier_of" and edge.target_company == company:
            add(edge.source_company, "上游", None, "公司供應商（資料庫）")
        elif edge.relation == "supplier_of" and edge.source_company == company:
            add(edge.target_company, "下游", None, "公司客戶（資料庫）")
        elif edge.relation == "customer_of":
            # The shipped legacy data stores vendor -> customer for customer_of.
            if edge.source_company == company:
                add(edge.target_company, "下游", None, "公司客戶（資料庫）")
            elif edge.target_company == company:
                add(edge.source_company, "上游", None, "公司供應商（資料庫）")

    for edge in load_product_relationships().itertuples(index=False):
        if edge.relation != "depends_on":
            continue
        dependency = _typed_edge(edge.source_product, "product", edge.relation, edge.target_product, "product", "curated")
        for role, product, linked_product in (
            ("上游", edge.source_product, edge.target_product),
            ("下游", edge.target_product, edge.source_product),
        ):
            if product not in owned:
                continue
            for partner in producers.get(linked_product, []):
                produces = _typed_edge(partner, "company", "produces", linked_product, "product", "curated")
                add(partner, role, product, f"{linked_product} 生產商（產品依賴）", hops=(dependency, produces))
    for edge in mappings.itertuples(index=False):
        add(edge.related_company, "上游" if edge.direction == "upstream" else "下游",
            edge.source_product, "分析師設定", str(edge.rationale), hops=(_managed_edge(edge),))

    return sorted(rows, key=lambda row: (row["product"] or "", row["role"], row["company"], row["link"]))


def analyze_topic(company: str, event_name: str) -> dict:
    event = get_event(event_name)
    companies = load_companies()[["name", "sector", "industry"]]
    if company not in set(companies["name"]):
        raise ValueError(f"Unknown company: {company}")
    relations = load_company_product_relationships()
    producers = defaultdict(list)
    owned = {}
    for edge in relations[relations["relation"] == "produces"].itertuples(index=False):
        producers[edge.product].append(edge.company)
        if edge.company == company:
            owned[edge.product] = float(edge.weight)

    # Managed product names can be shared by multiple producers. Keep only
    # mappings configured for the selected company.
    mappings = get_managed_mappings_for_product(company)
    loaded_edges = load_edges()
    edges = loaded_edges[loaded_edges["source_dataset"] != "analyst_managed"].reset_index(drop=True)
    columns = ("source", "source_type", "relation", "target", "target_type", "source_dataset")
    for edge in mappings.itertuples(index=False):
        edges.loc[len(edges)] = {**dict(zip(columns, _managed_edge(edge))), "weight": edge.weight}

    paths = defaultdict(list)
    for path in _walk_event(event, edges, companies, get_company_signal_lookup(), product_evidence=True):
        if path["signed_score"]:
            paths[path["node_type"], path["node"]].append(path)

    mixes = _revenue_mix(company)
    products = []
    for product, weight in owned.items():
        product_paths = paths["product", product]
        direct = any(path["layer"] == 1 for path in product_paths)
        indirect = any(path["layer"] > 1 for path in product_paths)
        if direct:
            exposure = "直接及間接" if indirect else "直接"
        else:
            exposure = "間接" if indirect else "無產品路徑"
        mix, period = mixes.get(product, (None, None))
        products.append({
            "product": product, "relationship_weight": weight,
            "revenue_mix_pct": mix, "revenue_mix_period": period, "exposure": exposure,
            **_scores(product_paths), "paths": _evidence(product_paths),
        })
    products.sort(key=lambda p: (-max(p["positive_score"] or 0, abs(p["negative_score"] or 0)), p["product"]))

    company_paths = paths["company", company]
    relevant = company_paths + [path for product in owned for path in paths["product", product]]
    scores = _scores(relevant)
    magnitude = max(scores["positive_score"] or 0, abs(scores["negative_score"] or 0))
    relevance = "高" if magnitude >= 0.7 else "中" if magnitude >= 0.35 else "低" if magnitude else "證據不足"
    affected = [f"{p['product']}（{p['direction']}）" for p in products if p["paths"]]
    sentences = [f"{company}對「{event_name}」的模型方向為{scores['direction']}。"]
    if affected:
        sentences.append(f"有產品路徑的項目：{'、'.join(affected[:3])}。")
    else:
        sentences.append("目前資料沒有個別產品的傳導路徑。")
    if company_paths:
        sentences.append(f"公司層級主要原因：{min(company_paths, key=_rank)['reason']}")
    return {
        "company": company, "event": event_name, "description": event.get("description", ""),
        "relevance": relevance, "direction": scores["direction"], "summary": "".join(sentences),
        "products": products, "chain": _chain_rows(company, owned, producers, mappings, paths),
    }
