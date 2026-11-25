"""Bounded official data capture and verified offline replay, owned by the product."""
from __future__ import annotations

from datetime import date, datetime, timezone
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import time
from urllib.parse import urlencode
import uuid
from zoneinfo import ZoneInfo

import requests

from core.multi_asset.adapters import timestamp, validate_request
from core.multi_asset.official_context import (CONTEXT_PARSER_VERSION, context_source_requests,
    parse_index, parse_nav, reference_instruments)
from core.multi_asset.official_sources import (AVAILABILITY_METHOD, PARSER_VERSION,
    parse_prices, parse_distributions, parse_splits, parse_fx)

UNIVERSE = {
    '0050': dict(name='元大台灣50', management_style='passive',
        metadata_source='https://www.twse.com.tw/zh/ETFortune/etfInfo/0050'),
    '00981A': dict(name='主動統一台股增長', management_style='active',
        metadata_source='https://www.twse.com.tw/zh/ETFortune/etfInfo/00981A'),
}
MAX_MONTHS = 24
MAX_RESPONSE_BYTES = 2_000_000
_LEGACY_CAPTURE = ('1.0.0', PARSER_VERSION)
_CONTEXT_CAPTURE = ('1.1.0', CONTEXT_PARSER_VERSION)
_INDEX_KINDS = {'index_tai50', 'index_taiex'}


def _bytes(payload):
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False)+'\n').encode('utf-8')


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def source_requests(symbols, start, end, *, include_etf_context=False):
    if not isinstance(include_etf_context, bool):
        raise ValueError('include_etf_context must be a boolean')
    if not isinstance(symbols, (tuple, list)) or not symbols or len(symbols) != len(set(symbols)) or any(s not in UNIVERSE for s in symbols):
        raise ValueError('Choose supported unique symbols: 0050 and/or 00981A')
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if first > last or start != first.isoformat() or end != last.isoformat():
        raise ValueError('Start/end must be ordered ISO dates')
    count = (last.year-first.year)*12 + last.month-first.month+1
    if not 1 <= count <= MAX_MONTHS:
        raise ValueError(f'Official collection is limited to {MAX_MONTHS} calendar months')
    result = []
    for symbol in sorted(symbols):
        for offset in range(count):
            month_index = first.year*12+first.month-1+offset
            month = f'{month_index//12:04d}{month_index%12+1:02d}01'
            result.append(dict(source_id=f'price:{symbol}:{month}', kind='price', symbol=symbol, month=month,
                source_url='https://www.twse.com.tw/exchangeReport/STOCK_DAY?'+urlencode(dict(response='json', date=month, stockNo=symbol))))
        result.append(dict(source_id=f'dividend:{symbol}', kind='dividend', symbol=symbol, month=None,
            source_url='https://www.twse.com.tw/rwd/zh/ETF/etfDiv?'+urlencode(dict(response='json', stkNo=symbol,
                startDate=f'{first.year-1:04d}0101', endDate=end.replace('-', '')))))
    result.append(dict(source_id='splits', kind='splits', symbol=None, month=None,
        source_url='https://www.twse.com.tw/rwd/zh/split/TWTCAU?'+urlencode(dict(response='json', startDate=start.replace('-', ''), endDate=end.replace('-', '')))))
    result.append(dict(source_id='fx', kind='fx', symbol=None, month=None,
        source_url='https://cpx.cbc.gov.tw/api/OpenData/FTDOpenData_Day'))
    if include_etf_context:
        result.extend(context_source_requests())
    return result


