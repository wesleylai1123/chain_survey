from __future__ import annotations

from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
import time

import pandas as pd
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/"data"/"history"/"tpca_industry_history.csv"
BASE="https://www.tpca.org.tw/web/"
LIST_URL=BASE+"list_news.php?PageNum={page}&menu_no=312&mod_no=184"

PATTERNS=[
    ("pcb_revenue_yoy", re.compile(r"(20\d{2})年(\d{1,2})月.*?PCB上市櫃營收\s*YoY\s*([+-]?\d+(?:\.\d+)?)%",re.I), "Networking","physical_throughput"),
    ("pcb_material_revenue_yoy", re.compile(r"(20\d{2})年(\d{1,2})月.*?PCB原物料營收\s*YoY\s*([+-]?\d+(?:\.\d+)?)%",re.I), "CCL","physical_throughput"),
    ("ccl_import_yoy", re.compile(r"(20\d{2})年(\d{1,2})月.*?CCL\s*進口\s*YoY\s*([+-]?\d+(?:\.\d+)?)%",re.I), "CCL","market_tightness"),
    ("ccl_export_yoy", re.compile(r"(20\d{2})年(\d{1,2})月.*?CCL\s*出口\s*YoY\s*([+-]?\d+(?:\.\d+)?)%",re.I), "CCL","physical_throughput"),
    ("rigid_pcb_export_yoy", re.compile(r"(20\d{2})年(\d{1,2})月.*?硬板出口\s*YoY\s*([+-]?\d+(?:\.\d+)?)%",re.I), "Networking","physical_throughput"),
]


def _fetch(url: str, timeout: int=30) -> str:
    req=Request(url,headers={"User-Agent":"Mozilla/5.0 chain_survey research bot"})
    with urlopen(req,timeout=timeout) as resp:
        return resp.read().decode("utf-8",errors="ignore")


def parse_list_page(html: str, min_year: int) -> list[dict]:
    soup=BeautifulSoup(html,"lxml")
    rows=[]
    for a in soup.find_all("a",href=True):
        title=" ".join(a.get_text(" ",strip=True).split())
        if not title:
            continue
        matched=None
        for metric_id,pattern,chain,dimension in PATTERNS:
            m=pattern.search(title)
            if m:
                matched=(metric_id,m,chain,dimension)
                break
        if not matched:
            continue
        metric_id,m,chain,dimension=matched
        year,month,value=int(m.group(1)),int(m.group(2)),float(m.group(3))
        if year < min_year:
            continue
        context=a.parent.get_text(" ",strip=True) if a.parent else title
        date_match=re.search(r"(20\d{2})[-/](\d{2})[-/](\d{2})",context)
        if not date_match and a.parent and a.parent.parent:
            context=a.parent.parent.get_text(" ",strip=True)
            date_match=re.search(r"(20\d{2})[-/](\d{2})[-/](\d{2})",context)
        if date_match:
            publish=pd.Timestamp(
                year=int(date_match.group(1)),month=int(date_match.group(2)),day=int(date_match.group(3)),
                hour=23,minute=59,second=59,tz="Asia/Taipei"
            )
        else:
            # Conservative fallback: use month end + 31 days, never earlier than the observation period.
            publish=pd.Timestamp(year=year,month=month,day=1,tz="Asia/Taipei")+pd.offsets.MonthEnd(1)+pd.Timedelta(days=31)
        period=pd.Timestamp(year=year,month=month,day=1,tz="Asia/Taipei")+pd.offsets.MonthEnd(1)
        rows.append({
            "metric_id":metric_id,
            "period":f"{year:04d}-{month:02d}",
            "period_date":period.isoformat(),
            "published_at":publish.isoformat(),
            "change_pct":value,
            "chain":chain,
            "dimension":dimension,
            "title":title,
            "source_url":urljoin(BASE,a["href"]),
            "source":"TPCA public industry chart",
            "knowledge_time_method":"page_publication_date",
        })
    return rows


def backfill(min_year: int=2023,max_pages: int=40,delay: float=0.0,workers: int=4) -> pd.DataFrame:
    rows=[]
    failures=[]
    def load(page: int):
        if delay:
            time.sleep(delay * ((page - 1) % max(workers,1)))
        html=_fetch(LIST_URL.format(page=page), timeout=12)
        return page, parse_list_page(html,min_year)

    with ThreadPoolExecutor(max_workers=max(1,workers)) as pool:
        futures={pool.submit(load,page):page for page in range(1,max_pages+1)}
        for future in as_completed(futures):
            page=futures[future]
            try:
                _,parsed=future.result()
                rows.extend(parsed)
            except Exception as exc:
                failures.append((page,str(exc)))
                print(f"TPCA_PAGE_SKIP page={page} {exc}")
    if failures:
        print(f"TPCA_BACKFILL_WARN failures={len(failures)}")
    if not rows:
        raise RuntimeError("TPCA history backfill returned no matching rows")
    frame=pd.DataFrame(rows)
    frame=frame.drop_duplicates(["metric_id","period"],keep="first").sort_values(["period","metric_id"])
    return frame.reset_index(drop=True)


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--min-year",type=int,default=2023)
    parser.add_argument("--max-pages",type=int,default=40)
    parser.add_argument("--delay",type=float,default=0.0)
    parser.add_argument("--workers",type=int,default=4)
    parser.add_argument("--output",type=Path,default=OUTPUT)
    args=parser.parse_args()
    frame=backfill(args.min_year,args.max_pages,args.delay,args.workers)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    frame.to_csv(args.output,index=False)
    counts=frame.groupby("metric_id")["period"].nunique().to_dict()
    print(f"TPCA_HISTORY_OK rows={len(frame)} metrics={counts}")


if __name__=="__main__":
    main()
