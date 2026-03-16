from __future__ import annotations

import pandas as pd

from core.data_loader import load_companies, load_edges, load_products


def get_company_profile(company_name: str) -> dict:
    companies = load_companies()
    row = companies.loc[companies["name"] == company_name]
    if row.empty:
        raise ValueError(f"Company not found: {company_name}")
    return row.iloc[0].to_dict()



def get_company_products(company_name: str) -> pd.DataFrame:
    edges = load_edges()
    products = load_products()
    rel = edges[(edges["source"] == company_name) & (edges["relation"] == "produces")]
    return products[products["name"].isin(rel["target"].tolist())]



def get_related_companies(company_name: str, relation: str | None = None) -> pd.DataFrame:
    edges = load_edges()
    mask = (edges["source"] == company_name) | (edges["target"] == company_name)
    rel_df = edges[mask].copy()
    if relation:
        rel_df = rel_df[rel_df["relation"] == relation]
    return rel_df



def get_upstream_downstream(company_name: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    edges = load_edges()
    upstream = edges[(edges["target"] == company_name) & (edges["relation"].isin(["supplier_of", "depends_on"]))].copy()
    downstream = edges[(edges["source"] == company_name) & (edges["relation"].isin(["supplier_of", "customer_of", "exposed_to"]))].copy()
    return upstream, downstream
