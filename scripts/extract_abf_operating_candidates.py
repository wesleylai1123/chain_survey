from __future__ import annotations

from io import BytesIO
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit, urlunsplit
import argparse
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass

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


@dataclass
class PdfFetchResult:
    body: bytes
    sha256: str
    raw_path: str
    fetch_mode: str
    changed: bool
    etag: str
    last_modified: str


def _raw_manifest_path(raw_root: Path) -> Path:
    return raw_root/"manifest.json"


def _load_raw_manifest(raw_root: Path) -> dict:
    path=_raw_manifest_path(raw_root)
    if not path.exists():
        return {"schema_version":"AbfDocumentCacheV1","documents":{}}
    payload=json.loads(path.read_text(encoding="utf-8"))
    payload.setdefault("schema_version","AbfDocumentCacheV1")
    payload.setdefault("documents",{})
    return payload


def _save_raw_manifest(raw_root: Path, manifest: dict) -> None:
    raw_root.mkdir(parents=True,exist_ok=True)
    _raw_manifest_path(raw_root).write_text(
        json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"
    )


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(path.resolve())


def fetch_pdf_conditional(
    url: str,
    *,
    stock_id: str,
    raw_root: Path,
    timeout: int=25,
    retries: int=3,
    backoff_seconds: float=1.0,
) -> PdfFetchResult:
    raw_root.mkdir(parents=True,exist_ok=True)
    manifest=_load_raw_manifest(raw_root)
    entry=manifest["documents"].get(url,{})
    cached_rel=str(entry.get("relative_path","")).strip()
    cached_path=(raw_root/cached_rel) if cached_rel else None
    cache_valid=bool(cached_path and cached_path.exists())

    headers={
        "User-Agent":"Mozilla/5.0 chain_survey/2.0 research collector",
        "Accept":"application/pdf,*/*;q=0.8",
        "Connection":"close",
    }
    if cache_valid and entry.get("etag"):
        headers["If-None-Match"]=str(entry["etag"])
    if cache_valid and entry.get("last_modified"):
        headers["If-Modified-Since"]=str(entry["last_modified"])

    last_error=None
    for attempt in range(retries):
        req=Request(_safe_url(url),headers=headers)
        try:
            with urlopen(req,timeout=timeout) as resp:
                body=resp.read()
                if not body:
                    raise ValueError("empty PDF payload")
                digest=hashlib.sha256(body).hexdigest()
                out=raw_root/str(stock_id)/f"{digest}.pdf"
                out.parent.mkdir(parents=True,exist_ok=True)
                if not out.exists():
                    out.write_bytes(body)
                etag=str(resp.headers.get("ETag","") or "")
                last_modified=str(resp.headers.get("Last-Modified","") or "")
                changed=digest != str(entry.get("sha256",""))
                manifest["documents"][url]={
                    "sha256":digest,
                    "relative_path":str(out.relative_to(raw_root)),
                    "etag":etag,
                    "last_modified":last_modified,
                    "last_checked_at":pd.Timestamp.now(tz="UTC").isoformat(),
                }
                _save_raw_manifest(raw_root,manifest)
                return PdfFetchResult(
                    body=body,sha256=digest,raw_path=_display_path(out),
                    fetch_mode="FULL_GET",changed=changed,etag=etag,last_modified=last_modified,
                )
        except HTTPError as exc:
            if exc.code==304 and cache_valid and cached_path is not None:
                body=cached_path.read_bytes()
                digest=hashlib.sha256(body).hexdigest()
                expected=str(entry.get("sha256",""))
                if expected and digest!=expected:
                    raise RuntimeError(f"cached PDF SHA mismatch for {url}: {digest} != {expected}")
                entry["last_checked_at"]=pd.Timestamp.now(tz="UTC").isoformat()
                manifest["documents"][url]=entry
                _save_raw_manifest(raw_root,manifest)
                return PdfFetchResult(
                    body=body,sha256=digest,raw_path=_display_path(cached_path),
                    fetch_mode="HTTP_304_CACHE",changed=False,
                    etag=str(entry.get("etag","") or ""),
                    last_modified=str(entry.get("last_modified","") or ""),
                )
            last_error=exc
        except Exception as exc:
            last_error=exc
        if attempt+1<retries:
            time.sleep(backoff_seconds*(attempt+1))
    raise RuntimeError(f"PDF fetch failed after {retries} attempts: {url}: {last_error}")


