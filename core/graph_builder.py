from __future__ import annotations

import networkx as nx
import pandas as pd
import plotly.graph_objects as go

from core.data_loader import load_companies, load_edges, load_products

NODE_TYPE_COLOR = {
    "company": "#2563eb",
    "product": "#10b981",
    "market": "#f59e0b",
    "event": "#ef4444",
}



def build_subgraph(center: str, depth: int = 1) -> nx.Graph:
    edges = load_edges()
    companies = load_companies()
    products = load_products()

    node_types = {}
    for _, row in companies.iterrows():
        node_types[row["name"]] = "company"
    for _, row in products.iterrows():
        node_types[row["name"]] = "product"

    market_nodes = set(edges.loc[edges["target_type"] == "market", "target"].tolist())
    for m in market_nodes:
        node_types[m] = "market"

    g = nx.Graph()
    frontier = {center}
    visited = set()

    for _ in range(depth):
        next_frontier = set()
        for node in frontier:
            if node in visited:
                continue
            visited.add(node)
            related = edges[(edges["source"] == node) | (edges["target"] == node)]
            for _, r in related.iterrows():
                s, t = r["source"], r["target"]
                g.add_node(s, node_type=node_types.get(s, r.get("source_type", "company")))
                g.add_node(t, node_type=node_types.get(t, r.get("target_type", "company")))
                g.add_edge(s, t, relation=r["relation"], weight=r.get("weight", 1.0))
                next_frontier.update([s, t])
        frontier = next_frontier

    if center not in g.nodes:
        g.add_node(center, node_type=node_types.get(center, "company"))
    return g



def draw_plotly_graph(g: nx.Graph, center: str) -> go.Figure:
    if len(g.nodes) == 1:
        pos = {center: (0, 0)}
    else:
        pos = nx.spring_layout(g, seed=42, k=1.2)

    edge_x, edge_y = [], []
    for u, v in g.edges():
        x0, y0 = pos[u]
        x1, y1 = pos[v]
        edge_x += [x0, x1, None]
        edge_y += [y0, y1, None]

    edge_trace = go.Scatter(
        x=edge_x,
        y=edge_y,
        line=dict(width=1, color="#94a3b8"),
        hoverinfo="none",
        mode="lines",
    )

    node_x, node_y, node_text, node_color, node_size = [], [], [], [], []
    for node, attr in g.nodes(data=True):
        x, y = pos[node]
        ntype = attr.get("node_type", "company")
        node_x.append(x)
        node_y.append(y)
        node_text.append(f"{node}<br>type: {ntype}")
        node_color.append("#7c3aed" if node == center else NODE_TYPE_COLOR.get(ntype, "#64748b"))
        node_size.append(28 if node == center else 20)

    node_trace = go.Scatter(
        x=node_x,
        y=node_y,
        mode="markers+text",
        text=list(g.nodes),
        textposition="top center",
        hovertext=node_text,
        hoverinfo="text",
        marker=dict(size=node_size, color=node_color, line=dict(width=1, color="white")),
    )

    fig = go.Figure(data=[edge_trace, node_trace])
    fig.update_layout(
        showlegend=False,
        margin=dict(l=10, r=10, t=20, b=10),
        xaxis=dict(showgrid=False, zeroline=False, visible=False),
        yaxis=dict(showgrid=False, zeroline=False, visible=False),
        paper_bgcolor="white",
        plot_bgcolor="white",
        height=650,
    )
    return fig
