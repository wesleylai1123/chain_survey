"""Export audited ABF comparisons and conservative financial calibration handoff."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from core.abf_transform_validation import COMPANIES, compare_abf_transforms
from core.abf_margin_transmission import scan_revenue_to_margin
from core.metric_semantics import normalize_history, timestamp, transform_observations


def clean(value):
    if isinstance(value,dict):
        return {str(k):clean(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):
        return [clean(v) for v in value]
    if isinstance(value,(np.bool_,bool)):
        return bool(value)
    if isinstance(value,(np.integer,)):
        return int(value)
    if isinstance(value,(float,np.floating)):
        return float(value) if np.isfinite(value) else None
    if value is pd.NA or value is pd.NaT:
        return None
    return value


def _write(path: Path, value):
    path.write_text(json.dumps(clean(value),ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def factor_known_at(factor: pd.DataFrame, *, as_of: str) -> pd.DataFrame:
    """Keep only financial snapshots known by the replay cutoff."""
    if factor.empty or 'available_date' not in factor:
        return factor.iloc[:0].copy()
    cutoff=timestamp(as_of)

    def bound(value, *, daily=False):
        if value is None or pd.isna(value) or not str(value).strip():
            return None
        parsed=pd.Timestamp(value)
        if pd.isna(parsed):
            return None
        if parsed.tzinfo is None:
            if not daily and len(str(value))!=10:
                raise ValueError(f'Timezone-aware acquisition/publication timestamp required: {value}')
            parsed=(parsed.normalize()+pd.Timedelta(days=1)-pd.Timedelta(microseconds=1)).tz_localize('Asia/Taipei')
        return parsed.tz_convert('UTC')

    def known(row):
        available=bound(row.get('available_date'),daily=True)
        if available is None:
            return False
        times=[available,bound(row.get('report_date'),daily=True)]
        times.extend(bound(row.get(field)) for field in (
            'observation_date','available_at','filing_published_at','release_date',
            'acquired_at','first_seen_at','snapshot_acquired_at'))
        return all(t<=cutoff for t in times if t is not None)

    return factor.loc[[known(row) for row in factor.to_dict('records')]].copy()


def build_report(history: pd.DataFrame, factor: pd.DataFrame, *, as_of: str, iterations: int=999) -> dict:
    table,details=compare_abf_transforms(history,as_of=as_of,iterations=iterations)
    signals=normalize_history(history,as_of=as_of)
    observations=[]
    for transform in ('LEVEL','CHANGE'):
        observations.extend(transform_observations(signals,transform).to_dict('records'))
    factor=factor_known_at(factor,as_of=as_of)
    margin=scan_revenue_to_margin(factor) if not factor.empty else pd.DataFrame()
    handoff=[]
    for company in COMPANIES:
        comparisons=table[table.company.eq(company)]
        margin_evidence=[]
        for record in margin.to_dict('records'):
            own=next((r for r in record['company_product_results'] if r['company']==company),None)
            if own:
                margin_evidence.append(dict(feature=record['feature'],target=record['target'],lag_quarters=record['lag_quarters'],
                    accounting_basis=record['accounting_basis'],evidence_status='DERIVED',
                    eligibility='reject',reason='Company-specific OOS, bootstrap, permutation and FDR not yet validated',
                    pooled_reference={'fdr_q':record['fdr_q'],'permutation_p':record['permutation_p'],
                                      'eligibility':record['eligibility'],'scope':'THREE_COMPANY_EXPLORATION'},
                    company_result=own))
        handoff.append(dict(company=company,product='ABF',evidence_status='INFERRED',
            stages=[dict(stage='Driver → Revenue',status='NOT_CALIBRATED',beta=None,
                         reason='Industry and company-total proxies; no eligible ABF product relation',
                         comparison_ids=comparisons.comparison_id.tolist()),
                    dict(stage='Revenue → GM',status='CANDIDATE_ONLY' if margin_evidence else 'UNAVAILABLE',beta=None,
                         reason='Verify standalone-quarter accounting, exact PIT and product mix before fitting ABF margin beta',
                         evidence=margin_evidence),
                    dict(stage='GM → EPS',status='UNAVAILABLE',beta=None,
                         reason='No verified ABF product gross-profit, OPEX, tax, nonoperating and diluted-share bridge')]))
    priority=[]
    for metric in table.metric_id.unique():
        subset=table[table.metric_id.eq(metric)&table.scenario.eq('DOWNSIDE')]
        priority.append(dict(source_metric=metric,scenario='DOWNSIDE',priority=1,
            data_status='AVAILABLE' if subset.data_status.eq('AVAILABLE').any() else 'MISSING',
            eligibility='support-only' if subset.eligibility.eq('support-only').any() else 'reject',
            action='Extend PIT history and validate Company × Product early-warning stability'))
    for metric in ('abf_orders_backlog','abf_customer_inventory','abf_utilization','abf_pricing','abf_product_mix'):
        priority.append(dict(source_metric=metric,scenario='DOWNSIDE',priority=1,data_status='MISSING',
            evidence_status='UNKNOWN',eligibility='reject',value=None,
            action='Acquire verified company-product observations with publication timestamps; do not substitute assumptions'))
    return dict(contract='ABFSemanticsValidationV1',owner='chain_survey',as_of=as_of,
        generated_at=datetime.now(timezone.utc).isoformat(),analysis_unit=['company','product'],
        policy=dict(transform_selection='NONE_PREDECLARED_2x2',lag_months=1,
            fdr_family='All metrics × companies × transform pairs, independently per scenario; missing p=1',
            holdout='Fixed calendar order; purge training labels unavailable before first test feature',
            conditional_resampling='Calendar-contiguous blocks; gaps are block boundaries',
            iterations=iterations,company_denominator=len(COMPANIES),minimum_samples=10),
        comparisons=table.to_dict('records'),details=details,observations=observations,
        calibration_handoff=handoff,downside_source_priorities=priority)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--history',type=Path,default=ROOT/'data/history/free_industry_history_panel.csv')
    parser.add_argument('--factor',type=Path,default=ROOT/'artifacts/factor_validation_dataset.csv')
    parser.add_argument('--as-of',default=datetime.now(timezone.utc).isoformat())
    parser.add_argument('--iterations',type=int,default=999)
    parser.add_argument('--output-dir',type=Path,default=ROOT/'artifacts')
    args=parser.parse_args(argv)
    history=pd.read_csv(args.history) if args.history.exists() else pd.DataFrame()
    factor=pd.read_csv(args.factor,low_memory=False) if args.factor.exists() else pd.DataFrame()
    report=build_report(history,factor,as_of=args.as_of,iterations=args.iterations)
    inputs={}
    for name,path in [('history',args.history),('factor',args.factor),
                      ('semantics',ROOT/'data/abf_metric_semantics.json'),('schema',ROOT/'contracts/metric-semantics/v1/schema.json')]:
        inputs[name]={'path':str(path),'sha256':sha256(path.read_bytes()).hexdigest() if path.exists() else None,
                      'data_status':'AVAILABLE' if path.exists() else 'UNAVAILABLE'}
    report['input_manifest']=inputs
    report['code_revision']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    report['working_tree_dirty']=bool(subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=ROOT,text=True).strip())
    out=args.output_dir
    out.mkdir(parents=True,exist_ok=True)
    _write(out/'abf_semantics_validation.json',report)
    table=pd.DataFrame(report['comparisons'])
    table.to_csv(out/'abf_transform_comparison.csv',index=False)
    _write(out/'abf_calibration_handoff.json',report['calibration_handoff'])
    _write(out/'abf_downside_source_priorities.json',report['downside_source_priorities'])
    columns=['company','product','scenario','metric_id','feature_transform','target_transform','sample_size','spearman','oos_sign_stability','company_sign_agreement','fdr_q','data_status','eligibility']
    counts=table.groupby(['scenario','eligibility']).size().to_string()
    html=f'''<!doctype html><meta charset="utf-8"><title>ABF semantics validation</title>
    <style>body{{font:15px system-ui;margin:40px;color:#172033;background:#f3f6fa}}table{{border-collapse:collapse;background:white;font-size:12px}}th,td{{padding:9px;border:1px solid #d8e0ea}}h1{{color:#0f172a}}pre{{background:white;padding:16px}}</style>
    <h1>ABF · Company × Product evidence</h1><p>As of {escape(args.as_of)} · Code {escape(report['code_revision'])}</p>
    <p>LEVEL preserves the recorded YoY rate (%). CHANGE is its calendar-month difference (percentage points).
    Company-total revenue and PCB industry data are proxies for ABF. Statistical validation does not establish product attribution.</p>
    <p>Upside and downside own their samples, sources, PIT, bootstrap, permutation, company results and FDR family.
    OOS folds are chronological with label-availability purging. All four transform pairs were declared in advance.</p>
    <pre>{escape(counts)}</pre>{table[columns].to_html(index=False,escape=True,na_rep='UNAVAILABLE')}
    <h2>Calibration handoff</h2><p>Driver → Revenue → GM → EPS remains uncalibrated at ABF product level.
    Missing product mix, orders, inventory, utilization and pricing are shown as missing, with null values.</p>
    <p>Full used rows, timestamps, dependency IDs, gates, OOS folds and input hashes: <a href="abf_semantics_validation.json">JSON evidence</a>.</p>'''
    (out/'abf_semantics_validation.html').write_text(html,encoding='utf-8')
    print('ABF_SEMANTICS_VALIDATION_OK',len(table),'comparisons',len(report['observations']),'observations')
    print(counts)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
