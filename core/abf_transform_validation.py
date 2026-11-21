"""Predeclared Level/Change comparisons; no winner selection on holdout data."""
from __future__ import annotations

from hashlib import sha256
from itertools import product

import numpy as np
import pandas as pd
from scipy.stats import rankdata

from core.driver_validation_engine import benjamini_hochberg
from core.metric_semantics import normalize_history, timestamp, transform_observations

COMPANIES = ('3037.TW','3189.TW','8046.TW')
METRICS = ('pcb_revenue_yoy','rigid_pcb_export_yoy','pcb_material_revenue_yoy','ccl_export_yoy','ccl_import_yoy')


def _corr(x, y) -> float | None:
    if len(x)<3 or len(set(x))<2 or len(set(y))<2:
        return None
    return float(np.corrcoef(rankdata(x),rankdata(y))[0,1])


def _blocks(frame: pd.DataFrame, size: int=3) -> list[np.ndarray]:
    """Moving blocks stop at calendar gaps, including gaps from conditional samples."""
    months = pd.PeriodIndex(frame['period'],freq='M').asi8
    blocks = []
    for start in range(len(frame)):
        end = start+1
        while end<min(start+size,len(frame)) and months[end]==months[end-1]+1:
            end += 1
        blocks.append(np.arange(start,end))
    return blocks


