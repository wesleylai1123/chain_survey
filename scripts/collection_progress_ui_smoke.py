from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts"
DATA_ROOT = ART / "persistent" / "factor_validation"
DATA_ROOT.mkdir(parents=True, exist_ok=True)
(DATA_ROOT / "batches").mkdir(parents=True, exist_ok=True)

status = DATA_ROOT / "collection_status.json"
manifest = DATA_ROOT / "cache_manifest_latest.json"
universe = DATA_ROOT / "taiwan_stock_universe.csv"
batch = DATA_ROOT / "batches" / "factor_batch_000.csv"

if not status.exists():
    status.write_text(json.dumps({
        "updated_at": "2026-09-11T01:19:57+00:00",
        "universe_companies": 1966,
        "batch_size": 25,
        "total_batches": 79,
        "completed_batches": [0],
        "completed_batch_count": 1,
        "pending_batch_count": 78,
        "next_batch": 1,
        "companies_materialized": 25,
        "factor_rows": 650,
    }), encoding="utf-8")
if not manifest.exists():
    entries = {}
    for stock in ("1101", "1102", "1103"):
        for dataset in (
            "TaiwanStockFinancialStatements", "TaiwanStockBalanceSheet", "TaiwanStockCashFlowsStatement",
            "TaiwanStockMonthRevenue", "TaiwanStockPrice", "TaiwanStockPER",
        ):
            entries[f"{stock}:{dataset}"] = {
                "stock_id": stock, "dataset_key": dataset, "start_date": "2020-01-01", "end_date": "2026-09-11",
                "row_count": 100, "status": "success", "last_success": "2026-09-11T01:19:57+00:00", "error": None,
                "source": "FinMind",
            }
    manifest.write_text(json.dumps({"version": 1, "updated_at": "smoke", "entries": entries}), encoding="utf-8")
if not universe.exists():
    universe.write_text("stock_id,ticker,name,market,sector,industry\n1101,1101.TW,TCC,twse,Cement,Cement\n1102,1102.TW,Asia Cement,twse,Cement,Cement\n", encoding="utf-8")
if not batch.exists():
    batch.write_text("stock_id,report_date\n1101,2020-03-31\n1101,2020-06-30\n1102,2020-03-31\n1102,2020-06-30\n", encoding="utf-8")

env = os.environ.copy()
env["COLLECTION_PROGRESS_ROOT"] = str(DATA_ROOT)
proc = subprocess.Popen(["python", "app/collection_progress_dashboard.py"], cwd=ROOT, env=env)
try:
    time.sleep(3)
    out = ART / "collection-progress-dashboard.png"
    subprocess.run(["scrot", str(out)], check=True)
    if not out.exists() or out.stat().st_size == 0:
        raise RuntimeError("screenshot not created")
    print(f"COLLECTION_PROGRESS_UI_SMOKE_OK {out}")
finally:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
