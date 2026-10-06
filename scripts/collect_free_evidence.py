from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.free_evidence_connectors import (
    DATA_GOV_METADATA,
    extract_data_gov_resource_url,
    fetch_bytes,
    load_source_config,
    parse_moea_export_orders_csv,
    parse_monthly_revenue_json,
    parse_tpca_listing,
)
from scripts.build_real_point_in_time_evidence import normalize_yoy_to_signal

DEFAULT_RELATIONS = ROOT / "data" / "company_product_relationships.csv"
DEFAULT_COMPANIES = ROOT / "data" / "company_master.csv"
DEFAULT_PERSISTENT = ROOT / "persistent" / "free_evidence"
DEFAULT_ARTIFACTS = ROOT / "artifacts"

PRODUCT_CHAIN = {
    "ABF Substrate": "ABF",
    "BT Substrate": "ABF",
    "3nm/4nm Wafer": "Foundry",
    "DRAM/NAND": "Memory",
    "HBM": "HBM",
    "CCL": "CCL",
    "High-speed PCB": "Networking",
}


def parse_month_period(value: Any) -> pd.Timestamp | None:
    text = str(value).strip()
    digits = re.sub(r"\D", "", text)
    if text.isdigit() and len(digits) in {5, 6}:
        y, mo = int(digits[:-2]), int(digits[-2:])
    else:
        m = re.search(r"(?P<y>\d{3,4})\D+(?P<m>\d{1,2})(?:月)?$", text)
        if not m:
            return None
        y, mo = int(m.group("y")), int(m.group("m"))
    if y < 1911:
        y += 1911
    if not 1 <= mo <= 12:
        return None
    return pd.Timestamp(year=y, month=mo, day=1)


def _evidence_row(
    *,
    evidence_id: str,
    dimension: str,
    chain: str,
    indicator: str,
    available_at: pd.Timestamp,
    yoy_pct: float,
    source_type: str,
    reliability_prior: float,
    source: str,
    source_id: str,
    evidence_group: str,
    period_date: str = "",
    notes: str = "",
    exposure_weight: float | None = None,
    exposure_basis: str = "",
) -> dict[str, Any]:
    return {
        "evidence_id": evidence_id,
        "theme": "AI Infrastructure",
        "dimension": dimension,
        "chain": chain,
        "evidence_group": evidence_group,
        "indicator": indicator,
        "period_date": period_date,
        "published_at": available_at,
        "as_of_date": available_at,
        "raw_value": yoy_pct,
        "raw_unit": "YoY %",
        "yoy_pct": yoy_pct,
        "signal": normalize_yoy_to_signal(yoy_pct),
        "source_type": source_type,
        "reliability": reliability_prior,
        "reliability_basis": "SOURCE_CLASS_PRIOR",
        "half_life_days": 90,
        "source": source,
        "notes": notes,
        "transform": "clip(yoy_pct / 100, -1, 1)",
        "transform_version": "yoy_linear_v1",
        "provenance": "LIVE_FREE_POINT_IN_TIME",
        "source_id": source_id,
        "availability_policy": "collection_time_conservative",
        "collected_at": available_at,
        "exposure_weight": exposure_weight,
        "exposure_basis": exposure_basis,
    }


