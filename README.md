# Fundamental Chain Reaction Platform

A cross-platform desktop GUI for exploring company relationships, event propagation, and basic financial snapshots.

## Features

- Company explorer with profile, products, upstream/downstream links, and financial trend chart
- Event simulator with impact scores and affected-company table
- Relationship graph viewer centered on a selected company
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

## Data Files

- `data/companies.csv`: company master data
- `data/products.csv`: product catalog
- `data/edges.csv`: relationship edges across companies, products, and markets
- `data/events.json`: event simulation definitions
- `data/financials.csv`: financial snapshot history

## Relationship Types

- `produces`
- `supplier_of`
- `customer_of`
- `depends_on`
- `belongs_to`
- `exposed_to`
