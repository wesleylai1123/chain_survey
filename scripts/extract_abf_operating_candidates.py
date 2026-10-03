from __future__ import annotations

from io import BytesIO
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import quote, urlsplit, urlunsplit
import argparse
import hashlib
import re

import pandas as pd
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1]
MANIFEST=ROOT/"artifacts"/"abf_source_manifest.csv"
OUTPUT=ROOT/"artifacts"/"abf_operating_candidates.csv"

USE_FOR_BY_DATA_ID={
    "abf_utilization_history":{"utilization"},
    "abf_product_mix_history":{"product_mix"},
    "abf_capacity_history":{"capacity"},
    "company_guidance_history":{"guidance"},
    "order_cancellation":{"downside"},
    "customer_inventory_correction":{"downside"},
    "abf_backlog_orders":{"guidance","downside"},
    "abf_lead_time":{"guidance","capacity"},
    "abf_asp_history":{"guidance","product_mix","downside"},
}
ABF_CONTEXT=re.compile(r"(?:\bABF\b|IC\s*substrate|IC載板|載板|FCBGA|flip[- ]?chip\s*BGA)",re.I)

PATTERNS=[
    ("abf_utilization_history","UTILIZATION_RANGE",re.compile(r"(?:ABF[^\n]{0,80})?(?:utilization|loading|稼動率)[^\n]{0,60}?(\d{1,3}(?:\.\d+)?)\s*[-~–至]\s*(\d{1,3}(?:\.\d+)?)\s*%",re.I),"percent"),
    ("abf_utilization_history","UTILIZATION_EXACT",re.compile(r"(?:ABF[^\n]{0,80})?(?:utilization|loading|稼動率)[^\n]{0,60}?(\d{1,3}(?:\.\d+)?)\s*%",re.I),"percent"),
    ("abf_utilization_history","FULL_UTILIZATION",re.compile(r"(?:ABF[^\n]{0,80})?(?:full utilization|fully utilized|滿載|滿產)",re.I),None),
    ("abf_product_mix_history","ABF_MIX",re.compile(r"ABF[^\n]{0,50}?(\d{1,3}(?:\.\d+)?)\s*%",re.I),"percent"),
    ("abf_product_mix_history","BT_MIX",re.compile(r"BT[^\n]{0,50}?(\d{1,3}(?:\.\d+)?)\s*%",re.I),"percent"),
    ("abf_capacity_history","CAPACITY_EXPANSION",re.compile(r"(?:ABF[^\n]{0,100})?(?:capacity expansion|expand capacity|new line|expansion|擴產|擴充產能|新產線)",re.I),None),
    ("company_guidance_history","GUIDANCE_UP",re.compile(r"(?:outlook|guidance|展望|需求)[^\n]{0,80}(?:increase|grow|improve|strong|recovery|成長|增加|改善|回升|強勁)",re.I),None),
    ("company_guidance_history","GUIDANCE_DOWN",re.compile(r"(?:outlook|guidance|展望|需求)[^\n]{0,80}(?:decline|weaker|soft|decrease|下滑|疲弱|減少|轉弱)",re.I),None),
    ("order_cancellation","ORDER_CUT",re.compile(r"(?:order cut|order cancellation|cut order|砍單|取消訂單|訂單下修)",re.I),None),
    ("customer_inventory_correction","INVENTORY_CORRECTION",re.compile(r"(?:inventory correction|inventory adjustment|庫存調整|庫存去化|去庫存)",re.I),None),
    ("abf_backlog_orders","ORDER_VISIBILITY",re.compile(r"(?:order visibility|backlog|訂單能見度|在手訂單)",re.I),None),
    ("abf_lead_time","LEAD_TIME",re.compile(r"(?:lead time|交期)[^\n]{0,60}?(\d+(?:\.\d+)?)\s*(week|weeks|週|month|months|月)",re.I),None),
    ("abf_asp_history","PRICE_UP",re.compile(r"(?:ABF[^\n]{0,80})?(?:price increase|price hike|raise price|漲價|價格上調)",re.I),None),
    ("abf_asp_history","PRICE_DOWN",re.compile(r"(?:ABF[^\n]{0,80})?(?:price pressure|price cut|降價|價格下滑|價格壓力)",re.I),None),
]


def _safe_url(url: str) -> str:
    parts=urlsplit(url)
    return urlunsplit((parts.scheme,parts.netloc,quote(parts.path),parts.query,parts.fragment))


def fetch_pdf(url: str, timeout: int=25) -> bytes:
    req=Request(_safe_url(url),headers={
        "User-Agent":"Mozilla/5.0 chain_survey/1.0 research collector",
        "Accept":"application/pdf,*/*;q=0.8",
    })
    with urlopen(req,timeout=timeout) as resp:
        return resp.read()


def pdf_pages(pdf_bytes: bytes) -> list[str]:
    reader=PdfReader(BytesIO(pdf_bytes))
    return [" ".join((page.extract_text() or "").split()) for page in reader.pages]


def _excerpt(text: str, start: int, end: int, radius: int=120) -> str:
    lo=max(0,start-radius); hi=min(len(text),end+radius)
    return text[lo:hi].strip()