def fetch_pdf(url: str, timeout: int=25, retries: int=3, backoff_seconds: float=1.0) -> bytes:
    last_error=None
    for attempt in range(retries):
        req=Request(_safe_url(url),headers={
            "User-Agent":"Mozilla/5.0 chain_survey/2.0 research collector",
            "Accept":"application/pdf,*/*;q=0.8",
            "Connection":"close",
        })
        try:
            with urlopen(req,timeout=timeout) as resp:
                body=resp.read()
                if not body:
                    raise ValueError("empty PDF payload")
                return body
        except Exception as exc:
            last_error=exc
            if attempt+1>=retries:
                break
            time.sleep(backoff_seconds*(attempt+1))
    raise RuntimeError(f"PDF fetch failed after {retries} attempts: {url}: {last_error}")


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


def extract_manifest(
    manifest: pd.DataFrame,
    *,
    timeout: int=25,
    retries: int=3,
    max_documents: int=120,
    best_effort: bool=True,
    raw_root: Path | None=None,
    pipeline_run_id: str="",
) -> tuple[pd.DataFrame,pd.DataFrame]:
    candidates=[]; status=[]
    docs=manifest.copy()
    if "document_kind" in docs:
        docs=docs[docs["document_kind"].eq("PDF")]
    docs=docs.drop_duplicates(["stock_id","document_url"]).head(max_documents)
    for _,row in docs.iterrows():
        url=str(row["document_url"])
        try:
            fetch_mode="FULL_GET"
            raw_changed=True
            etag=""
            last_modified=""
            if raw_root is not None:
                fetched=fetch_pdf_conditional(
                    url,stock_id=str(row["stock_id"]),raw_root=raw_root,
                    timeout=timeout,retries=retries,
                )
                body=fetched.body
                digest=fetched.sha256
                raw_path=fetched.raw_path
                fetch_mode=fetched.fetch_mode
                raw_changed=fetched.changed
                etag=fetched.etag
                last_modified=fetched.last_modified
            else:
                body=fetch_pdf(url,timeout=timeout,retries=retries)
                digest=hashlib.sha256(body).hexdigest()
                raw_path=""
            pages=pdf_pages(body)
            found=extract_candidates_from_pages(
                str(row["stock_id"]),str(row["company"]),str(row["source_id"]),url,pages,digest,str(row.get("use_for",""))
            )
            if not found.empty:
                found["raw_sha256"]=digest
                found["raw_snapshot_path"]=raw_path
                found["pipeline_run_id"]=pipeline_run_id
                candidates.append(found)
            status.append({
                "source_id":row["source_id"],"stock_id":row["stock_id"],"document_url":url,
                "status":"OK","pages":len(pages),"candidate_count":len(found),"sha256":digest,
                "raw_snapshot_path":raw_path,"pipeline_run_id":pipeline_run_id,
                "fetch_mode":fetch_mode,"raw_changed":raw_changed,
                "etag":etag,"last_modified":last_modified,"error":"",
            })
        except Exception as exc:
            status.append({
                "source_id":row.get("source_id",""),"stock_id":row.get("stock_id",""),"document_url":url,
                "status":"ERROR","pages":0,"candidate_count":0,"sha256":"","raw_snapshot_path":"",
                "pipeline_run_id":pipeline_run_id,"fetch_mode":"ERROR","raw_changed":False,
                "etag":"","last_modified":"","error":str(exc),
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
    p.add_argument("--retries",type=int,default=3)
    p.add_argument("--raw-root",type=Path,default=ROOT/"persistent"/"abf_documents")
    p.add_argument("--max-documents",type=int,default=120)
    p.add_argument("--strict",action="store_true")
    args=p.parse_args()

    run_id=os.environ.get("RESEARCH_PIPELINE_RUN_ID") or os.environ.get("GITHUB_RUN_ID") or pd.Timestamp.now(tz="UTC").strftime("%Y%m%dT%H%M%SZ")
    manifest=pd.read_csv(args.manifest,dtype={"stock_id":str})
    candidates,status=extract_manifest(
        manifest,timeout=args.timeout,retries=args.retries,max_documents=args.max_documents,
        best_effort=not args.strict,raw_root=args.raw_root,pipeline_run_id=run_id
    )
    args.output.parent.mkdir(parents=True,exist_ok=True)
    candidates.to_csv(args.output,index=False)
    status.to_csv(args.status_output,index=False)

    counts=candidates.groupby(["stock_id","data_id"]).size().to_dict() if not candidates.empty else {}
    print(f"ABF_OPERATING_CANDIDATES_OK documents={len(status)} candidates={len(candidates)} counts={counts}")


if __name__=="__main__":
    main()
