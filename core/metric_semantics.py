"""Explicit semantics and auditable, point-in-time observation transforms."""
from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, FormatChecker
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_STATUSES = {'DISCLOSED', 'DERIVED', 'ESTIMATED', 'INFERRED', 'UNKNOWN'}
EXACT_METHODS = {'source_reported', 'actual_publication_time', 'official_filing_timestamp'}


@lru_cache(maxsize=1)
def _registry() -> dict:
    return json.loads((ROOT/'data/abf_metric_semantics.json').read_text(encoding='utf-8'))


def metric_semantics(metric_id: str) -> dict:
    key = 'abf_company_revenue_yoy::*' if metric_id.startswith('abf_company_revenue_yoy::') else metric_id
    if key not in _registry()['metrics']:
        raise ValueError(f'Unregistered metric semantics: {metric_id}')
    return dict(_registry()['metrics'][key])


def financial_semantics(metric_id: str) -> dict:
    if metric_id not in _registry()['financial_metrics']:
        raise ValueError(f'Unregistered financial semantics: {metric_id}')
    return dict(_registry()['financial_metrics'][metric_id])


def timestamp(value: object) -> pd.Timestamp:
    parsed = pd.Timestamp(value)
    if pd.isna(parsed) or parsed.tzinfo is None:
        raise ValueError(f'Timezone-aware timestamp required: {value}')
    return parsed.tz_convert('UTC')


def _present(value: object) -> bool:
    return value is not None and not pd.isna(value) and bool(str(value).strip())


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    schema = json.loads((ROOT/'contracts/metric-semantics/v1/schema.json').read_text(encoding='utf-8'))
    return Draft202012Validator(schema, format_checker=FormatChecker())


def validate_signal(signal: dict) -> None:
    _validator().validate(signal)
    observed = timestamp(signal['observation_date'])
    generated = timestamp(signal['signal_generated_at'])
    available = timestamp(signal['available_at']) if signal['available_at'] else None
    release = timestamp(signal['release_date']) if signal['release_date'] else None
    if available is not None and (available < observed or available > generated):
        raise ValueError('Availability must follow observation and precede generation')
    if release is not None and (release < observed or available is None or release > available):
        raise ValueError('Release must follow observation and precede availability')
    if signal['pit_basis'] == 'SOURCE_REPORTED' and release is None:
        raise ValueError('Exact publication basis requires release_date')
    if signal['signal_value'] is not None and not np.isfinite(signal['signal_value']):
        raise ValueError('Signal value must be finite')


def normalize_history(history: pd.DataFrame, *, as_of: str, generated_at: str | None = None) -> pd.DataFrame:
    cutoff = timestamp(as_of)
    generated = timestamp(generated_at or datetime.now(timezone.utc).isoformat())
    if generated < cutoff:
        raise ValueError('signal_generated_at cannot precede as_of')
    rows, seen = [], {}
    if history.empty:
        return pd.DataFrame()
    for raw in history.to_dict('records'):
        metric = str(raw.get('metric_id',''))
        try:
            semantics = metric_semantics(metric)
        except ValueError:
            continue  # Other verticals have no ABF semantics and cannot enter this slice.
        period = pd.Period(str(raw['period'])[:7],freq='M')
        # Economic period is month-end in the source market, not UTC calendar date.
        observed = period.end_time.normalize().tz_localize('Asia/Taipei').tz_convert('UTC')
        method = str(raw.get('knowledge_time_method','UNKNOWN'))
        published = timestamp(raw['published_at']) if _present(raw.get('published_at')) else None
        release = timestamp(raw['release_date']) if _present(raw.get('release_date')) else (published if method in EXACT_METHODS else None)
        times = [t for t in (published,release) if t is not None]
        for field in ('available_at','first_seen_at','snapshot_acquired_at'):
            if _present(raw.get(field)):
                times.append(timestamp(raw[field]))
        available = max(times) if times else None
        if available is not None and available > cutoff:
            continue
        value = pd.to_numeric(raw.get('change_pct'), errors='coerce')
        value = float(value) if pd.notna(value) and np.isfinite(value) else None
        supplied_status=raw.get('evidence_status')
        if _present(supplied_status) and supplied_status not in EVIDENCE_STATUSES:
            raise ValueError(f'Noncanonical evidence status: {supplied_status}')
        url = str(raw.get('source_url','')).strip()
        urls = [url] if urlsplit(url).scheme in {'http','https'} and urlsplit(url).netloc else []
        company = metric.split('::',1)[1] if '::' in metric else 'INDUSTRY'
        content = json.dumps([metric,str(period),value,method,str(available),url,str(supplied_status)],ensure_ascii=False)
        oid = sha256(content.encode()).hexdigest()
        signal = dict(semantics, contract='MetricSignalSemanticsV1', metric_id=metric,
            company=company, period=str(period), transform='LEVEL', signal_value=value,
            observation_date=observed.isoformat(), release_date=release.isoformat() if release is not None else None,
            available_at=available.isoformat() if available is not None else None,
            signal_generated_at=generated.isoformat(),
            pit_basis='SOURCE_REPORTED' if release is not None and method in EXACT_METHODS else ('PROXY' if available is not None else 'UNKNOWN'),
            evidence_status=supplied_status if _present(supplied_status) else ('DISCLOSED' if value is not None and urls and method in EXACT_METHODS else ('DERIVED' if value is not None and urls else 'UNKNOWN')),
            knowledge_time_method=method, source_urls=urls, observation_id=oid, dependency_ids=[oid])
        validate_signal(signal)
        signal['source_lineage_complete']=bool(urls) and signal['evidence_status'] in {'DISCLOSED','DERIVED'}
        key = (metric,str(period))
        if key in seen:
            if seen[key] != oid:
                raise ValueError(f'Conflicting duplicate observation: {key}; select a documented vintage first')
            continue
        seen[key] = oid
        rows.append(signal)
    return pd.DataFrame(rows)


def transform_observations(frame: pd.DataFrame, transform: str) -> pd.DataFrame:
    if transform not in {'LEVEL','CHANGE'}:
        raise ValueError(f'Unknown transform: {transform}')
    if frame.empty or transform == 'LEVEL':
        return frame.copy()
    rows = []
    for _, group in frame.groupby(['metric_id','company','product'],sort=False):
        records = group.sort_values('period').to_dict('records')
        for previous, current in zip(records,records[1:]):
            if pd.Period(current['period'],'M')-1 != pd.Period(previous['period'],'M'):
                continue
            if pd.isna(current['signal_value']) or pd.isna(previous['signal_value']):
                continue
            row = dict(current)
            row.update(transform='CHANGE', unit='percentage_points', evidence_status='DERIVED',
                signal_value=current['signal_value']-previous['signal_value'],
                dependency_ids=previous['dependency_ids']+current['dependency_ids'],
                source_urls=sorted(set(previous['source_urls']+current['source_urls'])))
            row['source_lineage_complete']=all(r.get('source_lineage_complete',bool(r['source_urls'])) for r in (previous,current))
            for status in ('ESTIMATED','INFERRED','UNKNOWN'):
                if any(r['evidence_status']==status for r in (previous,current)):
                    row['evidence_status']=status
            for field in ('available_at','release_date'):
                values = [previous[field],current[field]]
                row[field] = max(values) if all(values) else None
            row['pit_basis'] = 'SOURCE_REPORTED' if all(r['pit_basis']=='SOURCE_REPORTED' for r in (previous,current)) else 'PROXY'
            row['observation_id'] = sha256('|'.join(row['dependency_ids']).encode()).hexdigest()
            validate_signal(row)
            rows.append(row)
    return pd.DataFrame(rows)