def _fetch_source(spec, audit=None):
    """Verified HTTPS, bounded body/attempts, no redirects or silent stale cache."""
    for attempt in range(3):
        chunks, size, status, headers = [], 0, None, {}
        try:
            with requests.get(spec['source_url'], timeout=(5, 25), stream=True, allow_redirects=False,
                    headers={'User-Agent': 'Mozilla/5.0 chain_survey-research/1.0'}, verify=True) as response:
                status = response.status_code
                headers = {key: response.headers[key] for key in ('Content-Type', 'Date', 'Last-Modified', 'ETag') if key in response.headers}
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    chunks.append(chunk)
                    if size > MAX_RESPONSE_BYTES:
                        if audit:
                            audit(b''.join(chunks)[:MAX_RESPONSE_BYTES], status, datetime.now(timezone.utc).isoformat(),
                                headers, attempt+1, False, 'response_size_limit')
                        raise ValueError('Official source response exceeds the size limit')
                raw = b''.join(chunks)
                acquired_at = datetime.now(timezone.utc).isoformat()
                if audit:
                    audit(raw, status, acquired_at, headers, attempt+1, True, None)
                if status != 200:
                    if status in {429, 500, 502, 503, 504} and attempt < 2:
                        time.sleep(2**attempt)
                        continue
                    raise ValueError(f'Official source HTTP {status}: {spec["source_id"]}')
                return raw, dict(status=200, acquired_at=acquired_at)
        except requests.RequestException as exc:
            if audit:
                audit(b''.join(chunks)[:MAX_RESPONSE_BYTES], status, datetime.now(timezone.utc).isoformat(),
                    headers, attempt+1, False, type(exc).__name__)
            if attempt == 2:
                raise ValueError(f'Official source transport failed: {spec["source_id"]}: {type(exc).__name__}') from exc
            time.sleep(2**attempt)
    raise ValueError('Official source attempts exhausted')


def _parse(raw, entry, manifest):
    if manifest['parser_version'] == CONTEXT_PARSER_VERSION:
        if entry['kind'] == 'nav':
            return parse_nav(raw, entry, manifest['symbols'])
        if entry['kind'] in _INDEX_KINDS:
            return parse_index(raw, entry, entry['kind'])
    if entry['kind'] == 'price':
        return parse_prices(raw, entry, entry['symbol'], entry['month'])
    if entry['kind'] == 'dividend':
        return parse_distributions(raw, entry, entry['symbol'])
    return {'splits': parse_splits, 'fx': parse_fx}[entry['kind']](raw, entry)


def _atomic_write(path, raw):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _inside(parent, relative):
    target = (parent/relative).resolve()
    if not target.is_relative_to(parent.resolve()) or target == parent.resolve():
        raise ValueError('Capture path escapes its directory')
    return target


