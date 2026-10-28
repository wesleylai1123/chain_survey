"""Primary-document reconciliation for company-total quarterly financial proxies."""
from __future__ import annotations

import math
import re
from urllib.parse import urlparse

import pandas as pd

OFFICIAL_HOSTS = {'unimicron.com','www.unimicron.com','kinsus.com.tw','www.kinsus.com.tw',
    'nanyapcb.com.tw','www.nanyapcb.com.tw','doc.twse.com.tw','mops.twse.com.tw','mopsov.twse.com.tw'}
SCALES = {'TWD': 1, 'TWD thousand': 1000, 'TWD million': 1000000}


def _precision(record: dict) -> float | None:
    places=record.get('published_decimal_places')
    if type(places) is not int or not 0<=places<=6 or record.get('unit') not in SCALES:
        return None
    return SCALES[record['unit']]*10**(-places)/2


def _q1_derivation(record: dict) -> dict | None:
    """Recognize only the inspected same-document H1 minus Q2 calculation."""
    try:
        derivation=record['derivation']
        h1,q2=derivation['inputs']['h1'],derivation['inputs']['q2']
        year=pd.Timestamp(record['period_end']).year
        if (derivation['method']!='H1_MINUS_Q2' or record['period_end']!=f'{year}-03-31'
                or h1['period_start']!=f'{year}-01-01' or q2['period_start']!=f'{year}-04-01'
                or h1['period_end']!=f'{year}-06-30' or q2['period_end']!=f'{year}-06-30'):
            return None
        bounds=[]
        tolerances=[]
        for name,source in (('h1',h1),('q2',q2)):
            if (source['unit']!=record['unit']
                    or source.get('company',record['company'])!=record['company']
                    or source.get('source_url',record['source_url'])!=record['source_url']
                    or source.get('source_document',record['source_document'])!=record['source_document']
                    or source.get('source_sha256',record['source_sha256'])!=record['source_sha256']
                    or source.get('consolidation',record['consolidation'])!='CONSOLIDATED'
                    or source.get('source_scope',record['source_scope'])!='COMPANY_TOTAL'
                    or source.get('accounting_basis','YTD' if name=='h1' else 'STANDALONE_QUARTER')
                       !=('YTD' if name=='h1' else 'STANDALONE_QUARTER')):
                return None
            precision=_precision(dict(record,**source))
            if precision is None:
                return None
            tolerances.append(precision)
            for field in ('available_at','acquired_at','release_date'):
                value=evidence_time(source.get(field),date_only=field=='release_date')
                if value is not None:
                    bounds.append(value)
        if not all(math.isfinite(float(record[field])) and
                abs(float(h1[field])-float(q2[field])-float(record[field]))<1e-9
                for field in ('revenue','gross_profit')):
            return None
        return {'bounds':bounds,'tolerance_twd':sum(tolerances),
                'observation_end':evidence_time(h1['period_end'],date_only=True)}
    except (KeyError,TypeError,ValueError):
        return None


def evidence_time(value, *, date_only=False):
    if value is None or pd.isna(value) or not str(value).strip():
        return None
    result=pd.Timestamp(value)
    if pd.isna(result):
        return None
    if result.tzinfo is None:
        if not date_only or len(str(value))!=10:
            raise ValueError('Evidence timestamps require timezone; only declared dates may omit it')
        result=(result.normalize()+pd.Timedelta(days=1)-pd.Timedelta(microseconds=1)).tz_localize('Asia/Taipei')
    return result.tz_convert('UTC')


