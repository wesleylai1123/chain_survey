from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts"
ART.mkdir(exist_ok=True)
manifest = ART / "factor_cache_manifest.json"
universe = ART / "taiwan_stock_universe.csv"
collection_status = ART / "collection_status.json"
if not manifest.exists():
    manifest.write_text(json.dumps({"version":1,"updated_at":"smoke","entries":{
        "2330:prices":{"stock_id":"2330","dataset_key":"prices","start_date":"2020-01-01","end_date":"2026-09-10","row_count":1600,"status":"success","last_success":"2026-09-10T00:00:00+00:00","error":None,"source":"FinMind"},
        "2454:valuation":{"stock_id":"2454","dataset_key":"valuation","start_date":"2020-01-01","end_date":"2026-09-10","row_count":0,"status":"failed","last_success":None,"error":"smoke failure","source":"FinMind"}
    }}), encoding="utf-8")
if not universe.exists():
    universe.write_text("stock_id,ticker,name,market,sector,industry\n2330,2330.TW,TSMC,twse,Semiconductor,Semiconductor\n2454,2454.TW,MediaTek,twse,Semiconductor,Semiconductor\n", encoding="utf-8")
collection_status.write_text(json.dumps({
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

env = os.environ.copy()
env["FACTOR_CACHE_MANIFEST"] = str(manifest)
env["TAIWAN_UNIVERSE"] = str(universe)
env["FACTOR_COLLECTION_STATUS"] = str(collection_status)
proc = subprocess.Popen(["python", "app/full_universe_runner.py"], cwd=ROOT, env=env)
try:
    time.sleep(3)
    out = ART / "full-universe-runner.png"
    subprocess.run(["scrot", str(out)], check=True)
    if not out.exists() or out.stat().st_size == 0:
        raise RuntimeError("screenshot not created")
    print(f"FULL_UNIVERSE_UI_SMOKE_OK {out}")
finally:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
