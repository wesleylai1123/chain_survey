from __future__ import annotations

from io import StringIO
from pathlib import Path
from urllib.request import Request, urlopen
import argparse
import calendar
import time

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "history" / "mops_abf_monthly_revenue_history.csv"
TARGETS = {
    "3037": ("欣興", "3037.TW"),
    "3189": ("景碩", "3189.TW"),
    "8046": ("南電", "8046.TW"),
}


def _flatten_columns(columns) -> list[str]:
    result=[]
    for col in columns:
        if isinstance(col, tuple):
            parts=[str(x).strip() for x in col if str(x).strip() and "Unnamed" not in str(x)]
            result.append(" ".join(parts))
        else:
            result.append(str(col).strip())
    return result


def _find_col(columns: list[str], needle: str) -> str:
    for col in columns:
        if needle in col:
            return col
    raise KeyError(f"Column containing {needle!r} not found in {columns}")


def _fetch_html(year: int, month: int, timeout: int = 12) -> str:
    roc_year=year-1911
    path=f"/nas/t21/sii/t21sc03_{roc_year}_{month}_0.html"
    errors=[]
    for host in ("https://doc.twse.com.tw", "https://mopsov.twse.com.tw", "https://mops.twse.com.tw"):
        url=host+path
        req=Request(url,headers={"User-Agent":"Mozilla/5.0 chain_survey research bot"})
        try:
            with urlopen(req,timeout=timeout) as resp:
                raw=resp.read()
            for enc in ("big5","cp950","utf-8"):
                try:
                    return raw.decode(enc)
                except UnicodeDecodeError:
                    continue
            return raw.decode("big5",errors="ignore")
        except Exception as exc:
            errors.append(f"{host}: {exc}")
    raise RuntimeError(f"Failed MOPS history {year}-{month:02d}: {'; '.join(errors)}")


def parse_mops_month(html: str, year: int, month: int) -> pd.DataFrame:
    tables=pd.read_html(StringIO(html))
    rows=[]
    for table in tables:
        table=table.copy()
        table.columns=_flatten_columns(table.columns)
        try:
            code_col=_find_col(list(table.columns),"公司代號")
            name_col=_find_col(list(table.columns),"公司名稱")
            revenue_col=_find_col(list(table.columns),"當月營收")
            yoy_col=_find_col(list(table.columns),"去年同月增減")
        except KeyError:
            continue
        for _, row in table.iterrows():
            code=str(row.get(code_col,"")).strip().replace(".0","")
            if code not in TARGETS:
                continue
            revenue=pd.to_numeric(str(row[revenue_col]).replace(",",""),errors="coerce")
            yoy_text=str(row[yoy_col]).replace(",","").replace("%","").strip()
            yoy=pd.to_numeric(yoy_text,errors="coerce")
            if pd.isna(revenue) or pd.isna(yoy):
                continue
            company,ticker=TARGETS[code]
            period_end=pd.Timestamp(year=year,month=month,day=calendar.monthrange(year,month)[1],tz="Asia/Taipei")
            next_month=period_end + pd.offsets.MonthBegin(1)
            # Conservative point-in-time proxy: monthly revenue must be filed by the 10th.
            published=pd.Timestamp(year=next_month.year,month=next_month.month,day=10,hour=23,minute=59,second=59,tz="Asia/Taipei")
            rows.append({
                "company":company,
                "ticker":ticker,
                "period":f"{year:04d}-{month:02d}",
                "period_date":period_end.isoformat(),
                "published_at":published.isoformat(),
                "monthly_revenue":float(revenue),
                "yoy_pct":float(yoy),
                "source":"MOPS historical monthly revenue",
                "source_url":f"https://mopsov.twse.com.tw/nas/t21/sii/t21sc03_{year-1911}_{month}_0.html",
                "knowledge_time_method":"regulatory_deadline_proxy",
            })
    if not rows:
        return pd.DataFrame(columns=[
            "company","ticker","period","period_date","published_at","monthly_revenue","yoy_pct",
            "source","source_url","knowledge_time_method"
        ])
    return pd.DataFrame(rows).drop_duplicates(["ticker","period"]).reset_index(drop=True)


def month_range(start: str, end: str):
    start_ts=pd.Period(start,freq="M")
    end_ts=pd.Period(end,freq="M")
    for p in pd.period_range(start_ts,end_ts,freq="M"):
        yield p.year,p.month


def backfill(start: str, end: str, delay: float = 0.25) -> pd.DataFrame:
    frames=[]
    failures=[]
    for year,month in month_range(start,end):
        try:
            html=_fetch_html(year,month)
            parsed=parse_mops_month(html,year,month)
            if not parsed.empty:
                frames.append(parsed)
        except Exception as exc:
            failures.append((year,month,str(exc)))
            print(f"MOPS_MONTH_SKIP {year}-{month:02d} {exc}")
        if delay:
            time.sleep(delay)
    if failures:
        print(f"MOPS_BACKFILL_WARN failures={len(failures)}")
    if not frames:
        raise RuntimeError("MOPS backfill returned no target rows")
    result=pd.concat(frames,ignore_index=True).drop_duplicates(["ticker","period"]).sort_values(["period","ticker"])
    return result.reset_index(drop=True)


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--from-month",default="2023-01")
    previous_month=(pd.Timestamp.now(tz="Asia/Taipei")-pd.offsets.MonthBegin(1)).strftime("%Y-%m")
    parser.add_argument("--to-month",default=previous_month)
    parser.add_argument("--delay",type=float,default=0.25)
    parser.add_argument("--output",type=Path,default=OUTPUT)
    args=parser.parse_args()
    frame=backfill(args.from_month,args.to_month,args.delay)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    frame.to_csv(args.output,index=False)
    print(f"MOPS_ABF_HISTORY_OK rows={len(frame)} months={frame['period'].nunique()} companies={frame['ticker'].nunique()}")


if __name__=="__main__":
    main()
