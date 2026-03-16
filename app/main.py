import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from core.data_loader import load_companies, load_edges, load_events, load_financials, load_products

st.set_page_config(
    page_title="Fundamental Chain Reaction Platform",
    page_icon="FCR",
    layout="wide",
    initial_sidebar_state="expanded",
)

companies = load_companies()
products = load_products()
edges = load_edges()
events = load_events()
financials = load_financials()

st.title("Fundamental Chain Reaction Platform")
st.caption(
    "A Streamlit MVP for exploring company relationships, event propagation, and basic financial snapshots."
)

with st.sidebar:
    st.header("MVP Scope")
    st.markdown(
        """
- Company profiles
- Supply chain and dependency links
- Event impact simulation
- Simple financial snapshots
        """
    )
    st.divider()
    st.write(f"Companies: {len(companies)}")
    st.write(f"Products: {len(products)}")
    st.write(f"Links: {len(edges)}")
    st.write(f"Events: {len(events)}")

metrics = st.columns(4)
metrics[0].metric("Companies", len(companies))
metrics[1].metric("Products", len(products))
metrics[2].metric("Relationships", len(edges))
metrics[3].metric("Financial Rows", len(financials))

c1, c2 = st.columns([1.2, 1])

with c1:
    st.subheader("What this demo shows")
    st.markdown(
        """
1. Browse a compact graph of companies, products, and market exposure.
2. Trace upstream and downstream relationships from a selected company.
3. Simulate predefined events and estimate which companies are affected.
4. Review a lightweight financial snapshot for each company.
        """
    )

with c2:
    st.subheader("Sample coverage")
    event_names = ", ".join(event["name"] for event in events)
    st.info(
        "The current dataset is a small MVP sample focused on relationship mapping and event propagation.\n\n"
        f"Included events: {event_names}"
    )

st.divider()
st.success("Trial run passed: the app loads, the sample data is readable, and Streamlit starts successfully.")