def extract_candidates_from_pages(
    stock_id: str,
    company: str,
    source_id: str,
    document_url: str,
    pages: list[str],
    document_sha256: str="",
    use_for: str="guidance;utilization;product_mix;capacity;downside",
) -> pd.DataFrame:
    rows=[]
    permissions={x.strip() for x in str(use_for).split(";") if x.strip()}
    for page_no,text in enumerate(pages,start=1):
        if not text:
            continue
        for data_id,signal_type,pattern,unit in PATTERNS:
            if not (USE_FOR_BY_DATA_ID.get(data_id,set()) & permissions):
                continue
            for m in pattern.finditer(text):
                excerpt=_excerpt(text,m.start(),m.end())
                page_has_abf=bool(ABF_CONTEXT.search(text))
                if data_id.startswith("abf_") and not (ABF_CONTEXT.search(excerpt) or page_has_abf):
                    continue
                value=value_low=value_high=pd.NA
                direction="NEUTRAL"
                if signal_type=="UTILIZATION_RANGE":
                    value_low=float(m.group(1)); value_high=float(m.group(2)); value=(value_low+value_high)/2
                elif signal_type in {"UTILIZATION_EXACT","ABF_MIX","BT_MIX"}:
                    value=float(m.group(1))
                elif signal_type=="LEAD_TIME":
                    value=float(m.group(1)); unit=m.group(2)
                elif signal_type in {"GUIDANCE_UP","PRICE_UP","CAPACITY_EXPANSION","FULL_UTILIZATION","ORDER_VISIBILITY"}:
                    direction="UP"
                elif signal_type in {"GUIDANCE_DOWN","PRICE_DOWN","ORDER_CUT","INVENTORY_CORRECTION"}:
                    direction="DOWN"
                rows.append({
                    "source_id":source_id,"stock_id":str(stock_id),"company":company,
                    "document_url":document_url,"document_sha256":document_sha256,
                    "source_page":page_no,"data_id":data_id,"signal_type":signal_type,
                    "direction":direction,"value":value,"value_low":value_low,"value_high":value_high,
                    "unit":unit or "event","source_excerpt":excerpt,
                    "source_permission":";".join(sorted(permissions)),
                    "scope_gate":"ABF_CONTEXT" if data_id.startswith("abf_") else "SOURCE_PERMISSION",
                    "extraction_rule":pattern.pattern,"review_status":"CANDIDATE",
                })
    if not rows:
        return pd.DataFrame(columns=[
            "source_id","stock_id","company","document_url","document_sha256","source_page",
            "data_id","signal_type","direction","value","value_low","value_high","unit",
            "source_excerpt","source_permission","scope_gate","extraction_rule","review_status",
        ])
    return pd.DataFrame(rows).drop_duplicates(
        ["stock_id","document_url","source_page","data_id","signal_type","source_excerpt"]
    ).reset_index(drop=True)


def extract_manifest(manifest: pd.DataFrame, *, timeout: int=25, max_documents: int=120, best_effort: bool=True) -> tuple[pd.DataFrame,pd.DataFrame]:
    candidates=[]; status=[]
    docs=manifest.copy()
    if "document_kind" in docs:
        docs=docs[docs["document_kind"].eq("PDF")]
    docs=docs.drop_duplicates(["stock_id","document_url"]).head(max_documents)
    for _,row in docs.iterrows():
        url=str(row["document_url"])
        try:
            body=fetch_pdf(url,timeout=timeout)
            digest=hashlib.sha256(body).hexdigest()
            pages=pdf_pages(body)
            found=extract_candidates_from_pages(
                str(row["stock_id"]),str(row["company"]),str(row["source_id"]),url,pages,digest,str(row.get("use_for",""))
            )
            if not found.empty:
                candidates.append(found)
            status.append({
                "source_id":row["source_id"],"stock_id":row["stock_id"],"document_url":url,
                "status":"OK","pages":len(pages),"candidate_count":len(found),"sha256":digest,"error":"",
            })
        except Exception as exc:
            status.append({
                "source_id":row.get("source_id",""),"stock_id":row.get("stock_id",""),"document_url":url,
                "status":"ERROR","pages":0,"candidate_count":0,"sha256":"","error":str(exc),
            })
            if not best_effort:
                raise
    out=pd.concat(candidates,ignore_index=True) if candidates else extract_candidates_from_pages("","","","",[])
    return out,pd.DataFrame(status)


def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument("--manifest",type=Path,default=MANIFEST)
    p.add_argument("--output",type=Path,default=OUTPUT)
    p.add_argument("--status-output",type=Path,default=ROOT/"artifacts"/"abf_document_extract_status.csv")
    p.add_argument("--timeout",type=int,default=25)
    p.add_argument("--max-documents",type=int,default=120)
    p.add_argument("--strict",action="store_true")
    args=p.parse_args()

    manifest=pd.read_csv(args.manifest,dtype={"stock_id":str})
    candidates,status=extract_manifest(
        manifest,timeout=args.timeout,max_documents=args.max_documents,best_effort=not args.strict
    )
    args.output.parent.mkdir(parents=True,exist_ok=True)
    candidates.to_csv(args.output,index=False)
    status.to_csv(args.status_output,index=False)

    counts=candidates.groupby(["stock_id","data_id"]).size().to_dict() if not candidates.empty else {}
    print(f"ABF_OPERATING_CANDIDATES_OK documents={len(status)} candidates={len(candidates)} counts={counts}")


if __name__=="__main__":
    main()
