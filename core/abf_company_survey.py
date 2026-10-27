"""One Company × ABF view of the semantics audit and reviewed company evidence.

This module packages evidence, never estimates a new relationship or selects a
transform. Consumers must plot ``sample_rows`` and ``trend.observations`` as supplied.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from itertools import product
import math
import re
from urllib.parse import urlsplit

import pandas as pd

from core.abf_transform_validation import COMPANIES, METRICS
from core.metric_semantics import EVIDENCE_STATUSES, EXACT_METHODS


COMPANY_NAMES = {'3037.TW': '欣興', '3189.TW': '景碩', '8046.TW': '南電'}
SCENARIOS = ('UPSIDE', 'DOWNSIDE')
TRANSFORMS = ('LEVEL', 'CHANGE')
ACQUISITION_FIELDS = ('acquired_at', 'first_seen_at', 'snapshot_acquired_at')
FORWARD_LOOKING_KINDS = {'GUIDANCE', 'FORWARD_LOOKING', 'FORECAST', 'ESTIMATE', 'PROJECTION', 'TARGET'}
OPERATING_INPUTS = ('abf_orders_backlog', 'abf_customer_inventory', 'abf_utilization',
                    'abf_pricing', 'abf_asp', 'abf_product_mix')
FINANCIAL_UNITS = {'gross_margin': 'ratio', 'revenue': 'TWD', 'revenue_yoy': 'ratio',
                   'eps': 'TWD_per_share'}


def _present(value: object) -> bool:
    return value is not None and not pd.isna(value) and bool(str(value).strip())


def _number(value: object) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _json_value(value):
    """Detach source objects and emit strict JSON, including pandas missing values."""
    if isinstance(value, dict):
        return {str(k): _json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(v) for v in value]
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    if value is None or pd.isna(value):
        return None
    if hasattr(value, 'item'):
        return _json_value(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _time(value: object, *, field: str, end_of_day: bool = True) -> pd.Timestamp | None:
    if not _present(value):
        return None
    try:
        parsed = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'Invalid {field} date/timestamp: {value}') from exc
    if pd.isna(parsed):
        raise ValueError(f'Invalid {field} date/timestamp: {value}')
    if parsed.tzinfo is None:
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(value)):
            raise ValueError(f'Timezone-aware {field} timestamp required: {value}')
        parsed = parsed.tz_localize('Asia/Taipei')
        if end_of_day:
            parsed += pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    return parsed.tz_convert('UTC')


def _iso(value: pd.Timestamp | None) -> str | None:
    return value.isoformat() if value is not None else None


def _company(raw: dict) -> str | None:
    candidates = []
    for field in ('company', 'ticker', 'stock_id'):
        if not _present(raw.get(field)):
            continue
        candidate = str(raw[field]).strip()
        if candidate in COMPANY_NAMES.values():
            candidate = next(k for k, name in COMPANY_NAMES.items() if name == candidate)
        elif re.fullmatch(r'\d{4}(?:\.0)?', candidate):
            candidate = candidate[:4]+'.TW'
        if candidate in COMPANIES:
            candidates.append(candidate)
    if len(set(candidates)) > 1:
        raise ValueError('Conflicting company/ticker/stock_id identifiers')
    return candidates[0] if candidates else None


def _status(raw: dict, default: str = 'UNKNOWN') -> str:
    status = raw.get('evidence_status')
    if not _present(status):
        return default
    if status not in EVIDENCE_STATUSES:
        raise ValueError(f'Noncanonical evidence status: {status}')
    return status


def _urls(raw: dict) -> list[str]:
    supplied = raw.get('source_urls', [])
    candidates = list(supplied) if isinstance(supplied, (list, tuple)) else [supplied]
    candidates += [raw.get('source_url'), raw.get('filing_source_url'), raw.get('fundamental_source_url'),
                   raw.get('primary_financial_source_url')]
    urls = set()
    for value in candidates:
        if not _present(value):
            continue
        url = str(value).strip()
        parsed = urlsplit(url)
        if parsed.scheme in {'http', 'https'} and parsed.netloc:
            urls.add(url)
    return sorted(urls)


def _dates(raw: dict, *, generated_at: str | None, financial: bool = False) -> dict:
    observed = _time(raw.get('observation_date', raw.get('report_date')),
                     field='observation_date', end_of_day=False)
    release_fields = ('release_date', 'filing_published_at') + (('financial_release_date',) if financial else ())
    releases = [_time(raw.get(k), field=k) for k in release_fields]
    release = max((t for t in releases if t is not None), default=None)
    acquisition_fields = ACQUISITION_FIELDS + (('financial_evidence_acquired_at',) if financial else ())
    acquisitions = [_time(raw.get(k), field=k) for k in acquisition_fields]
    acquired = max((t for t in acquisitions if t is not None), default=None)
    available_times = [release, acquired, _time(raw.get('available_at'), field='available_at')]
    if financial:
        available_times.append(_time(raw.get('available_date'), field='available_date'))
        available_times.append(_time(raw.get('financial_basis_verification_available_at'),
                                     field='financial_basis_verification_available_at'))
    available = max((t for t in available_times if t is not None), default=None)
    generated = _time(raw.get('signal_generated_at') or generated_at, field='signal_generated_at')
    if observed is not None:
        if acquired is not None and acquired < observed:
            raise ValueError('acquired_at cannot precede observation_date')
        if release is not None and release < observed:
            raise ValueError('release_date cannot precede observation_date')
        if available is not None and available < observed:
            raise ValueError('Availability/acquisition cannot precede observation_date')
    if generated is not None and available is not None and generated < available:
        raise ValueError('signal_generated_at cannot precede availability/acquisition')
    # A date-only disclosure is a conservative end-of-day bound, not an exact release.
    release_inputs = [raw.get(k) for k in ('release_date', 'filing_published_at') if _present(raw.get(k))]
    exact_release = bool(release_inputs) and all(
        pd.Timestamp(v).tzinfo is not None for v in release_inputs)
    for field, exact_values in (
            ('release_time_basis', {'EXACT', 'EXACT_TIMESTAMP', 'TIMESTAMP', 'SOURCE_REPORTED'}),
            ('time_basis', {'EXACT', 'EXACT_TIMESTAMP', 'SOURCE_REPORTED', 'ACTUAL_PUBLICATION_TIME', 'OFFICIAL_FILING_TIMESTAMP'}),
            ('pit_basis', {'SOURCE_REPORTED'}), ('knowledge_time_method', EXACT_METHODS)):
        if _present(raw.get(field)) and raw[field] not in exact_values:
            exact_release = False
    if raw.get('pit_exact') is False:
        exact_release = False
    if financial and raw.get('financial_pit_exact') is False:
        exact_release = False
    return dict(observation_date=_iso(observed), release_date=_iso(release),
                available_at=_iso(available), acquired_at=_iso(acquired),
                signal_generated_at=_iso(generated), exact_release=exact_release)


def _known(dates: dict, cutoff: pd.Timestamp) -> bool:
    return dates['available_at'] is not None and all(
        _time(dates.get(k), field=k) <= cutoff for k in ('available_at', 'observation_date')
        if dates.get(k) is not None)


def _fact_records(facts: list | dict) -> list[dict]:
    if isinstance(facts, dict):
        if 'facts' in facts:
            facts = facts['facts']
        elif 'fact_id' in facts:
            facts = [facts]
        else:
            facts = [dict(value, fact_id=value.get('fact_id', key))
                     for key, value in facts.items() if isinstance(value, dict)]
    if not isinstance(facts, list) or any(not isinstance(row, dict) for row in facts):
        raise ValueError('Reviewed facts must be a list of records or a facts dictionary')
    return facts


def _reviewed_facts(facts: list | dict, *, cutoff: pd.Timestamp, generated_at: str) -> tuple[list, list]:
    accepted, rejected, seen = [], [], {}
    for raw in _fact_records(facts):
        raw = _json_value(raw)
        company = _company(raw)
        fact_id = raw.get('fact_id')
        if fact_id in seen:
            if seen[fact_id] != raw:
                raise ValueError(f'Conflicting reviewed fact ID: {fact_id}')
            continue
        if _present(fact_id):
            seen[fact_id] = raw
        status = _status(raw)
        dates = _dates(raw, generated_at=generated_at)
        urls = _urls(raw)
        document = raw.get('document') or raw.get('source_document') or raw.get('document_name')
        page = raw.get('page', raw.get('source_page'))
        reason = None
        if not _present(fact_id) or company is None or not _present(raw.get('metric_id')):
            reason = 'MISSING_IDENTITY'
        elif raw.get('product') not in {'ABF', 'All company products'} and not (
                raw.get('source_scope') == 'COMPANY_TOTAL' and raw.get('is_proxy') is True):
            reason = 'UNSUPPORTED_PRODUCT_SCOPE'
        elif not urls or not _present(document) or not _present(page):
            reason = 'UNTRACEABLE_SOURCE'
        elif not dates['observation_date'] or not _known(dates, cutoff):
            reason = 'UNAVAILABLE_OR_AFTER_AS_OF'
        if reason:
            rejected.append(dict(fact_id=fact_id, company=company, reason=reason))
            continue
        fact = deepcopy(raw)
        fact['source_product'] = raw.get('source_product') or raw['product']
        if raw['product'] != 'ABF':
            fact['product'] = 'All company products'
        fact.update(company=company, stock_id=company[:4], fact_id=str(fact_id),
                    value=_number(raw.get('value')), source_urls=urls,
                    document=document, page=page, **{k: v for k, v in dates.items() if k != 'exact_release'})
        company_total = fact['product'] == 'All company products'
        fact['source_scope'] = 'COMPANY_TOTAL' if company_total else (raw.get('source_scope') or 'UNKNOWN')
        fact['is_proxy'] = company_total or raw.get('is_proxy') is not False or fact['source_scope'] != 'COMPANY_PRODUCT'
        fact['evidence_status'] = status
        fact['accounting_basis'] = raw.get('accounting_basis') or 'UNKNOWN'
        fact['source_lineage_complete'] = True
        fact['pit_exact'] = bool(dates['exact_release'] and dates['acquired_at'])
        fact['data_status'] = 'AVAILABLE' if fact['pit_exact'] else 'PIT_UNAVAILABLE'
        fact['is_forward_looking'] = (raw.get('is_forward_looking') is True or
            any(str(raw.get(field, '')).upper() in FORWARD_LOOKING_KINDS for field in ('measure_kind', 'validation_status')))
        fact['usable'] = status in {'DISCLOSED', 'DERIVED'} and fact['pit_exact'] and not fact['is_forward_looking']
        calculation = raw.get('calculation') or {}
        dependencies = calculation.get('dependencies', raw.get('dependency_ids'))
        if dependencies is None:
            dependencies = [] if status == 'DERIVED' else [str(fact_id)]
        if not isinstance(dependencies, list) or any(not isinstance(dep, str) for dep in dependencies):
            raise ValueError(f'Fact dependency_ids must be a list of fact IDs: {fact_id}')
        fact['dependency_ids'] = list(dependencies)
        accepted.append(fact)
    return _resolve_fact_dependencies(accepted, rejected), rejected


def _resolve_fact_dependencies(facts: list[dict], rejected: list[dict]) -> list[dict]:
    """A reviewed calculation can only use facts available with full input lineage."""
    by_id = {fact['fact_id']: fact for fact in facts}
    resolved, visiting = {}, set()

    def resolve(fact_id):
        if fact_id in resolved:
            return resolved[fact_id]
        if fact_id in visiting:
            raise ValueError(f'Cyclic reviewed fact dependencies: {fact_id}')
        fact = by_id.get(fact_id)
        if fact is None:
            return None
        visiting.add(fact_id)
        deps = fact['dependency_ids']
        calculated = fact['evidence_status'] == 'DERIVED' or fact.get('calculation') is not None
        inputs = [resolve(dep) for dep in deps if dep != fact_id]
        reason = None
        if any(item is None for item in inputs) or (calculated and (not inputs or fact_id in deps)):
            reason = 'DEPENDENCY_UNAVAILABLE'
        elif any(item['company'] != fact['company'] for item in inputs):
            reason = 'DEPENDENCY_COMPANY_MISMATCH'
        elif calculated and fact['value'] is not None and any(item['value'] is None for item in inputs):
            reason = 'DEPENDENCY_VALUE_UNAVAILABLE'
        elif inputs:
            fact['available_at'] = max([fact['available_at'], *(f['available_at'] for f in inputs)])
            acquired = [f['acquired_at'] for f in [fact, *inputs] if f['acquired_at']]
            fact['acquired_at'] = max(acquired) if acquired else None
            if fact['signal_generated_at'] < fact['available_at']:
                reason = 'DEPENDENCY_AFTER_SIGNAL_GENERATION'
            fact['source_urls'] = sorted({url for f in [fact, *inputs] for url in f['source_urls']})
            fact['source_lineage_complete'] = all(f['source_lineage_complete'] for f in [fact, *inputs])
            fact['pit_exact'] = all(f['pit_exact'] for f in [fact, *inputs])
            fact['is_proxy'] = any(f['is_proxy'] for f in [fact, *inputs])
            fact['is_forward_looking'] = any(f['is_forward_looking'] for f in [fact, *inputs])
            total_inputs = [f for f in [fact, *inputs] if f['source_scope'] == 'COMPANY_TOTAL']
            if total_inputs:
                products = {f['source_product'] for f in total_inputs}
                fact.update(product='All company products', source_scope='COMPANY_TOTAL',
                            source_product='All company products' if 'All company products' in products else ', '.join(sorted(products)))
            elif any(f['source_scope'] != fact['source_scope'] for f in inputs):
                fact.update(source_scope='UNKNOWN', source_product='Mixed or unknown scope', is_proxy=True)
            for status in ('ESTIMATED', 'INFERRED', 'UNKNOWN'):
                if any(f['evidence_status'] == status for f in [fact, *inputs]):
                    fact['evidence_status'] = status
            fact['data_status'] = 'AVAILABLE' if fact['pit_exact'] else 'PIT_UNAVAILABLE'
            fact['usable'] = (fact['evidence_status'] in {'DISCLOSED', 'DERIVED'} and fact['pit_exact']
                              and fact['source_lineage_complete'] and not fact['is_forward_looking']
                              and all(f['usable'] for f in inputs))
        visiting.remove(fact_id)
        if reason:
            rejected.append(dict(fact_id=fact_id, company=fact['company'], reason=reason))
        resolved[fact_id] = None if reason else fact
        return resolved[fact_id]

    return [result for fact in facts if (result := resolve(fact['fact_id'])) is not None]


def _financial_rows(factor: pd.DataFrame, *, cutoff: pd.Timestamp, generated_at: str) -> list[dict]:
    rows, seen = [], {}
    for raw in factor.to_dict('records'):
        company = _company(raw)
        if company is None:
            continue
        raw = _json_value(raw)
        for field in ('report_date', 'available_date'):
            if re.fullmatch(r'\d{4}-\d{2}-\d{2}T00:00:00', str(raw.get(field))):
                raw[field] = raw[field][:10]  # pandas date columns retain the daily-data convention.
        # Validate source dates and any explicit signal before applying the cutoff.
        # A default current signal is minted only for financial knowledge already known.
        dates = _dates(raw, generated_at=None, financial=True)
        if not dates['observation_date'] or not _known(dates, cutoff):
            continue
        dates = _dates(raw, generated_at=generated_at, financial=True)
        urls = _urls(raw)
        verified = raw.get('accounting_basis_verified') is True
        basis = raw.get('accounting_basis') if verified and urls else 'UNKNOWN'
        if basis not in {'STANDALONE_QUARTER', 'YTD', 'TTM', 'CONSOLIDATED_REPORTED'}:
            basis = 'UNKNOWN'
        report_date = str(raw.get('report_date') or raw['observation_date'])[:10]
        fid = f'financial::{company}::{report_date}'
        row = dict(company=company, product='ABF', source_product='All company products',
            source_scope='COMPANY_TOTAL', is_proxy=True, report_date=report_date,
            evidence_id=fid, accounting_basis=basis,
            accounting_basis_verified=verified and basis != 'UNKNOWN',
            source_urls=urls, source_lineage_complete=bool(urls),
            fundamental_source=raw.get('fundamental_source') or 'UNKNOWN',
            fundamental_source_url=raw.get('fundamental_source_url'), market_source=raw.get('market_source'),
            financial_value_verification=raw.get('financial_value_verification') or 'UNVERIFIED',
            primary_financial_source_url=raw.get('primary_financial_source_url'),
            financial_evidence_id=raw.get('financial_evidence_id'),
            financial_evidence_sha256=raw.get('financial_evidence_sha256'),
            financial_evidence_acquired_at=raw.get('financial_evidence_acquired_at'),
            financial_source_page=raw.get('financial_source_page'),
            financial_period_start=raw.get('financial_period_start'),
            financial_published_decimal_places=raw.get('financial_published_decimal_places'),
            financial_rounding_tolerance_twd=raw.get('financial_rounding_tolerance_twd'),
            financial_basis_verification_available_at=raw.get('financial_basis_verification_available_at'),
            financial_comparative_from_later_document=raw.get('financial_comparative_from_later_document',False),
            value_source_urls=_urls({'source_url': raw.get('fundamental_source_url') or raw.get('source_url')}),
            filing_source_url=raw.get('filing_source_url'), filing_source_role='PUBLICATION_TIME_VERIFICATION',
            source_provenance='Financial values retain their provider; the filing URL verifies publication time only.',
            filing_document_name=raw.get('filing_document_name'),
            availability_method=raw.get('availability_method') or 'UNKNOWN',
            available_date=raw.get('available_date'), units=dict(FINANCIAL_UNITS),
            evidence_status=_status(raw, 'DERIVED' if urls else 'UNKNOWN'),
            dependency_ids=[fid], **{k: v for k, v in dates.items() if k != 'exact_release'})
        row.update({metric: _number(raw.get(metric)) for metric in FINANCIAL_UNITS})
        row['pit_exact'] = bool(urls and dates['exact_release'] and dates['acquired_at'])
        row['data_status'] = 'AVAILABLE' if row['pit_exact'] else 'PIT_UNAVAILABLE'
        if fid in seen:
            if row != seen[fid]:
                raise ValueError(f'Conflicting company-quarter financial context: {fid}')
            continue
        seen[fid] = row
        rows.append(row)
    return sorted(rows, key=lambda r: (r['company'], r['report_date']))


def _margin_audit(audit: dict, company: str, *, cutoff: pd.Timestamp, usable: bool) -> dict:
    margin=audit.get('margin_validation') or {}
    known=_time(margin.get('as_of'),field='margin.as_of')
    comparisons=[]
    if usable and margin.get('contract')=='ABFMarginValidationV1' and known is not None and known<=cutoff:
        for raw in margin.get('comparisons',[]):
            if raw.get('company')!=company or raw.get('product')!='ABF':
                continue
            row=deepcopy(raw)
            # The page packages the audit; it cannot authorize an ABF forecast from a proxy.
            if row.get('is_proxy',True) or row.get('source_scope')!='COMPANY_PRODUCT':
                row['forecast_beta']=None
                if row.get('eligibility')=='eligible':
                    row['eligibility']='reject'
                    row['rejection_reasons']=sorted(set(row.get('rejection_reasons',[])+['PROXY_SCOPE']))
            comparisons.append(row)
    return dict(contract='ABFMarginValidationV1',
        data_status='AVAILABLE' if any(r.get('sample_rows') for r in comparisons) else 'UNAVAILABLE',
        comparisons=comparisons,policy=deepcopy(margin.get('policy',{})),
        source_scope='COMPANY_TOTAL',is_proxy=True,forecast_beta=None)


def _unavailable_detail(company: str, scenario: str, metric: str, ft: str, tt: str,
                        lag: int, reason: str) -> dict:
    return dict(comparison_id=f'{scenario}|{metric}|{company}|{ft}|{tt}|{lag}',
        company=company, product='ABF', scenario=scenario, metric_id=metric,
        target_metric=f'abf_company_revenue_yoy::{company}',
        feature_transform=ft, target_transform=tt, lag_months=lag, timing_class='LEADING',
        source_scope='INDUSTRY_AGGREGATE', target_scope='COMPANY_TOTAL', is_proxy=True,
        feature_unit='percent' if ft == 'LEVEL' else 'percentage_points',
        target_unit='percent' if tt == 'LEVEL' else 'percentage_points',
        evidence_status='UNKNOWN', data_status='UNAVAILABLE', eligibility='reject',
        sample_size=0, spearman=None, bootstrap_ci_low=None, bootstrap_ci_high=None,
        permutation_p=None, fdr_q=None, pit_exact=False, source_lineage_complete=False,
        gates={}, oos_folds=[], sample_rows=[], source_urls=[], reasons=[reason])


def _audit_detail(raw: dict, *, cutoff: pd.Timestamp, unavailable: dict) -> dict | None:
    _status(raw)
    for sample in [raw, *raw.get('sample_rows', [])]:
        for field in ('feature_available_at', 'target_available_at', 'available_at',
                      'observation_date', 'target_observation_date', *ACQUISITION_FIELDS,
                      'release_date', 'target_release_date'):
            time = _time(sample.get(field), field=field, end_of_day=field not in {'observation_date', 'target_observation_date'})
            if time is not None and time > cutoff:
                return None  # Filtering rows without re-auditing would mislabel statistics.
        bounds = [_time(sample.get(k), field=k) for k in ACQUISITION_FIELDS]
        audited = [_time(sample.get(k), field=k) for k in ('feature_available_at', 'available_at')]
        if any(bound > used for bound in bounds if bound is not None for used in audited if used is not None):
            withheld = deepcopy(unavailable)
            withheld['reasons'] = ['AUDIT_REQUIRES_REVALIDATION']
            return withheld
    detail = deepcopy(raw)
    detail.setdefault('pit_exact', False)
    detail.setdefault('is_proxy', True)
    detail.setdefault('source_lineage_complete', False)
    detail.setdefault('evidence_status', 'UNKNOWN')
    detail.setdefault('sample_rows', [])
    detail.setdefault('oos_folds', [])
    detail.setdefault('gates', {})
    detail.setdefault('source_urls', [])
    detail.setdefault('data_status', 'UNAVAILABLE')
    detail.setdefault('eligibility', 'reject')
    if detail['pit_exact'] and any(not sample.get('release_date') or not sample.get('target_release_date')
                                   for sample in detail['sample_rows']):
        detail['pit_exact'] = False
    if not detail['sample_rows']:
        detail['pit_exact'] = False
    if detail['sample_rows']:
        complete = all(_urls(sample) and sample.get('dependency_ids') and
                       sample.get('source_lineage_complete') is True for sample in detail['sample_rows'])
        metadata = all(all(sample.get(k) for k in ('available_at', 'feature_available_at',
            'target_available_at', 'observation_date', 'target_observation_date', 'signal_generated_at'))
            and 'release_date' in sample for sample in detail['sample_rows'])
        detail['source_lineage_complete'] = bool(detail['source_lineage_complete'] and complete)
        if not complete or not metadata:
            detail.update(data_status='UNAVAILABLE', eligibility='reject', pit_exact=False)
            detail['gates']['source_lineage'] = False
            detail['reasons'] = [*detail.get('reasons', []), 'INCOMPLETE_AUDIT_METADATA']
    if raw.get('eligibility') == 'eligible' and (
            detail['is_proxy'] or not detail['pit_exact'] or not detail['source_lineage_complete']
            or detail['data_status'] != 'AVAILABLE' or not detail['gates'] or not all(detail['gates'].values())
            or detail.get('source_scope') != 'COMPANY_PRODUCT' or detail.get('target_scope') != 'COMPANY_PRODUCT'
            or any(sample.get('is_proxy') is not False or sample.get('pit_exact') is not True
                   for sample in detail['sample_rows'])):
        withheld = deepcopy(unavailable)
        withheld['reasons'] = ['AUDIT_REQUIRES_REVALIDATION']
        return withheld
    return detail


def _company_details(audit: dict, company: str, *, cutoff: pd.Timestamp, usable: bool) -> dict:
    source = audit.get('details') or {}
    rows = list(source.values()) if isinstance(source, dict) else source
    metrics = list(dict.fromkeys([*METRICS, *(r.get('metric_id') for r in rows if r.get('metric_id'))]))
    lag = int((audit.get('policy') or {}).get('lag_months', 1))
    lags = sorted({lag, *(int(r['lag_months']) for r in rows if r.get('lag_months') is not None)})
    details = {}
    for scenario, metric, ft, tt, lag in product(SCENARIOS, metrics, TRANSFORMS, TRANSFORMS, lags):
        empty = _unavailable_detail(company, scenario, metric, ft, tt, lag,
                                   'MISSING_AUDIT_EVIDENCE' if usable else 'AUDIT_UNAVAILABLE_OR_AFTER_AS_OF')
        details[empty['comparison_id']] = empty
    if usable:
        for raw in rows:
            if raw.get('company') != company or raw.get('product') != 'ABF':
                continue
            cid = raw.get('comparison_id')
            if cid not in details:
                raise ValueError(f'Invalid predeclared comparison identity: {cid}')
            expected = details[cid]
            if any(raw.get(k) != expected[k] for k in ('company', 'product', 'scenario', 'metric_id',
                   'feature_transform', 'target_transform', 'lag_months')):
                raise ValueError(f'Conflicting audit comparison identity: {cid}')
            copied = _audit_detail(raw, cutoff=cutoff, unavailable=expected)
            if copied is not None:
                details[cid] = copied
            else:
                expected['reasons'] = ['AUDIT_SAMPLE_AFTER_AS_OF']
    return details


def _trend(audit: dict, company: str, *, cutoff: pd.Timestamp, usable: bool, generated_at: str) -> dict:
    observations = []
    for raw in audit.get('observations', []) if usable else []:
        if raw.get('transform') != 'LEVEL' or raw.get('company') not in {'INDUSTRY', company}:
            continue
        _status(raw)
        acquisitions = [_time(raw.get(k), field=k) for k in ACQUISITION_FIELDS]
        if any(time is not None and time > cutoff for time in acquisitions):
            continue
        dates = _dates(raw, generated_at=generated_at)
        if dates['observation_date'] is None or not _known(dates, cutoff):
            continue
        observation = deepcopy(raw)
        if any(time is not None for time in acquisitions):
            observation.update(available_at=dates['available_at'], acquired_at=dates['acquired_at'])
        observations.append(observation)
    return dict(data_status='AVAILABLE' if observations else 'UNAVAILABLE', transform='LEVEL',
                observations=observations, policy='Recorded YoY rates remain CHANGE measures; LEVEL is identity.')


def _missing_inputs(facts: list[dict]) -> list[dict]:
    rows = []
    for metric in OPERATING_INPUTS:
        actual = [f for f in facts if f['metric_id'] == metric and f['product'] == 'ABF'
                  and not f['is_proxy'] and not f['is_forward_looking']
                  and f['evidence_status'] == 'DISCLOSED' and f['value'] is not None]
        latest = max(actual, key=lambda f: (f['observation_date'], f['available_at'])) if actual else None
        rows.append(dict(metric_id=metric, product='ABF', source_scope='COMPANY_PRODUCT', is_proxy=False,
            value=latest['value'] if latest else None, unit=latest.get('unit') if latest else None,
            evidence_status=latest['evidence_status'] if latest else 'UNKNOWN',
            data_status=latest['data_status'] if latest else 'MISSING',
            evidence_ids=[latest['fact_id']] if latest else [],
            reason=None if latest else 'No reviewed, company-product disclosure available; proxy data cannot fill this input.'))
    return rows


def _sources(details: dict, observations: list, facts: list, financial: list) -> list[dict]:
    sources = {}
    records = [(cid, d) for cid, d in details.items()]
    records += [(o.get('observation_id'), o) for o in observations]
    records += [(f['fact_id'], f) for f in facts]
    records += [(r['evidence_id'], r) for r in financial]
    for evidence_id, row in records:
        for url in _urls(row):
            sources.setdefault(url, set())
            if evidence_id:
                sources[url].add(evidence_id)
    return [dict(source_url=url, evidence_ids=sorted(ids)) for url, ids in sorted(sources.items())]


def build_company_survey(audit: dict, factor: pd.DataFrame, facts: list | dict, *, as_of: str) -> dict:
    """Build ABFCompanySurveyV1 from existing audit evidence and optional reviewed facts.

    ``as_of`` is the knowledge cutoff, not the signal creation time. Date-only
    availability uses Taiwan end of day; all acquisition bounds cap a replay.
    No files are opened and no network calls or model fitting take place.
    """
    cutoff = _time(as_of, field='as_of')
    if cutoff is None:
        raise ValueError('as_of timestamp is required')
    generated_at = datetime.now(timezone.utc).isoformat()
    audit_cutoff = _time(audit.get('as_of'), field='audit.as_of')
    usable = audit_cutoff is not None and audit_cutoff <= cutoff
    reviewed, rejected = _reviewed_facts(facts, cutoff=cutoff, generated_at=generated_at)
    financial = _financial_rows(factor, cutoff=cutoff, generated_at=generated_at)
    companies = []
    for company in COMPANIES:
        details = _company_details(audit, company, cutoff=cutoff, usable=usable)
        trend = _trend(audit, company, cutoff=cutoff, usable=usable, generated_at=generated_at)
        company_facts = [f for f in reviewed if f['company'] == company]
        history = [row for row in financial if row['company'] == company]
        evidence_ids = [cid for cid, d in details.items() if d.get('sample_rows')]
        evidence_ids += [f['fact_id'] for f in company_facts]
        # Unavailable comparison IDs still identify the exact evidence gap being queried.
        references = evidence_ids or list(details)
        scenarios = {}
        for scenario in SCENARIOS:
            selected = [d for d in details.values() if d['scenario'] == scenario]
            scenarios[scenario] = dict(scenario=scenario,
                options=[{k: d[k] for k in ('comparison_id', 'metric_id', 'feature_transform', 'target_transform', 'lag_months')}
                         for d in selected],
                comparison_ids=[d['comparison_id'] for d in selected],
                data_status='AVAILABLE' if any(d.get('sample_rows') for d in selected) else 'UNAVAILABLE',
                eligibility_counts={state: sum(d.get('eligibility') == state for d in selected)
                                    for state in ('eligible', 'support-only', 'reject')})
        counts = {s: scenarios[s]['eligibility_counts'] for s in SCENARIOS}
        has_evidence = bool(evidence_ids or history or trend['observations'])
        fact_text = ' '.join(f['statement'] for f in sorted(company_facts,
                            key=lambda f: f['observation_date'], reverse=True)[:4] if f.get('statement'))
        assessment = dict(evidence_status='INFERRED' if has_evidence else 'UNKNOWN',
            status='RESEARCH_ONLY' if has_evidence else 'UNAVAILABLE', evidence_ids=references,
            summary=(f"{COMPANY_NAMES[company]} ABF: upside {counts['UPSIDE']['eligible']} eligible, "
                     f"{counts['UPSIDE']['support-only']} support-only; downside {counts['DOWNSIDE']['eligible']} eligible, "
                     f"{counts['DOWNSIDE']['support-only']} support-only. "
                     f"{len(company_facts)} reviewed company facts; {len(history)} company-total financial periods. "
                     'Industry/company-total proxies do not identify ABF product revenue or margin. '
                     'The financial bridge is uncalibrated.' + (' Reviewed facts: '+fact_text if fact_text else '')),
            fact_summary=[dict(statement=f.get('statement'), fact_id=f['fact_id'], metric_id=f['metric_id'],
                               value=f['value'], unit=f.get('unit'), product=f['product']) for f in company_facts])
        handoff = [deepcopy(h) for h in audit.get('calibration_handoff', [])
                   if usable and h.get('company') == company and h.get('product') == 'ABF']
        verified=sum(r['accounting_basis_verified'] and r['accounting_basis']=='STANDALONE_QUARTER'
                     for r in history)
        record = dict(company=company, stock_id=company[:4], name=COMPANY_NAMES[company], product='ABF',
            data_status='AVAILABLE' if has_evidence else 'UNAVAILABLE', assessment=assessment,
            scenario_options=list(SCENARIOS), scenarios=scenarios, details=details, trend=trend,
            financial_context=dict(data_status='AVAILABLE' if history else 'UNAVAILABLE', rows=history,
                source_scope='COMPANY_TOTAL', source_product='All company products', is_proxy=True,
                accounting_basis=('STANDALONE_QUARTER' if history and verified==len(history)
                                  else 'PARTIALLY_VERIFIED' if verified else 'UNKNOWN'),
                basis_coverage=dict(periods=len(history),verified_standalone=verified,
                    unverified=len(history)-verified,
                    mismatches=sum(r.get('financial_value_verification')=='MISMATCH' for r in history)),
                units=dict(FINANCIAL_UNITS)),
            primary_facts=company_facts, rejected_facts=[f for f in rejected if f['company'] == company],
            missing_inputs=_missing_inputs(company_facts),
            financial_bridge=dict(status='NOT_CALIBRATED', beta=None, evidence_status='UNKNOWN',
                reason='Verify ABF attribution, standalone-quarter basis, exact PIT and company-specific robustness before fitting.',
                stages=[dict(stage=stage, status='NOT_CALIBRATED', beta=None, evidence_ids=references)
                        for stage in ('Driver → Revenue', 'Revenue → GM', 'GM → EPS')],
                audit_handoff=handoff,margin_audit=_margin_audit(audit,company,cutoff=cutoff,usable=usable)),
            operating_mechanism=[dict(statement='ABF orders, utilization, ASP and product mix may affect revenue and margin.',
                evidence_status='INFERRED', status='UNVALIDATED_HYPOTHESIS', evidence_ids=references)],
            research_questions=[dict(question=question, evidence_ids=references, evidence_status='UNKNOWN') for question in (
                'Are company-product backlog, customer inventory, utilization, ASP and product mix publicly measurable?',
                'Do independently validated upside and downside relations survive chronological OOS and FDR?',
                'Can standalone-quarter revenue and gross profit with exact availability support an ABF-specific bridge?')],
            invalidation_conditions=[dict(condition=condition, evidence_ids=references, evidence_status='INFERRED') for condition in (
                'Invalidate the reading if a source revision changes the audited direction, OOS stability or uncertainty gates.',
                'Do not treat industry or company-total correlations as ABF forecasts without product attribution and exact PIT.',
                'Withdraw financial interpretation if accounting basis, publication time or acquisition lineage cannot be verified.')],
            sources=_sources(details, trend['observations'], company_facts, history))
        companies.append(record)
    return _json_value(dict(contract='ABFCompanySurveyV1', owner='chain_survey',
        analysis_unit=['company', 'product'], as_of=_iso(cutoff), generated_at=generated_at,
        audit_metadata={k: deepcopy(audit.get(k)) for k in ('contract', 'as_of', 'generated_at',
                        'input_manifest', 'code_revision', 'working_tree_dirty')},
        policy=dict(transform_selection='NONE_PREDECLARED_2x2', statistical_authority='ABFSemanticsValidationV1',
            audit_usable_at_cutoff=usable, availability='MAX_SOURCE_RELEASE_AVAILABILITY_ACQUISITION',
            date_only_availability='TAIWAN_END_OF_DAY', financial_bridge='NOT_CALIBRATED'),
        companies=companies, rejected_facts=rejected,
        downside_source_priorities=deepcopy(audit.get('downside_source_priorities', [])) if usable else []))
