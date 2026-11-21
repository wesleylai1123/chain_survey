from __future__ import annotations

from pathlib import Path
from io import StringIO
from urllib.request import Request, urlopen
import argparse
import re

import pandas as pd
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/"data"/"history"/"trendforce_public_price_history.csv"
URL="https://www.trendforce.com/price/dram/dram_contract"


def _fetch(timeout: int=30) -> str:
    req=Request(URL,headers={"User-Agent":"Mozilla/5.0 chain_survey research bot"})
    with urlopen(req,timeout=timeout) as resp:
        return resp.read().decode("utf-8",errors="ignore")


def _parse_percent(text: str) -> float:
    m=re.search(r"([+-]?\d+(?:\.\d+)?)\s*%",text.replace("▲","+").replace("▼","-"))
    if not m:
        raise ValueError(f"No percentage in {text!r}")
    return float(m.group(1))


def parse_public_page(html: str) -> pd.DataFrame:
    soup=BeautifulSoup(html,"lxml")
    text=" ".join(soup.get_text(" ",strip=True).split())
    update_matches=re.findall(r"Last Update\s+(20\d{2}-\d{2}-\d{2})\s+(\d{2}:\d{2})\s*\(GMT\+8\)",text)
    if not update_matches:
        raise ValueError("TrendForce Last Update timestamp not found")
    tables=pd.read_html(StringIO(html))
    rows=[]
    # Identify rows by stable product names across all public tables.
    wanted={
        "DDR5 16Gb (2Gx8) 4800/5600":("dram_spot_ddr5_16gb","spot"),
        "DDR5 8GB SO-DIMM":("dram_contract_ddr5_8gb_sodimm","contract"),
        "DDR4 16GB SO-DIMM":("dram_contract_ddr4_16gb_sodimm","contract"),
    }
    # Page order currently exposes spot first, contract second. Use table columns to infer section.
    for table in tables:
        cols=[" ".join([str(x) for x in c if "Unnamed" not in str(x)]).strip() if isinstance(c,tuple) else str(c) for c in table.columns]
        table=table.copy(); table.columns=cols
        first_col=cols[0] if cols else ""
        for _,r in table.iterrows():
            item=str(r.iloc[0]).strip()
            if item not in wanted:
                continue
            metric_id,kind=wanted[item]
            change_col=next((c for c in cols if "Change" in c),None)
            avg_col=next((c for c in cols if "Session Average" in c),None)
            if not change_col:
                continue
            change=_parse_percent(str(r[change_col]))
            avg=float(str(r[avg_col]).replace(",","")) if avg_col and pd.notna(r[avg_col]) else pd.NA
            # Spot is the freshest update; contract uses the next Last Update marker on the public page.
            idx=0 if kind=="spot" else min(1,len(update_matches)-1)
            d,t=update_matches[idx]
            published=pd.Timestamp(f"{d} {t}",tz="Asia/Taipei")
            rows.append({
                "metric_id":metric_id,
                "kind":kind,
                "product":item,
                "observed_at":published.isoformat(),
                "published_at":published.isoformat(),
                "session_average":avg,
                "change_pct":change,
                "source_url":URL,
                "source":"TrendForce public DRAM price page",
                "knowledge_time_method":"page_last_update",
            })
    if not rows:
        raise RuntimeError("No TrendForce public rows parsed")
    return pd.DataFrame(rows)


def append_history(current: pd.DataFrame, path: Path=OUTPUT) -> pd.DataFrame:
    if path.exists():
        old=pd.read_csv(path)
        combined=pd.concat([old,current],ignore_index=True,sort=False)
    else:
        combined=current.copy()
    return combined.drop_duplicates(["metric_id","published_at"],keep="last").sort_values(["published_at","metric_id"]).reset_index(drop=True)


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,default=OUTPUT)
    args=parser.parse_args()
    current=parse_public_page(_fetch())
    history=append_history(current,args.output)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    history.to_csv(args.output,index=False)
    print(f"TRENDFORCE_PUBLIC_HISTORY_OK rows={len(history)} new={len(current)}")


if __name__=="__main__":
    main()