def reconcile_financial_evidence(panel: pd.DataFrame, reviewed: dict, *, as_of: str) -> pd.DataFrame:
    """Verify accounting basis without changing provider amounts or historical vintages.

    A primary document verifies the inspected column, not when the provider knew it.
    Later comparative columns retain the later document's acquisition bound.
    """
    if reviewed.get('contract')!='ABFQuarterlyFinancialEvidenceV1':
        raise ValueError('Unexpected quarterly financial evidence contract')
    cutoff=evidence_time(as_of)
    if cutoff is None:
        raise ValueError('as_of is required')
    records={}
    for record in reviewed.get('quarter_records',[]):
        key=(record.get('company'),record.get('period_end'))
        if key in records:
            raise ValueError(f'Conflicting reviewed company-quarter records: {key}')
        records[key]=record
    # Work by unique row positions; concatenated company panels may share labels.
    out=panel.reset_index(drop=True).copy()
    defaults=dict(accounting_basis='UNKNOWN',accounting_basis_verified=False,financial_value_verification='UNVERIFIED',
        financial_evidence_id=None,primary_financial_source_url=None,financial_evidence_sha256=None,
        financial_basis_verification_available_at=None,financial_evidence_acquired_at=None,
        financial_release_date=None,financial_pit_exact=False,financial_verified_scope='COMPANY_TOTAL',
        financial_source_page=None,financial_comparative_from_later_document=False,
        financial_period_start=None,financial_published_decimal_places=None,financial_rounding_tolerance_twd=None)
    for field,value in defaults.items():
        out[field]=value
    for index,row in out.iterrows():
        end=pd.Timestamp(row['report_date'])
        record=records.get((str(row['ticker']),end.strftime('%Y-%m-%d')))
        if record is None:
            continue
        out.at[index,'financial_evidence_id']=record.get('evidence_id')
        out.at[index,'financial_value_verification']='INVALID_EVIDENCE'
        url=urlparse(str(record.get('source_url','')))
        if (record.get('accounting_basis')!='STANDALONE_QUARTER'
                or record.get('consolidation')!='CONSOLIDATED'
                or record.get('source_scope')!='COMPANY_TOTAL'
                or record.get('product')!='ABF'
                or record.get('evidence_status') not in {'DISCLOSED','DERIVED'}
                or record.get('unit') not in SCALES
                or not end.is_quarter_end
                or record.get('period_start')!=end.to_period('Q').start_time.strftime('%Y-%m-%d')
                or _precision(record) is None
                or url.scheme!='https' or url.hostname not in OFFICIAL_HOSTS
                or not record.get('source_page') or not record.get('source_document')
                or not record.get('source_excerpt')
                or not re.fullmatch(r'[0-9a-f]{64}',str(record.get('source_sha256','')))):
            continue
        acquired=evidence_time(record.get('acquired_at'))
        available=evidence_time(record.get('available_at'))
        released=evidence_time(record.get('release_date'),date_only=True)
        if acquired is None or available is None:
            continue
        derived=record.get('evidence_status')=='DERIVED'
        derivation=_q1_derivation(record) if derived else None
        if derived and derivation is None:
            continue
        bounds=[t for t in (acquired,available,released) if t is not None]
        if derivation:
            bounds.extend(derivation['bounds'])
        known=max(bounds)
        observation=evidence_time(end.strftime('%Y-%m-%d'),date_only=True)
        if known<observation or (derivation and known<derivation['observation_end']):
            continue
        if known>cutoff:
            out.at[index,'financial_value_verification']='AFTER_AS_OF'
            continue
        scale=SCALES[record['unit']]
        tolerance=derivation['tolerance_twd'] if derivation else _precision(record)
        values=[]
        for field in ('revenue','gross_profit'):
            try:
                primary=float(record[field])*scale
                provider=float(row[field])
            except (ValueError,TypeError,KeyError):
                values=[]
                break
            if not math.isfinite(primary) or not math.isfinite(provider):
                values=[]
                break
            values.append(abs(primary-provider))
        if len(values)!=2 or max(values)>tolerance:
            out.at[index,'financial_value_verification']='MISMATCH'
            continue
        out.at[index,'accounting_basis']='STANDALONE_QUARTER'
        out.at[index,'accounting_basis_verified']=True
        out.at[index,'financial_value_verification']='MATCH' if max(values)==0 else 'ROUNDED_MATCH'
        out.at[index,'primary_financial_source_url']=record['source_url']
        out.at[index,'financial_evidence_sha256']=record['source_sha256']
        out.at[index,'financial_source_page']=record['source_page']
        out.at[index,'financial_period_start']=record['period_start']
        out.at[index,'financial_published_decimal_places']=record['published_decimal_places']
        out.at[index,'financial_rounding_tolerance_twd']=tolerance
        out.at[index,'financial_basis_verification_available_at']=known.isoformat()
        out.at[index,'financial_evidence_acquired_at']=acquired.isoformat()
        out.at[index,'financial_release_date']=released.isoformat() if released is not None else None
        out.at[index,'financial_comparative_from_later_document']=bool(record.get('comparative_period_from_later_document',False))
        # Reconciliation proves current published numbers, not the provider's past vintage.
        out.at[index,'financial_pit_exact']=False
    out.index=panel.index.copy()
    return out