def _statistics(frame: pd.DataFrame, *, iterations: int, seed: int) -> dict:
    x,y = frame['x'].to_numpy(),frame['y'].to_numpy()
    observed = _corr(x,y)
    result = dict(spearman=observed,bootstrap_ci_low=None,bootstrap_ci_high=None,permutation_p=None)
    if len(frame)<6 or observed is None:
        return result
    rng = np.random.default_rng(seed)
    blocks = _blocks(frame)
    boot = []
    # A fixed attempt count prevents degenerate samples from hanging the process.
    for _ in range(iterations):
        indices = []
        while len(indices)<len(frame):
            indices.extend(blocks[int(rng.integers(len(blocks)))])
        sample = np.asarray(indices[:len(frame)])
        value = _corr(x[sample],y[sample])
        if value is not None:
            boot.append(value)
    if len(boot)>=max(10,iterations//2):
        result['bootstrap_ci_low'],result['bootstrap_ci_high'] = map(float,np.quantile(boot,[.025,.975]))
    # Nonoverlapping calendar blocks for the permutation null.
    parts, cursor = [],0
    while cursor<len(frame):
        block = blocks[cursor]
        parts.append(y[block])
        cursor = int(block[-1])+1
    exceed = 0
    for _ in range(iterations):
        shuffled = np.concatenate([parts[i] for i in rng.permutation(len(parts))])
        value = _corr(x,shuffled)
        exceed += value is not None and abs(value)>=abs(observed)-1e-12
    result['permutation_p'] = float((1+exceed)/(1+iterations))
    return result


def _aligned(feature: pd.DataFrame, target: pd.DataFrame, lag: int) -> pd.DataFrame:
    columns = ['period','x','y','feature_available_at','target_available_at','target_observation_date',
               'feature_observation_id','target_observation_id','source_urls','source_lineage_complete','pit_exact','is_proxy']
    if feature.empty or target.empty:
        return pd.DataFrame(columns=columns)
    targets = {r['period']:r for r in target.to_dict('records')}
    rows = []
    for f in feature.to_dict('records'):
        t = targets.get(str(pd.Period(f['period'],'M')+lag))
        if t is None or pd.isna(f['signal_value']) or pd.isna(t['signal_value']):
            continue
        if not f['available_at'] or not t['available_at']:
            continue
        # Forecasting must precede the economic target, not just its later release.
        if timestamp(f['available_at'])>timestamp(t['observation_date']):
            continue
        rows.append(dict(period=f['period'],x=f['signal_value'],y=t['signal_value'],
            feature_available_at=f['available_at'],target_available_at=t['available_at'],
            observation_date=f['observation_date'],release_date=f['release_date'],
            available_at=f['available_at'],signal_generated_at=f['signal_generated_at'],
            target_observation_date=t['observation_date'],target_release_date=t['release_date'],
            feature_observation_id=f['observation_id'],target_observation_id=t['observation_id'],
            dependency_ids=f['dependency_ids']+t['dependency_ids'],
            source_urls=sorted(set(f['source_urls']+t['source_urls'])),
            source_lineage_complete=all(r.get('source_lineage_complete',bool(r['source_urls'])) for r in (f,t)),
            pit_exact=f['pit_basis']==t['pit_basis']=='SOURCE_REPORTED',
            is_proxy=bool(f['is_proxy'] or t['is_proxy'])))
    return pd.DataFrame(rows,columns=list(dict.fromkeys(columns+list(rows[0] if rows else [])))).sort_values('period').reset_index(drop=True)


def _side(frame: pd.DataFrame, scenario: str, expected_sign: int) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    beneficial = frame['x']*expected_sign
    return frame[beneficial.gt(0) if scenario=='UPSIDE' else beneficial.lt(0)].copy()


def _oos(frame: pd.DataFrame, scenario: str, expected_sign: int) -> list[dict]:
    folds = []
    # Fixed chronological boundaries from unconditional data, before side selection.
    for start,end in ((.50,.65),(.65,.80),(.80,1.0)):
        test = frame.iloc[int(len(frame)*start):int(len(frame)*end)]
        if test.empty:
            continue
        cutoff = test['feature_available_at'].min()
        train = frame.iloc[:int(len(frame)*start)]
        train = train[train['target_available_at']<cutoff]
        train_side,test_side = _side(train,scenario,expected_sign),_side(test,scenario,expected_sign)
        folds.append(dict(train_size=len(train_side),test_size=len(test_side),
            train_spearman=_corr(train_side['x'],train_side['y']),
            test_spearman=_corr(test_side['x'],test_side['y']),
            train_last_label_available_at=train['target_available_at'].max() if len(train) else None,
            test_first_feature_available_at=cutoff,
            first_test_period=test.iloc[0]['period'],last_test_period=test.iloc[-1]['period']))
    return folds


def compare_abf_transforms(history: pd.DataFrame, *, as_of: str, metrics: tuple[str,...]=METRICS,
                           iterations: int=999, lag_months: int=1,
                           expected_signs: dict[str,int] | None=None) -> tuple[pd.DataFrame,dict]:
    if iterations<19:
        raise ValueError('At least 19 resamples required')
    if lag_months<1:
        raise ValueError('Leading early-warning comparison requires positive month lag')
    normalized = normalize_history(history,as_of=as_of)
    transformed = {t:transform_observations(normalized,t) for t in ('LEVEL','CHANGE')}
    rows,details = [],{}
    for metric,scenario,ft,tt,company in product(metrics,('UPSIDE','DOWNSIDE'),('LEVEL','CHANGE'),('LEVEL','CHANGE'),COMPANIES):
        sign = (expected_signs or {}).get(metric,1)
        if sign not in {-1,1}:
            raise ValueError('Expected sign must be predeclared as -1 or +1')
        target = f'abf_company_revenue_yoy::{company}'
        feature_frame,target_frame = transformed[ft],transformed[tt]
        feature = feature_frame[feature_frame.metric_id==metric] if not feature_frame.empty else pd.DataFrame()
        target_data = target_frame[target_frame.metric_id==target] if not target_frame.empty else pd.DataFrame()
        aligned = _aligned(feature,target_data,lag_months)
        side = _side(aligned,scenario,sign)
        key = f'{scenario}|{metric}|{company}|{ft}|{tt}|{lag_months}'
        seed = int(sha256(key.encode()).hexdigest()[:8],16)
        stats = _statistics(side,iterations=iterations,seed=seed)
        folds = _oos(aligned,scenario,sign)
        oos = [f['test_spearman'] for f in folds if f['test_spearman'] is not None and f['train_size']>=6 and f['test_size']>=3]
        share = sum(v*sign>=.15 for v in oos)/len(folds) if folds else 0.0
        hit = float((side['y']>0 if scenario=='UPSIDE' else side['y']<0).mean()) if len(side) else None
        rho,lo,hi = stats['spearman'],stats['bootstrap_ci_low'],stats['bootstrap_ci_high']
        gates = dict(sample_size=len(side)>=10,correlation_direction=rho is not None and rho*sign>=.2,
            direction_hit=hit is not None and hit>=.6,
            oos_stability=len(oos)>=2 and share>=2/3,
            bootstrap=lo is not None and hi is not None and (lo>0 if sign>0 else hi<0),
            permutation=stats['permutation_p'] is not None and stats['permutation_p']<=.1)
        data_status = 'UNAVAILABLE' if history.empty else ('MISSING' if feature.empty or target_data.empty else ('PIT_UNAVAILABLE' if aligned.empty else 'AVAILABLE'))
        row = dict(comparison_id=key,company=company,product='ABF',scenario=scenario,metric_id=metric,
            target_metric=target,feature_transform=ft,target_transform=tt,lag_months=lag_months,
            timing_class='LEADING',timing_relative_to=target,expected_sign=sign,as_of=as_of,
            measure_kind='CHANGE',feature_unit='percent' if ft=='LEVEL' else 'percentage_points',
            target_unit='percent' if tt=='LEVEL' else 'percentage_points',
            source_scope='INDUSTRY_AGGREGATE',target_scope='COMPANY_TOTAL',
            accounting_basis='CONSOLIDATED_REPORTED',return_basis='NOT_APPLICABLE',
            is_proxy=True,evidence_status='DERIVED' if len(side) else 'UNKNOWN',data_status=data_status,
            sample_size=len(side),**stats,target_direction_hit_rate=hit,oos_sign_stability=share,
            oos_spearman=float(np.median(oos)) if oos else None,
            pit_exact=bool(len(side) and side['pit_exact'].all()),
            source_lineage_complete=bool(len(side) and side['source_lineage_complete'].all()),
            source_urls=sorted({url for urls in side['source_urls'] for url in urls}),
            bootstrap_iterations=iterations,permutation_iterations=iterations,random_seed=seed,
            block_size_months=3,eligibility='reject')
        detail = dict(row,gates=gates,oos_folds=folds,sample_rows=side.to_dict('records'))
        rows.append(row)
        details[key] = detail
    table = pd.DataFrame(rows)
    if table.empty:
        return table,details
    table['fdr_q'] = np.nan
    table['fdr_family_size'] = 0
    for scenario in ('UPSIDE','DOWNSIDE'):
        mask = table.scenario.eq(scenario)
        # Missing comparisons remain in the preregistered family with p=1.
        table.loc[mask,'fdr_q'] = benjamini_hochberg(pd.to_numeric(table.loc[mask,'permutation_p'],errors='coerce').fillna(1)).to_numpy()
        table.loc[mask,'fdr_family_size'] = int(mask.sum())
    table['company_sign_agreement'] = 0.0
    for _,group in table.groupby(['scenario','metric_id','feature_transform','target_transform']):
        cross = group[['company','sample_size','spearman','oos_sign_stability']].to_dict('records')
        agreement = sum(r['sample_size']>=10 and pd.notna(r['spearman']) and r['spearman']*int(group.iloc[0].expected_sign)>0 for r in cross)/len(COMPANIES)
        for idx in group.index:
            row = table.loc[idx]
            detail = details[row.comparison_id]
            detail['gates'].update(fdr=bool(row.fdr_q<=.1),cross_company=agreement>=2/3,
                source_lineage=bool(row.source_lineage_complete))
            stats_pass = all(detail['gates'].values())
            eligibility = 'support-only' if stats_pass else 'reject'
            # Proxy scope/PIT are separate from statistical eligibility.
            if stats_pass and not row.is_proxy and row.pit_exact:
                eligibility = 'eligible'
            table.at[idx,'company_sign_agreement'] = agreement
            table.at[idx,'eligibility'] = eligibility
            detail.update(fdr_q=float(row.fdr_q),fdr_family_size=int(row.fdr_family_size),
                company_sign_agreement=agreement,cross_company=cross,eligibility=eligibility,
                reasons=[k for k,v in detail['gates'].items() if not v]+(['PROXY_SCOPE_OR_PIT'] if row.is_proxy or not row.pit_exact else []))
    return table,details
