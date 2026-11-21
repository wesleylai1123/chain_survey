from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from core.operating_correlation_engine import OperatingCorrelationConfig, scan_operating_correlations

HISTORY=ROOT/"data"/"history"/"free_industry_history_panel.csv"
OUT=ROOT/"artifacts"/"operating_correlation_results.csv"

def main() -> None:
    history=pd.read_csv(HISTORY)
    results=scan_operating_correlations(history,config=OperatingCorrelationConfig())
    if results.empty:
        raise RuntimeError("No operating correlation results")
    OUT.parent.mkdir(parents=True,exist_ok=True)
    results.to_csv(OUT,index=False)
    print("OPERATING_CORRELATION_OK",len(results))
    print(results.head(15).to_string(index=False))

if __name__=="__main__":
    main()
