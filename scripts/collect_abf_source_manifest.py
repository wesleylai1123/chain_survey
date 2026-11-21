from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
import argparse
import csv
import hashlib
import time

import pandas as pd
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
REGISTRY=ROOT/"data"/"abf_source_registry.csv"
OUTPUT=ROOT/"artifacts"/"abf_source_manifest.csv"


@dataclass(frozen=True)
class FetchResult:
    url: str
    status: str
    content_type: str
    body: bytes
    error: str=""


def load_registry(path: str | Path=REGISTRY) -> pd.DataFrame:
    frame=pd.read_csv(path,dtype={"stock_id":str})
    required={
        "source_id","stock_id","company","source_type","source_url","source_host",
        "primary","use_for","parser_type","refresh_cadence","health_selector",
        "fallback_source_id","notes",
    }
    missing=required-set(frame.columns)
    if missing:
        raise ValueError(f"ABF source registry missing columns: {sorted(missing)}")
    if frame["source_id"].duplicated().any():
        raise ValueError("ABF source_id must be unique")
    if not frame["primary"].astype(str).str.lower().eq("true").all():
        raise ValueError("ABF calibration registry accepts only primary sources")
    known=set(frame["source_id"])
    bad=sorted(set(frame.loc[frame["fallback_source_id"].fillna("").ne(""),"fallback_source_id"])-known)
    if bad:
        raise ValueError(f"Unknown fallback source ids: {bad}")
    return frame


def fetch(url: str, *, timeout: int=15, retries: int=2, delay: float=0.5) -> FetchResult:
    last=""
    for attempt in range(retries+1):
        try:
            req=Request(url,headers={
                "User-Agent":"Mozilla/5.0 chain_survey/1.0 research collector",
                "Accept":"text/html,application/xhtml+xml,application/pdf,application/json;q=0.9,*/*;q=0.8",
            })
            with urlopen(req,timeout=timeout) as resp:
                body=resp.read()
                ctype=str(resp.headers.get("Content-Type","")).split(";")[0].strip().lower()
                return FetchResult(resp.geturl(),str(getattr(resp,"status",200)),ctype,body)
        except Exception as exc:
            last=str(exc)
            if attempt < retries and delay:
                time.sleep(delay*(attempt+1))
    return FetchResult(url,"ERROR","",b"",last)


def _decode(body: bytes) -> str:
    for enc in ("utf-8","big5","cp950"):
        try:
            return body.decode(enc)
        except UnicodeDecodeError:
            continue
    return body.decode("utf-8",errors="ignore")


def extract_links(html: str, base_url: str) -> list[dict[str,str]]:
    soup=BeautifulSoup(html,"lxml")
    rows=[]
    for node in soup.find_all(["a","iframe","source"]):
        raw=node.get("href") or node.get("src")
        if not raw:
            continue
        url=urljoin(base_url,raw)
        parsed=urlparse(url)
        if parsed.scheme not in {"http","https"}:
            continue
        label=" ".join(node.get_text(" ",strip=True).split())
        lower=(url+" "+label).lower()
        kind=(
            "PDF" if ".pdf" in lower else
            "VIDEO" if any(x in lower for x in ("youtube","webpro","video","youtu.be")) else
            "DOCUMENT" if any(x in lower for x in ("download","report","financial","investor","conference")) else
            "LINK"
        )
        rows.append({"document_url":url,"document_label":label,"document_kind":kind})
    seen=set(); unique=[]
    for row in rows:
        key=row["document_url"]
        if key in seen:
            continue
        seen.add(key); unique.append(row)
    return unique


def discover_source(row: pd.Series, *, timeout: int=15, retries: int=2) -> tuple[list[dict],dict]:
    result=fetch(row["source_url"],timeout=timeout,retries=retries)
    health={
        "source_id":row["source_id"],"stock_id":row["stock_id"],"company":row["company"],
        "source_url":row["source_url"],"fetch_url":result.url,"status":result.status,
        "content_type":result.content_type,"healthy":False,"error":result.error,
    }
    if result.status=="ERROR":
        return [],health

    body_hash=hashlib.sha256(result.body).hexdigest()
    health["sha256"]=body_hash
    text=_decode(result.body) if result.body else ""
    selector=str(row.get("health_selector","") or "").strip()
    health["healthy"]=bool(result.body) and (not selector or selector.lower() in text.lower())
    health["error"]="" if health["healthy"] else f"health selector missing: {selector}"

    links=[]
    if "html" in result.content_type or text.lstrip().startswith("<"):
        for link in extract_links(text,result.url):
            links.append({
                "source_id":row["source_id"],"stock_id":row["stock_id"],"company":row["company"],
                "parser_type":row["parser_type"],"use_for":row["use_for"],
                "source_page_url":result.url,"source_page_sha256":body_hash,
                **link,
            })
    else:
        links.append({
            "source_id":row["source_id"],"stock_id":row["stock_id"],"company":row["company"],
            "parser_type":row["parser_type"],"use_for":row["use_for"],
            "source_page_url":result.url,"source_page_sha256":body_hash,
            "document_url":result.url,"document_label":row["source_type"],
            "document_kind":"DOCUMENT",
        })
    return links,health


def build_manifest(registry: pd.DataFrame, *, timeout: int=15, retries: int=2) -> tuple[pd.DataFrame,pd.DataFrame]:
    manifests=[]; health_rows=[]
    by_id=registry.set_index("source_id",drop=False)
    for _,row in registry.iterrows():
        links,health=discover_source(row,timeout=timeout,retries=retries)
        health_rows.append(health)
        if health["healthy"]:
            manifests.extend(links)
            continue
        fallback=str(row.get("fallback_source_id","") or "").strip()
        if fallback and fallback in by_id.index:
            frow=by_id.loc[fallback]
            flinks,fhealth=discover_source(frow,timeout=timeout,retries=retries)
            fhealth=dict(fhealth); fhealth["fallback_for"]=row["source_id"]
            health_rows.append(fhealth)
            if fhealth["healthy"]:
                for link in flinks:
                    link=dict(link); link["fallback_for"]=row["source_id"]
                    manifests.append(link)
    manifest=pd.DataFrame(manifests)
    if not manifest.empty:
        manifest=manifest.drop_duplicates(["stock_id","document_url"]).sort_values(["stock_id","source_id","document_url"])
    return manifest.reset_index(drop=True),pd.DataFrame(health_rows)


def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument("--registry",type=Path,default=REGISTRY)
    p.add_argument("--output",type=Path,default=OUTPUT)
    p.add_argument("--health-output",type=Path,default=ROOT/"artifacts"/"abf_source_health.csv")
    p.add_argument("--timeout",type=int,default=15)
    p.add_argument("--retries",type=int,default=2)
    args=p.parse_args()
    registry=load_registry(args.registry)
    manifest,health=build_manifest(registry,timeout=args.timeout,retries=args.retries)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    manifest.to_csv(args.output,index=False)
    health.to_csv(args.health_output,index=False)
    healthy=int(health["healthy"].fillna(False).sum()) if not health.empty else 0
    print(f"ABF_SOURCE_DISCOVERY_OK sources={len(registry)} health_rows={len(health)} healthy={healthy} documents={len(manifest)}")
    if healthy < 3:
        raise RuntimeError("Fewer than three ABF primary source endpoints are healthy")


if __name__=="__main__":
    main()