def _build_request(manifest, raw_sources):
    start, end = manifest['start'], manifest['end']
    prices, distributions, splits, rates = [], [], [], []
    nav_observations, index_observations = [], []
    for entry, raw in raw_sources:
        rows = _parse(raw, entry, manifest)
        if entry['kind'] == 'price':
            prices.extend(r for r in rows if start <= r['period'] <= end)
        elif entry['kind'] == 'dividend':
            distributions.extend(r for r in rows if (start <= r['ex_date'] <= end)
                or (r['pay_date'] is not None and start <= r['pay_date'] <= end)
                or (r['pay_date'] is None and r['ex_date'] <= end))
        elif entry['kind'] == 'splits':
            splits.extend(r for r in rows if start <= r['period'] <= end and r['instrument_id'][:-3] in manifest['symbols'])
        elif entry['kind'] == 'fx':
            rates.extend(r for r in rows if start <= r['period'] <= end)
        elif entry['kind'] == 'nav':
            nav_observations.extend(rows)
        elif entry['kind'] in _INDEX_KINDS:
            index_observations.extend(rows)
    grid = sorted({r['period'] for r in prices})
    if len(grid) < 2:
        raise ValueError('At least two official trading dates are required')
    for symbol in manifest['symbols']:
        if not any(r['instrument_id'] == symbol+'.TW' for r in prices):
            raise ValueError(f'No price data in requested window for {symbol}')
    if not rates:
        raise ValueError('No official USD/TWD observations in requested window')
    instruments = []
    for symbol in sorted(manifest['symbols']):
        metadata = manifest['instrument_metadata'][symbol]
        instruments.append(dict(instrument_id=symbol+'.TW', symbol=symbol, name=metadata['name'],
            asset_type='etf', exchange='TWSE', quote_currency='TWD', domicile='TW', market='TW',
            management_style=metadata['management_style'], benchmark_id=None, return_basis='unadjusted_price',
            corporate_actions_complete=False, distributions_complete=False))
    instruments.append(dict(instrument_id='USD-TWD', symbol='USD/TWD', name='USD/TWD interbank closing spot',
        asset_type='fx', exchange=None, quote_currency='TWD', domicile=None, market='TW',
        management_style='none', benchmark_id=None, return_basis='split_adjusted_price',
        fx_base_currency='USD', fx_quote_currency='TWD', corporate_actions_complete=True, distributions_complete=True))
    prices.extend(dict(instrument_id='USD-TWD', period=r['period'], value=r['rate'],
        **{k: r[k] for k in ('published_at', 'acquired_at', 'source_url', 'snapshot_id')}) for r in rates if r['period'] in grid)
    lineage = dict(kind='TAIWAN_OFFICIAL_AS_ACQUIRED', capture_id=manifest['capture_id'],
        captured_at=manifest['captured_at'], parser_version=manifest['parser_version'], availability_method=AVAILABILITY_METHOD,
        price_basis='unadjusted', splits=splits, distribution_records=distributions,
        instrument_metadata=manifest['instrument_metadata'],
        sources=manifest['sources'], nominal_initial_capital='1 reporting-currency unit; not user account capital',
        limitations=['Historical endpoint publication times are unknown; availability is conservatively the acquisition time.',
            'Unadjusted ETF prices do not establish total return or investment cash accounting.',
            'Distribution policy prose does not establish the actual income/ROC classification.',
            'Split reference prices are rounded; exact split ratios are not inferred.',
            'Supplied trading-date union is not an independently verified exchange calendar.',
            'CBC interbank close is a research reference, not an executable broker FX quote.',
            'Benchmarks, fees, underlying holdings and personalized taxes are not inferred.'])
    if manifest['parser_version'] == CONTEXT_PARSER_VERSION:
        instruments.extend(manifest['reference_instruments'])
        grid_dates = set(grid)
        prices.extend({key: value for key, value in row.items() if key != 'price_index'}
            for row in index_observations if row['period'] in grid_dates)
        lineage['etf_context'] = dict(schema_version='1.0.0', reference_role='independent_research_only',
            nav_observations=nav_observations, index_observations=index_observations)
    request = dict(contract='MultiAssetResearchV1', schema_version='1.1.0', as_of=manifest['captured_at'],
        base_currency=manifest['base_currency'], objective='accumulation', periods_per_year=252, period_grid=grid,
        risk_free_rate=None, rolling_windows=[21, 63, 252], instruments=instruments, observations=prices,
        distributions=[{k: v for k, v in r.items() if k != 'record_date'} for r in distributions],
        fx_rates=rates, regimes=[], holdings=[], evidence=[], adapter_lineage=lineage,
        cash_flow_assumptions=dict(initial_capital=1.0, withholding_tax_rate=None, distribution_fee_rate=None,
            fx_fee_rate=None, buy_fee_rate=None, reinvest_fee_rate=None))
    return validate_request(request)