def revenue_snapshot_to_evidence(
    frame: pd.DataFrame,
    relationships: pd.DataFrame,
    companies: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    rel = relationships.copy()
    rel = rel[rel["product"].isin(PRODUCT_CHAIN)]
    if companies is not None and not companies.empty:
        master = companies[["name", "ticker"]].copy()
        master["ticker_key"] = master["ticker"].astype(str).str.replace(r"\..*$", "", regex=True)
        rel = rel.merge(master, left_on="company", right_on="name", how="left")
        joined = frame.merge(
            rel[["company", "product", "weight", "ticker_key"]],
            left_on="ticker", right_on="ticker_key", how="inner", suffixes=("_feed", ""),
        )
        if not joined.empty:
            joined["company"] = joined["company"].fillna(joined.get("company_feed"))
    else:
        joined = frame.merge(rel[["company", "product", "weight"]], on="company", how="inner")

    rows: list[dict[str, Any]] = []
    for _, row in joined.iterrows():
        yoy = row.get("yoy_pct")
        if pd.isna(yoy):
            continue
        chain = PRODUCT_CHAIN[str(row["product"])]
        period = str(row.get("period", ""))
        weight = float(row["weight"]) if pd.notna(row.get("weight")) else None
        rows.append(_evidence_row(
            evidence_id=f"{row['source_id']}_{row['ticker']}_{period}",
            dimension="financial_confirmation",
            chain=chain,
            indicator=f"{row['company']} monthly revenue YoY",
            available_at=pd.Timestamp(row["published_at"]),
            yoy_pct=float(yoy),
            source_type="company_actual",
            reliability_prior=0.90,
            source=str(row["source"]),
            source_id=str(row["source_id"]),
            evidence_group=f"monthly_revenue_{row['ticker']}_{period}",
            period_date=period,
            notes=f"Product mapping: {row['product']}; exposure is configured, not observed product mix.",
            exposure_weight=weight,
            exposure_basis="CONFIGURED_ASSUMPTION",
        ))
    return pd.DataFrame(rows)


def moea_snapshot_to_evidence(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    work = frame.copy()
    work["period_ts"] = work["period"].map(parse_month_period)
    work = work[work["period_ts"].notna()].copy()
    rows: list[dict[str, Any]] = []
    for indicator, group in work.groupby("indicator", dropna=False):
        group = group.sort_values("period_ts").drop_duplicates("period_ts", keep="last")
        latest = group.iloc[-1]
        prior = group[group["period_ts"] == latest["period_ts"] - pd.DateOffset(years=1)]
        if prior.empty or float(prior.iloc[-1]["raw_value"]) == 0:
            continue
        yoy = (float(latest["raw_value"]) / float(prior.iloc[-1]["raw_value"]) - 1.0) * 100.0
        period = latest["period_ts"].strftime("%Y-%m")
        rows.append(_evidence_row(
            evidence_id=f"{latest['source_id']}_{re.sub('[^A-Za-z0-9]+','_',str(indicator))}_{period}",
            dimension=str(latest["dimension"]),
            chain=str(latest["chain"]),
            indicator=f"MOEA export orders — {indicator}",
            available_at=pd.Timestamp(latest["published_at"]),
            yoy_pct=yoy,
            source_type="government_statistic",
            reliability_prior=0.98,
            source=str(latest["source"]),
            source_id=str(latest["source_id"]),
            evidence_group=f"moea_export_orders_{latest['chain']}_{period}",
            period_date=period,
            notes="YoY derived from official monthly levels; collection time is the conservative earliest availability.",
        ))
    return pd.DataFrame(rows)


def tpca_snapshot_to_evidence(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    return pd.DataFrame([
        _evidence_row(
            evidence_id=f"tpca_{row['indicator']}_{pd.Timestamp(row['published_at']).strftime('%Y%m%d')}",
            dimension=str(row["dimension"]),
            chain=str(row["chain"]),
            indicator=f"TPCA {row['indicator']}",
            available_at=pd.Timestamp(row["published_at"]),
            yoy_pct=float(row["yoy_pct"]),
            source_type="industry_association",
            reliability_prior=0.80,
            source=str(row["source"]),
            source_id=str(row["source_id"]),
            evidence_group=f"tpca_{row['indicator']}_{pd.Timestamp(row['published_at']).strftime('%Y%m')}",
            notes=str(row.get("context", ""))[:240],
        )
        for _, row in frame.iterrows()
    ])


def _manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"sources": {}}


def persist_if_changed(
    *,
    persistent_root: Path,
    source_id: str,
    payload: bytes,
    collected_at: pd.Timestamp,
    extension: str,
    source_url: str,
) -> tuple[Path | None, str, bool, pd.Timestamp]:
    manifest_path = persistent_root / "manifest.json"
    manifest = _manifest(manifest_path)
    digest = hashlib.sha256(payload).hexdigest()
    current=manifest["sources"].get(source_id,{})
    if current.get("sha256") == digest:
        latest=current.get("latest_snapshot")
        existing=(persistent_root/latest) if latest else None
        canonical=pd.to_datetime(current.get("collected_at"),utc=True)
        current["last_verified_at"]=collected_at.isoformat()
        current["source"]=source_url
        manifest["sources"][source_id]=current
        manifest_path.parent.mkdir(parents=True,exist_ok=True)
        manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        return existing, digest, False, canonical
    stamp = collected_at.tz_convert("UTC").strftime("%Y%m%dT%H%M%SZ")
    out = persistent_root / "raw" / source_id / f"{stamp}.{extension}"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(payload)
    manifest["sources"][source_id] = {
        "sha256": digest,
        "latest_snapshot": str(out.relative_to(persistent_root)),
        "collected_at": collected_at.isoformat(),
        "last_verified_at": collected_at.isoformat(),
        "source": source_url,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out, digest, True, collected_at


def load_persisted_snapshot(
    *,
    persistent_root: Path,
    source_id: str,
) -> tuple[bytes,Path,str,pd.Timestamp,pd.Timestamp,str] | None:
    manifest=_manifest(persistent_root/"manifest.json")
    current=manifest.get("sources",{}).get(source_id)
    if not current:
        return None
    latest=current.get("latest_snapshot")
    digest=str(current.get("sha256",""))
    if not latest or len(digest)!=64:
        return None
    path=persistent_root/latest
    if not path.exists():
        return None
    payload=path.read_bytes()
    actual=hashlib.sha256(payload).hexdigest()
    if actual!=digest:
        raise ValueError(f"persisted snapshot SHA mismatch for {source_id}: {actual} != {digest}")
    canonical=pd.to_datetime(current.get("collected_at"),utc=True)
    last_verified=pd.to_datetime(current.get("last_verified_at") or current.get("collected_at"),utc=True)
    return payload,path,digest,canonical,last_verified,str(current.get("source",""))


def _display_path(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _decorate_retrieval(
    derived: pd.DataFrame,
    *,
    digest: str,
    raw_path: Path | None,
    run_id: str,
    retrieval_status: str,
    retrieval_attempted_at: pd.Timestamp,
    last_verified_at: pd.Timestamp,
    stale_age_hours: float,
    fetch_error: str="",
) -> pd.DataFrame:
    if derived.empty:
        return derived
    out=derived.copy()
    out["raw_sha256"]=digest
    out["raw_snapshot_path"]=_display_path(raw_path)
    out["pipeline_run_id"]=run_id
    out["retrieval_status"]=retrieval_status
    out["retrieval_attempted_at"]=retrieval_attempted_at.isoformat()
    out["last_verified_at"]=last_verified_at.isoformat()
    out["stale_age_hours"]=float(stale_age_hours)
    out["retrieval_error"]=fetch_error
    return out


def _parse_payload(
    source: dict[str,Any],
    payload: bytes,
    *,
    canonical_collected_at: pd.Timestamp,
    source_url: str,
    relationships: pd.DataFrame,
    companies: pd.DataFrame,
) -> tuple[pd.DataFrame,int]:
    sid,kind=source["source_id"],source["kind"]
    if kind=="monthly_revenue_json":
        parsed=parse_monthly_revenue_json(
            payload,source_id=sid,market=source["market"],
            collected_at=canonical_collected_at,source_url=source_url,
        )
        return revenue_snapshot_to_evidence(parsed,relationships,companies),len(parsed)
    if kind=="data_gov_dataset_csv":
        parsed=parse_moea_export_orders_csv(
            payload,source_id=sid,chain=source["chain"],dimension=source["dimension"],
            collected_at=canonical_collected_at,source_url=source_url,
        )
        return moea_snapshot_to_evidence(parsed),len(parsed)
    if kind=="tpca_public_listing":
        parsed=parse_tpca_listing(payload,collected_at=canonical_collected_at,source_url=source_url)
        return tpca_snapshot_to_evidence(parsed),len(parsed)
    raise ValueError(f"Unsupported connector kind: {kind}")


def collect_all(
    *,
    config_path: Path | str | None = None,
    persistent_root: Path = DEFAULT_PERSISTENT,
    artifacts_dir: Path = DEFAULT_ARTIFACTS,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    cfg = load_source_config(config_path or ROOT / "data" / "free_evidence_sources.json")
    run_id=os.environ.get("RESEARCH_PIPELINE_RUN_ID") or os.environ.get("GITHUB_RUN_ID") or pd.Timestamp.now(tz="UTC").strftime("%Y%m%dT%H%M%SZ")
    relationships = pd.read_csv(DEFAULT_RELATIONS)
    companies = pd.read_csv(DEFAULT_COMPANIES)
    evidence_frames: list[pd.DataFrame] = []
    status: list[dict[str, Any]] = []

    for source in cfg["sources"]:
        if not source.get("enabled", True):
            continue
        sid, kind = source["source_id"], source["kind"]
        try:
            if kind == "monthly_revenue_json":
                fetched = fetch_bytes(source["url"])
                raw_path,digest,changed,canonical_collected_at=persist_if_changed(
                    persistent_root=persistent_root, source_id=sid, payload=fetched.payload,
                    collected_at=fetched.collected_at, extension="json", source_url=fetched.url,
                )
                parsed = parse_monthly_revenue_json(
                    fetched.payload, source_id=sid, market=source["market"],
                    collected_at=canonical_collected_at, source_url=fetched.url,
                )
                derived=revenue_snapshot_to_evidence(parsed, relationships, companies)
                derived=_decorate_retrieval(
                    derived,digest=digest,raw_path=raw_path,run_id=run_id,retrieval_status="FRESH",
                    retrieval_attempted_at=fetched.collected_at,last_verified_at=fetched.collected_at,
                    stale_age_hours=0.0,
                )
                evidence_frames.append(derived)
                rows = len(parsed)
            elif kind == "data_gov_dataset_csv":
                metadata_fetch = fetch_bytes(DATA_GOV_METADATA.format(dataset_id=source["dataset_id"]))
                resource_url = extract_data_gov_resource_url(json.loads(metadata_fetch.payload.decode("utf-8")))
                fetched = fetch_bytes(resource_url)
                raw_path,digest,changed,canonical_collected_at=persist_if_changed(
                    persistent_root=persistent_root, source_id=sid, payload=fetched.payload,
                    collected_at=fetched.collected_at, extension="csv", source_url=fetched.url,
                )
                parsed = parse_moea_export_orders_csv(
                    fetched.payload, source_id=sid, chain=source["chain"], dimension=source["dimension"],
                    collected_at=canonical_collected_at, source_url=fetched.url,
                )
                derived=moea_snapshot_to_evidence(parsed)
                derived=_decorate_retrieval(
                    derived,digest=digest,raw_path=raw_path,run_id=run_id,retrieval_status="FRESH",
                    retrieval_attempted_at=fetched.collected_at,last_verified_at=fetched.collected_at,
                    stale_age_hours=0.0,
                )
                evidence_frames.append(derived)
                rows = len(parsed)
            elif kind == "tpca_public_listing":
                fetched = fetch_bytes(source["url"])
                raw_path,digest,changed,canonical_collected_at=persist_if_changed(
                    persistent_root=persistent_root, source_id=sid, payload=fetched.payload,
                    collected_at=fetched.collected_at, extension="html", source_url=fetched.url,
                )
                parsed = parse_tpca_listing(fetched.payload, collected_at=canonical_collected_at, source_url=fetched.url)
                derived=tpca_snapshot_to_evidence(parsed)
                derived=_decorate_retrieval(
                    derived,digest=digest,raw_path=raw_path,run_id=run_id,retrieval_status="FRESH",
                    retrieval_attempted_at=fetched.collected_at,last_verified_at=fetched.collected_at,
                    stale_age_hours=0.0,
                )
                evidence_frames.append(derived)
                rows = len(parsed)
            else:
                raise ValueError(f"Unsupported connector kind: {kind}")
            status.append({
                "source_id":sid,"provider":source.get("provider",""),"kind":kind,"status":"ok","rows":rows,
                "fetch_collected_at":fetched.collected_at.isoformat(),
                "canonical_available_at":canonical_collected_at.isoformat(),
                "last_verified_at":fetched.collected_at.isoformat(),
                "retrieval_status":"FRESH",
                "stale_age_hours":0.0,
                "source_url":fetched.url,
                "sha256":digest,"payload_bytes":len(fetched.payload),"changed":bool(changed),
                "persistent_path":_display_path(raw_path),
            })
        except Exception as exc:
            attempted_at=pd.Timestamp.now(tz="UTC")
            fallback=None
            if bool(source.get("allow_stale_fallback",False)):
                try:
                    fallback=load_persisted_snapshot(persistent_root=persistent_root,source_id=sid)
                except Exception as fallback_load_exc:
                    exc=RuntimeError(f"{exc}; persisted fallback invalid: {fallback_load_exc}")
            if fallback is not None:
                payload,raw_path,digest,canonical_collected_at,last_verified_at,stored_url=fallback
                stale_age_hours=max(0.0,(attempted_at-last_verified_at).total_seconds()/3600.0)
                max_stale_hours=float(source.get("max_stale_hours",72))
                if stale_age_hours<=max_stale_hours:
                    try:
                        derived,rows=_parse_payload(
                            source,payload,canonical_collected_at=canonical_collected_at,
                            source_url=stored_url or str(source.get("url","")),
                            relationships=relationships,companies=companies,
                        )
                        derived=_decorate_retrieval(
                            derived,digest=digest,raw_path=raw_path,run_id=run_id,
                            retrieval_status="STALE_FALLBACK",retrieval_attempted_at=attempted_at,
                            last_verified_at=last_verified_at,stale_age_hours=stale_age_hours,
                            fetch_error=str(exc),
                        )
                        evidence_frames.append(derived)
                        status.append({
                            "source_id":sid,"provider":source.get("provider",""),"kind":kind,
                            "status":"stale_fallback","rows":rows,
                            "fetch_collected_at":attempted_at.isoformat(),
                            "canonical_available_at":canonical_collected_at.isoformat(),
                            "last_verified_at":last_verified_at.isoformat(),
                            "retrieval_status":"STALE_FALLBACK",
                            "stale_age_hours":stale_age_hours,
                            "max_stale_hours":max_stale_hours,
                            "source_url":stored_url or str(source.get("url","")),
                            "sha256":digest,"payload_bytes":len(payload),"changed":False,
                            "persistent_path":_display_path(raw_path),
                            "error":str(exc),
                        })
                        continue
                    except Exception as fallback_parse_exc:
                        exc=RuntimeError(f"{exc}; stale fallback parse failed: {fallback_parse_exc}")
                else:
                    exc=RuntimeError(
                        f"{exc}; stale fallback exceeds max age: {stale_age_hours:.1f}h > {max_stale_hours:.1f}h"
                    )
            status.append({
                "source_id":sid,"provider":source.get("provider",""),"kind":kind,"status":"error","rows":0,
                "retrieval_status":"ERROR","error":str(exc),"collected_at":attempted_at.isoformat(),
            })

    frames = [f for f in evidence_frames if not f.empty]
    evidence = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if not evidence.empty:
        evidence = evidence.sort_values(["published_at", "evidence_id"]).drop_duplicates("evidence_id", keep="last")
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    evidence.to_csv(artifacts_dir / "free_evidence_latest.csv", index=False)

    summary = {
        "pipeline_run_id":run_id,
        "collected_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "policy": cfg.get("policy",""),
        "sources_total": len(status),
        "sources_ok": sum(s["status"] == "ok" for s in status),
        "sources_stale": sum(s["status"] == "stale_fallback" for s in status),
        "sources_usable": sum(s["status"] in {"ok","stale_fallback"} for s in status),
        "sources_error": sum(s["status"] == "error" for s in status),
        "evidence_rows": len(evidence),
        "sources": status,
    }
    (artifacts_dir / "free_evidence_collection_status.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return evidence, summary


if __name__ == "__main__":
    evidence, summary = collect_all()
    print(f"FREE_EVIDENCE_COLLECTION_OK sources_ok={summary['sources_ok']}/{summary['sources_total']} evidence_rows={len(evidence)}")
    for source in summary["sources"]:
        print(source)
