# Fundamental Chain Reaction Platform

A cross-platform desktop GUI for exploring company relationships, event propagation, and basic financial snapshots.

## Features

- Company explorer with profile, products, upstream/downstream links, and financial trend chart
- Multi-layer event simulator with first-layer, second-layer, and third-layer propagation
- Propagation controls for decay, polarity, lag, and industry/sector sensitivity
- Real-fundamental overlays from official monthly revenue and quarterly statements that modulate event scores
- Relationship graph viewer centered on a selected company
- Formalized data model for companies, products, relationships, event templates, and financial field definitions
- Registry for future real-world data connectors such as monthly revenue, quarterly filings, IR summaries, and news events
- Runs as a local desktop app on Windows, macOS, and WSL Ubuntu 24.04 with GUI support

## Requirements

- Python 3.11+ recommended
- `tkinter` available in the Python runtime
- On WSL Ubuntu 24.04, GUI support via WSLg or another X server

## Install

```bash
python -m venv .venv
```

Activate the environment:

```bash
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```bash
# macOS / WSL Ubuntu
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## Run

```bash
python app/main.py
```

## WSL Ubuntu 24.04 Notes

- If you use modern WSL on Windows 11, WSLg usually provides GUI support out of the box.
- If `tkinter` is missing, install it with:

```bash
sudo apt update
sudo apt install -y python3-tk
```

## Canonical Data Model

- `data/company_master.csv`: company master data
- `data/product_master.csv`: product master data
- `data/company_relationships.csv`: company-to-company relationships
- `data/company_product_relationships.csv`: company-to-product relationships
- `data/product_relationships.csv`: product dependency graph
- `data/product_market_relationships.csv`: product-to-market exposure graph
- `data/event_templates.json`: formal event templates with seed rules and propagation parameters
- `data/financial_field_definitions.csv`: financial metric definitions
- `data/external_data_sources.csv`: registry of planned real-world data sources
- `data/monthly_revenue.csv`: official monthly revenue canonical table
- `data/quarterly_financials.csv`: official quarterly financial canonical table
- `data/data_model_manifest.json`: manifest of the formalized datasets

Legacy demo files remain in `data/companies.csv`, `data/products.csv`, `data/edges.csv`, and `data/events.json`, but the application now prefers the canonical files above.

## Refresh Official TWSE Data

Run the ingestion script to pull the latest official monthly revenue and quarterly financial data for the Taiwan-listed companies in `company_master.csv`:

```bash
python scripts/refresh_twse_data.py
```

The script writes:

- `data/monthly_revenue.csv`
- `data/quarterly_financials.csv`

## Relationship Types

- `produces`
- `supplier_of`
- `customer_of`
- `depends_on`
- `belongs_to`
- `exposed_to`
