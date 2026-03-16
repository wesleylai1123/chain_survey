from __future__ import annotations

import pandas as pd

from core.data_loader import load_financials



def get_company_financials(company_name: str) -> pd.DataFrame:
    df = load_financials().copy()
    out = df[df["company"] == company_name].sort_values("period")
    return out.reset_index(drop=True)



def latest_snapshot(company_name: str) -> dict:
    df = get_company_financials(company_name)
    if df.empty:
        return {}
    return df.iloc[-1].to_dict()
