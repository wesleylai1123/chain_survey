"""Look-through and research context; neither is a forecast or driver promotion."""
from __future__ import annotations

from collections import defaultdict
import math

from core.indicator_taxonomy import indicator_table
from core.multi_asset.adapters import available, timestamp

ABF_COMPANIES = {'3037.TW', '3189.TW', '8046.TW'}


def build_exposures(request):
    output = []
    for instrument in request['instruments']:
        iid = instrument['instrument_id']
        if instrument['asset_type'] != 'etf':
            continue
        snapshots = [r for r in request.get('holdings', []) if r['instrument_id'] == iid
            and available(r, request['as_of']) and r['period'] <= timestamp(request['as_of']).date().isoformat()]
        if not snapshots:
            output.append(dict(instrument_id=iid, status='MISSING', coverage=0.0, unknown_weight=1.0,
                securities={}, sectors={'UNKNOWN': 1.0}, currencies={'UNKNOWN': 1.0}, factors={},
                note='Quote currency does not establish underlying FX exposure.'))
            continue
        snapshots.sort(key=lambda r: (r['period'], max(timestamp(r['published_at']), timestamp(r['acquired_at']))))
        latest = snapshots[-1]
        tied = [r for r in snapshots if r['period'] == latest['period'] and
            max(timestamp(r['published_at']), timestamp(r['acquired_at'])) == max(timestamp(latest['published_at']), timestamp(latest['acquired_at']))]
        if any(r != latest for r in tied):
            raise ValueError('Ambiguous equal-time holdings snapshots')
        positions = latest['positions']
        ids = [p['security_id'] for p in positions]
        weights = [p['weight'] for p in positions]
        if len(set(ids)) != len(ids) or any(not isinstance(w, (int, float)) or isinstance(w, bool) or not math.isfinite(w) or not 0 <= w <= 1 for w in weights):
            raise ValueError('Invalid or duplicate holdings')
        coverage = math.fsum(weights)
        if coverage > 1 + 1e-9:
            raise ValueError('Holdings weights exceed one')
        residual = max(0.0, 1 - coverage)
        sectors, currencies = defaultdict(float), defaultdict(float)
        factors = {}
        for p in positions:
            sectors[p.get('sector') or 'UNKNOWN'] += p['weight']
            currencies[p.get('currency') or 'UNKNOWN'] += p['weight']
            for key, loading in p.get('factors', {}).items():
                if loading is None:
                    continue
                if not math.isfinite(loading):
                    raise ValueError('Non-finite factor loading')
                target = factors.setdefault(key, dict(weighted_loading=0.0, coverage=0.0))
                target['weighted_loading'] += p['weight'] * loading
                target['coverage'] += p['weight']
        sectors['UNKNOWN'] += residual
        currencies['UNKNOWN'] += residual
        output.append(dict(instrument_id=iid, status='AVAILABLE' if residual < 1e-9 else 'PARTIAL',
            period=latest['period'], source_url=latest['source_url'], snapshot_id=latest['snapshot_id'],
            coverage=coverage, unknown_weight=residual, securities={p['security_id']: p['weight'] for p in positions},
            sectors=dict(sectors), currencies=dict(currencies), factors=factors,
            note='Snapshot exposure only; currency weights exclude unreported hedges and derivatives.'))
    return output


def build_research_context(request):
    exposures = build_exposures(request)
    companies = set()
    for item in request['instruments']:
        if item['asset_type'] == 'stock':
            symbol = item['symbol']
            if symbol.isdigit() and item.get('exchange') in {'TWSE', 'XTAI'}:
                symbol += '.TW'
            companies.add(symbol)
    for exposure in exposures:
        companies.update(exposure['securities'])
    abf = bool(companies & ABF_COMPANIES)
    catalog = indicator_table().to_dict('records') if abf else []
    catalog = [{key: None if isinstance(value, float) and not math.isfinite(value) else value
        for key, value in row.items()} for row in catalog]
    scenarios = {'UPSIDE': [], 'DOWNSIDE': []}
    groups = defaultdict(list)
    for row in request.get('evidence', []):
        if not available(row, request['as_of']):
            continue
        scenario = row.get('scenario')
        if scenario not in scenarios:
            raise ValueError('Evidence scenario must be independently UPSIDE or DOWNSIDE')
        key = (row['instrument_id'], row['relative_to'], row['evidence_group'])
        groups[key].append(row)
    vintages = []
    for key, rows in sorted(groups.items()):
        if len({r['scenario'] for r in rows}) > 1:
            raise ValueError('A shared evidence group cannot establish independent opposing scenarios')
        rows.sort(key=lambda r: max(timestamp(r['published_at']), timestamp(r['acquired_at'])))
        latest = rows[-1]
        latest_time = max(timestamp(latest['published_at']), timestamp(latest['acquired_at']))
        if any(r != latest and max(timestamp(r['published_at']), timestamp(r['acquired_at'])) == latest_time for r in rows):
            raise ValueError('Conflicting equal-time evidence revisions or repeated mappings')
        scenarios[latest['scenario']].append(latest)
        vintages.append(dict(group=list(key), selected=latest, superseded=rows[:-1]))
    return dict(exposures=exposures, companies=sorted(companies), indicators=catalog,
        scenarios=scenarios, evidence_vintages=vintages, sensitivity=None,
        sensitivity_references=[dict(source='core/abf_sensitivity_engine.py',
            research_output='artifacts/abf_revenue_sensitivity.csv', availability='REFERENCE_ONLY',
            target='company_revenue_yoy', status='NO_COEFFICIENT_TRANSFER',
            note='Run the existing ABF sensitivity workflow to inspect dated calibration; no ETF beta is inferred.')]
            if abf else [],
        model_references=['data/industry_driver_models.json', 'data/validated_driver_registry.json'] if abf else [],
        limitations=['Catalog timing is target-relative metadata, not a dated observation.',
            'Existing ABF validation does not establish ETF return predictability.',
            'No exposure weight is converted into an EPS sensitivity or counted as evidence.'])
