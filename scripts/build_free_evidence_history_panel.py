from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
HISTORY_DIR=ROOT/"data"/"history"
OUTPUT=HISTORY_DIR/"free_industry_history_panel.csv"


def build_mops_panel(path: Path) -> pd.DataFrame:
    frame=pd.read_csv(path)
    rows=[]
    for _,r in frame.iterrows():
        rows.append({
            "source_id":"mops_abf_monthly_revenue",
            "metric_id":f"abf_company_revenue_yoy::{r['ticker']}",
            "entity":r["company"],
            "period":r["period"],
            "period_date":r["period_date"],
            "published_at":r["published_at"],
            "value":r["monthly_revenue"],
            "value_unit":"TWD thousand",
            "change_pct":r["yoy_pct"],
            "chain":"ABF",
            "dimension":"financial_confirmation",
            "source":r["source"],
            "source_url":r["source_url"],
            "knowledge_time_method":r["knowledge_time_method"],
        })
    return pd.DataFrame(rows)


def build_tpca_panel(path: Path) -> pd.DataFrame:
    frame=pd.read_csv(path)
    out=frame.rename(columns={"change_pct":"change_pct"}).copy()
    out["source_id"]="tpca_public_industry"
    out["entity"]="Taiwan PCB industry"
    out["value"]=out["change_pct"]
    out["value_unit"]="percent"
    return out[[
        "source_id","metric_id","entity","period","period_date","published_at","value","value_unit",
        "change_pct","chain","dimension","source","source_url","knowledge_time_method"
    ]]


def build_trendforce_panel(path: Path) -> pd.DataFrame:
    frame=pd.read_csv(path)
    frame["period"]=pd.to_datetime(frame["published_at"],utc=True).dt.strftime("%Y-%m-%d")
    frame["period_date"]=frame["observed_at"]
    frame["entity"]=frame["product"]
    frame["value"]=frame["session_average"]
    frame["value_unit"]="USD"
    frame["chain"]="Memory"
    frame["dimension"]="market_tightness"
    frame["source_id"]="trendforce_public_dram"
    return frame[[
        "source_id","metric_id","entity","period","period_date","published_at","value","value_unit",
        "change_pct","chain","dimension","source","source_url","knowledge_time_method"
    ]]


def build_history_panel(history_dir: Path=HISTORY_DIR) -> pd.DataFrame:
    parts=[]
    mops=history_dir/"mops_abf_monthly_revenue_history.csv"
    tpca=history_dir/"tpca_industry_history.csv"
    tf=history_dir/"trendforce_public_price_history.csv"
    if mops.exists():
        parts.append(build_mops_panel(mops))
    if tpca.exists():
        parts.append(build_tpca_panel(tpca))
    if tf.exists():
        parts.append(build_trendforce_panel(tf))
    if not parts:
        raise RuntimeError("No history source files found")
    panel=pd.concat(parts,ignore_index=True,sort=False)
    panel["period_date"]=pd.to_datetime(panel["period_date"],utc=True,format="mixed")
    panel["published_at"]=pd.to_datetime(panel["published_at"],utc=True,format="mixed")
    if (panel["published_at"] < panel["period_date"]).any():
        bad=panel.loc[panel["published_at"] < panel["period_date"],["source_id","metric_id","period"]]
        raise ValueError(f"Point-in-time violation in history panel: {bad.to_dict('records')}")
    panel=panel.drop_duplicates(["source_id","metric_id","period"],keep="last")
    return panel.sort_values(["period_date","source_id","metric_id"]).reset_index(drop=True)


def coverage_summary(panel: pd.DataFrame) -> pd.DataFrame:
    rows=[]
    for (source,metric),g in panel.groupby(["source_id","metric_id"]):
        rows.append({
            "source_id":source,
            "metric_id":metric,
            "observations":len(g),
            "first_period":g["period_date"].min().date().isoformat(),
            "last_period":g["period_date"].max().date().isoformat(),
            "latest_published_at":g["published_at"].max().isoformat(),
        })
    return pd.DataFrame(rows).sort_values(["source_id","metric_id"]).reset_index(drop=True)


def main() -> None:
    panel=build_history_panel()
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    panel.to_csv(OUTPUT,index=False)
    summary=coverage_summary(panel)
    summary.to_csv(HISTORY_DIR/"free_industry_history_coverage.csv",index=False)
    print(f"FREE_HISTORY_PANEL_OK rows={len(panel)} metrics={panel['metric_id'].nunique()} sources={panel['source_id'].nunique()}")


if __name__=="__main__":
    main()