def capture_official_data(symbols, start, end, output_dir, *, base_currency='TWD', fetcher=None,
                         clock=None, pace_seconds=2.0, include_etf_context=False):
    specs = source_requests(symbols, start, end, include_etf_context=include_etf_context)
    schema_version, parser_version = _CONTEXT_CAPTURE if include_etf_context else _LEGACY_CAPTURE
    clock = clock or (lambda: datetime.now(timezone.utc).isoformat())
    now = timestamp(clock())
    if end > now.astimezone(ZoneInfo('Asia/Taipei')).date().isoformat():
        raise ValueError('Capture window cannot include future dates')
    if base_currency not in {'TWD', 'USD'}:
        raise ValueError('Official capture supports reporting in TWD or USD')
    if not isinstance(pace_seconds, (float, int)) or not math.isfinite(pace_seconds) or not 0 <= pace_seconds <= 10:
        raise ValueError('Invalid source request pacing')
    root = Path(output_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    run = root/'runs'/uuid.uuid4().hex
    (run/'raw').mkdir(parents=True)
    manifest = dict(contract='TaiwanOfficialCaptureV1', schema_version=schema_version, capture_id=run.name,
        start=start, end=end, symbols=sorted(symbols), base_currency=base_currency,
        instrument_metadata={symbol: copy.deepcopy(UNIVERSE[symbol]) for symbol in sorted(symbols)},
        captured_at=None, parser_version=parser_version, sources=[], attempts=[])
    if include_etf_context:
        manifest['reference_instruments'] = reference_instruments()
    raw_sources = []
    try:
        for index, spec in enumerate(specs):
            def record_attempt(body, status, acquired, headers, attempt, complete, error):
                relative = 'raw/'+_digest(body)+'.bin'
                target = run/relative
                if target.exists():
                    if target.read_bytes() != body:
                        raise ValueError('Attempt evidence conflicts with immutable source bytes')
                else:
                    with target.open('xb') as stream:
                        stream.write(body)
                manifest['attempts'].append(dict(spec, status=status, acquired_at=acquired,
                    sha256=_digest(body), bytes=len(body), path=relative, attempt=attempt,
                    body_complete=complete, error=error, response_headers=headers))
            raw, response = fetcher(spec) if fetcher else _fetch_source(spec, record_attempt)
            if fetcher:
                record_attempt(raw, response['status'], response['acquired_at'], {}, 1, True, None)
            if not isinstance(raw, bytes) or len(raw) > MAX_RESPONSE_BYTES:
                raise ValueError('Invalid or oversized source response bytes')
            acquired_at = response['acquired_at']
            timestamp(acquired_at)
            entry = dict(spec, status=response['status'], acquired_at=acquired_at,
                sha256=_digest(raw), bytes=len(raw), path='raw/'+_digest(raw)+'.bin')
            target = run/entry['path']
            if target.exists():
                if target.read_bytes() != raw:
                    raise ValueError('Immutable source path has conflicting bytes')
            else:
                with target.open('xb') as stream:
                    stream.write(raw)
            manifest['sources'].append(entry)
            _parse(raw, entry, manifest)
            raw_sources.append((entry, raw))
            if pace_seconds and index+1 < len(specs):
                time.sleep(pace_seconds)
        manifest['captured_at'] = clock()
        if any(timestamp(r['acquired_at']) > timestamp(manifest['captured_at']) for r in manifest['sources']):
            raise ValueError('Capture cutoff precedes a source acquisition')
        request = _build_request(manifest, raw_sources)
        rendered = _bytes(request)
        _atomic_write(run/'request.json', rendered)
        manifest.update(request_path='request.json', request_sha256=_digest(rendered))
        raw_manifest = _bytes(manifest)
        _atomic_write(run/'manifest.json', raw_manifest)
        _atomic_write(root/'latest-good.json', _bytes(dict(manifest_path=f'runs/{run.name}/manifest.json',
            manifest_sha256=_digest(raw_manifest), captured_at=manifest['captured_at'])))
        return run/'manifest.json'
    except Exception as exc:
        _atomic_write(run/'failed.json', _bytes(dict(manifest, failure=str(exc), status='FAILED')))
        raise


def _validate_reference_instruments(frozen):
    expected = reference_instruments()
    if not isinstance(frozen, list) or len(frozen) != len(expected):
        raise ValueError('Capture is missing required frozen reference instruments')
    for definition, canonical in zip(frozen, expected):
        if not isinstance(definition, dict) or definition.keys() != canonical.keys():
            raise ValueError('Capture reference instrument shape is invalid')
        name = definition['name']
        if not isinstance(name, str) or not name.strip():
            raise ValueError('Capture reference instrument name is invalid')
        # Display names are frozen. Source-defined identity and return semantics are versioned.
        if any(type(definition[key]) is not type(value) or definition[key] != value
               for key, value in canonical.items() if key != 'name'):
            raise ValueError('Capture reference instrument identity or semantics changed')


def load_capture(path):
    manifest_path = Path(path).resolve()
    raw_manifest = manifest_path.read_bytes()
    manifest = json.loads(raw_manifest.decode('utf-8'))
    versions = (manifest.get('schema_version'), manifest.get('parser_version'))
    if manifest.get('contract') != 'TaiwanOfficialCaptureV1' or versions not in (_LEGACY_CAPTURE, _CONTEXT_CAPTURE):
        raise ValueError('Unsupported official capture or parser version')
    include_etf_context = versions == _CONTEXT_CAPTURE
    expected = source_requests(manifest['symbols'], manifest['start'], manifest['end'],
        include_etf_context=include_etf_context)
    frozen_metadata = manifest.get('instrument_metadata')
    if not isinstance(frozen_metadata, dict) or set(frozen_metadata) != set(manifest['symbols']):
        raise ValueError('Capture is missing frozen instrument metadata')
    for symbol, metadata in frozen_metadata.items():
        if not isinstance(metadata, dict) or not isinstance(metadata.get('name'), str) or not metadata['name'] or metadata.get('management_style') not in {'active', 'passive'} or metadata.get('metadata_source') != f'https://www.twse.com.tw/zh/ETFortune/etfInfo/{symbol}':
            raise ValueError('Capture instrument metadata is invalid')
    if include_etf_context:
        _validate_reference_instruments(manifest.get('reference_instruments'))
    entries = manifest.get('sources')
    if not isinstance(entries, list) or len(expected) != len(entries):
        raise ValueError('Capture is missing required source responses')
    cutoff = timestamp(manifest['captured_at'])
    if manifest['end'] > cutoff.astimezone(ZoneInfo('Asia/Taipei')).date().isoformat():
        raise ValueError('Capture window is after its cutoff')
    raw_sources = []
    for spec, entry in zip(expected, entries):
        if any(entry.get(k) != v for k, v in spec.items()):
            raise ValueError('Capture source identity, order or request URL changed')
        if timestamp(entry['acquired_at']) > cutoff:
            raise ValueError('Capture source is unavailable at cutoff')
        raw_path = _inside(manifest_path.parent, entry['path'])
        if raw_path.stat().st_size > MAX_RESPONSE_BYTES:
            raise ValueError('Frozen source exceeds the response size limit')
        raw = raw_path.read_bytes()
        raw_sources.append((entry, raw))
    for attempt in manifest.get('attempts', []):
        if timestamp(attempt['acquired_at']) > cutoff:
            raise ValueError('Capture attempt is unavailable at cutoff')
        attempt_path = _inside(manifest_path.parent, attempt['path'])
        if attempt_path.stat().st_size > MAX_RESPONSE_BYTES:
            raise ValueError('Attempt evidence exceeds its byte limit')
        body = attempt_path.read_bytes()
        if _digest(body) != attempt.get('sha256') or len(body) != attempt.get('bytes'):
            raise ValueError('Attempt evidence hash or byte count mismatch')
    request = _build_request(manifest, raw_sources)
    saved = _inside(manifest_path.parent, manifest.get('request_path', '')).read_bytes()
    if _digest(saved) != manifest.get('request_sha256') or saved != _bytes(request):
        raise ValueError('Capture request hash or deterministic replay mismatch')
    return request, dict(path=str(manifest_path), sha256=_digest(raw_manifest), bytes=len(raw_manifest),
        source_count=len(entries), notice='REAL OFFICIAL AS-ACQUIRED SNAPSHOT; UNADJUSTED ETF PRICES')
