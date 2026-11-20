"""Optional official NAV and independent return-index research context.

NAV snapshots and partial index responses retain their actual supplied dates.
These helpers neither infer historical coverage nor assign ETF benchmarks.
"""
from __future__ import annotations

import csv
from datetime import date
import hashlib
import io
import math
import re

from core.multi_asset.adapters import available, timestamp
from core.multi_asset.official_sources import (
    _deduplicate, _not_future, _number, _payload, _provenance, official_date,
)

CONTEXT_PARSER_VERSION = 'taiwan-official-1.1.0'
_NAV_URL = 'https://www.sitca.org.tw/MemberK0000/F/03/nav.csv'
_INDEX_ROOT = 'https://openapi.twse.com.tw/v1/indicesReport/'
_NAV_FIELDS = ['日期', '會員代號', '公司名稱', '基金統編', '基金代號', '基金名稱',
               '基金淨值', '漲跌', '漲跌幅', '類型代號', '幣別', '受益憑證代號']
_SUPPORTED_ETFS = {'0050.TW', '00981A.TW'}
_INDEX_SPECS = {
    'index_tai50': ('TWSE.TAI50.TR', 'Taiwan50TotalReturnIndex', 'TAI50I'),
    'index_taiex': ('TWSE.TAIEX.TR', 'TAIEXTotalReturnIndex', 'MFI94U'),
}


def context_source_requests():
    """The three fixed official context endpoints; each call owns its records."""
    return [dict(source_id='nav', kind='nav', symbol=None, month=None, source_url=_NAV_URL),
            dict(source_id='index:TAI50', kind='index_tai50', symbol=None, month=None,
                 source_url=_INDEX_ROOT + 'TAI50I'),
            dict(source_id='index:TAIEX', kind='index_taiex', symbol=None, month=None,
                 source_url=_INDEX_ROOT + 'MFI94U')]


def reference_instruments():
    """Independent source-defined research indices, with no ETF assignment."""
    return [dict(instrument_id=instrument_id, symbol=symbol, name=name,
                 asset_type='benchmark', exchange='TWSE', quote_currency='TWD',
                 domicile='TW', market='TW', management_style='none', benchmark_id=None,
                 return_basis='total_return_index', corporate_actions_complete=True,
                 distributions_complete=True)
            for instrument_id, symbol, name in [
                ('TWSE.TAI50.TR', 'TAI50.TR', 'TWSE Taiwan 50 Total Return Index'),
                ('TWSE.TAIEX.TR', 'TAIEX.TR', 'TWSE TAIEX Total Return Index')]]


def _csv_payload(raw, metadata):
    # CSV needs the same byte/time checks as JSON without attempting JSON decoding.
    if metadata.get('status') != 200:
        raise ValueError('Official response HTTP status is not successful')
    if hashlib.sha256(raw).hexdigest() != metadata.get('sha256') or len(raw) != metadata.get('bytes'):
        raise ValueError('Official response hash or byte count mismatch')
    timestamp(metadata.get('acquired_at'))
    try:
        records = list(csv.reader(io.StringIO(raw.decode('utf-8-sig'), newline=''), strict=True))
    except (UnicodeDecodeError, csv.Error) as exc:
        raise ValueError('Official NAV response is not valid UTF-8 CSV') from exc
    if not records or records[0] != _NAV_FIELDS:
        raise ValueError('Official NAV response fields changed or are missing')
    if len(records) < 2 or any(len(record) != len(_NAV_FIELDS) for record in records[1:]):
        raise ValueError('Official NAV table row shape changed or is empty')
    return [dict(zip(_NAV_FIELDS, record)) for record in records[1:]]


def parse_nav(raw, metadata, symbols):
    """Select certificate codes exactly; internal fund codes/names are not IDs."""
    records = _csv_payload(raw, metadata)
    selected = set(symbols)
    rows = []
    for record in records:
        symbol = record['受益憑證代號']
        if symbol not in selected:
            continue
        if record['幣別'] != 'TWD':
            raise ValueError('Selected official ETF NAV currency must be TWD')
        if not re.fullmatch(r'[0-9]{8}', record['日期']):
            raise ValueError('Official NAV date must be compact Gregorian YYYYMMDD')
        period = official_date(record['日期'])
        _not_future(period, metadata)
        rows.append(dict(instrument_id=symbol + '.TW', period=period,
                         nav=_number(record['基金淨值'], missing=True), currency=record['幣別'],
                         **_provenance(metadata)))
    return _deduplicate(rows, ['instrument_id', 'period'], ['nav', 'currency'])


def parse_index(raw, metadata, kind):
    """Parse documented TWSE ROC dates and use only the total-return value."""
    if kind not in _INDEX_SPECS:
        raise ValueError('Unsupported official reference index kind')
    instrument_id, value_field, _ = _INDEX_SPECS[kind]
    records = _payload(raw, metadata)
    if not isinstance(records, list):
        raise ValueError('Official index response must be an array')
    fields = {'Date', value_field}
    if kind == 'index_tai50':
        fields.add('Taiwan50Index')
    rows = []
    for record in records:
        if not isinstance(record, dict) or set(record) != fields:
            raise ValueError('Official reference index fields changed')
        text = record['Date']
        if not isinstance(text, str) or not re.fullmatch(r'[0-9]{7}', text):
            raise ValueError('Official index date must be compact ROC YYYMMDD')
        period = date(int(text[:3]) + 1911, int(text[3:5]), int(text[5:])).isoformat()
        _not_future(period, metadata)
        row = dict(instrument_id=instrument_id, period=period,
                   value=_number(record[value_field], missing=True), **_provenance(metadata))
        if kind == 'index_tai50':
            row['price_index'] = _number(record['Taiwan50Index'], missing=True)
        rows.append(row)
    values = ['value', 'price_index'] if kind == 'index_tai50' else ['value']
    return _deduplicate(rows, ['instrument_id', 'period'], values)


def _context(request):
    if not isinstance(request, dict):
        return None
    lineage = request.get('adapter_lineage')
    context = lineage.get('etf_context') if isinstance(lineage, dict) else None
    if (not isinstance(context, dict) or context.get('schema_version') != '1.0.0'
            or not isinstance(context.get('nav_observations'), list)
            or not isinstance(context.get('index_observations'), list)):
        return None
    return context


def _is_period(value):
    try:
        return isinstance(value, str) and date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _records(value):
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _groups(records, identities):
    grouped = {}
    for row in _records(records):
        instrument_id, period = row.get('instrument_id'), row.get('period')
        if isinstance(instrument_id, str) and instrument_id in identities and _is_period(period):
            grouped.setdefault((instrument_id, period), []).append(row)
    return grouped


def _stamp(row):
    try:
        return max(timestamp(row.get('published_at')), timestamp(row.get('acquired_at')))
    except (ValueError, TypeError):
        return None


def _latest(rows, cutoff, fields):
    """Resolve observable vintages; ties with conflicting facts are unusable.

    If none are available, keep a deterministic supplied record for display only.
    Publication and acquisition both constrain availability; their maximum is the
    vintage's effective observation time.
    """
    if not rows:
        return {}, 'MISSING'
    eligible = [row for row in rows if available(row, cutoff)]
    candidates = eligible or rows
    stamps = [_stamp(row) for row in candidates]
    dated = [stamp for stamp in stamps if stamp is not None]
    latest = max(dated) if dated else None
    candidates = [row for row, stamp in zip(candidates, stamps) if stamp == latest]
    # Equivalent facts may carry different source identifiers: stable ordering
    # makes display reproducible without resolving a numeric conflict by order.
    chosen = min(candidates, key=lambda row: (str(row.get('source_url', '')), str(row.get('snapshot_id', ''))))
    if any(any(row.get(field) != chosen.get(field) for field in fields)
           for row in candidates if row is not chosen):
        chosen = dict(chosen, **{field: None for field in fields})
        return chosen, 'CONFLICT'
    return chosen, 'AVAILABLE' if eligible else 'UNAVAILABLE_AS_OF'


def _positive(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def _grid(request):
    value = request.get('period_grid')
    return {period for period in value if _is_period(period)} if isinstance(value, list) else set()


def _valuation_reason(nav, nav_status, price, price_status, currency, period, grid):
    if period not in grid:
        return 'OUTSIDE_PERIOD_GRID'
    if nav_status != 'AVAILABLE':
        return 'NAV_' + nav_status
    if not _positive(nav.get('nav')):
        return 'NAV_MISSING' if nav.get('nav') is None else 'NAV_INVALID'
    if price_status != 'AVAILABLE':
        return 'PRICE_' + price_status
    if not _positive(price.get('value')):
        return 'PRICE_MISSING' if price.get('value') is None else 'PRICE_INVALID'
    if not isinstance(currency, str) or not re.fullmatch('[A-Z]{3}', currency) or not nav.get('currency'):
        return 'CURRENCY_UNKNOWN'
    if nav['currency'] != currency or price.get('currency', currency) != currency:
        return 'CURRENCY_MISMATCH'
    return 'AVAILABLE'


def valuation_rows(request):
    """Exact-date native-currency NAV valuation facts, never nearest-day or FX fills.

    Supported selected funds with no supplied NAV get an explicit missing row.
    Old requests without this optional context retain their previous empty view.
    """
    context = _context(request)
    if context is None:
        return []
    instruments = {row['instrument_id']: row for row in _records(request.get('instruments'))
                   if isinstance(row.get('instrument_id'), str)
                   and row['instrument_id'] in _SUPPORTED_ETFS and row.get('asset_type') == 'etf'}
    navs = _groups(context['nav_observations'], instruments)
    prices = _groups(request.get('observations'), instruments)
    cutoff, grid = request.get('as_of'), _grid(request)
    result = []
    for instrument_id, instrument in sorted(instruments.items()):
        dates = sorted(period for identity, period in navs if identity == instrument_id)
        if not dates:
            result.append(dict(instrument_id=instrument_id, period=None, nav=None, close=None,
                               currency=instrument.get('quote_currency'), premium_discount=None,
                               reason='NAV_MISSING', nav_source_url=None, price_source_url=None))
        for period in dates:
            nav, nav_status = _latest(navs[(instrument_id, period)], cutoff, ['nav', 'currency'])
            price, price_status = _latest(prices.get((instrument_id, period), []), cutoff, ['value', 'currency'])
            reason = _valuation_reason(nav, nav_status, price, price_status,
                                       instrument.get('quote_currency'), period, grid)
            result.append(dict(instrument_id=instrument_id, period=period, nav=nav.get('nav'),
                               close=price.get('value'), currency=nav.get('currency'),
                               premium_discount=price['value'] / nav['nav'] - 1 if reason == 'AVAILABLE' else None,
                               reason=reason, nav_source_url=nav.get('source_url'),
                               price_source_url=price.get('source_url')))
    return result


def reference_rows(request):
    """Report supplied ranges and actual cutoff-usable coverage on the grid."""
    context = _context(request)
    if context is None:
        return []
    identities = {row['instrument_id'] for row in reference_instruments()}
    groups = _groups(context['index_observations'], identities)
    grid, cutoff = _grid(request), request.get('as_of')
    result = []
    for instrument_id in sorted({identity for identity, _ in groups}):
        dates = sorted(period for identity, period in groups if identity == instrument_id)
        usable, any_available, source_urls = 0, False, set()
        for period in dates:
            row, status = _latest(groups[(instrument_id, period)], cutoff, ['value'])
            if isinstance(row.get('source_url'), str):
                source_urls.add(row['source_url'])
            any_available |= status == 'AVAILABLE'
            if period in grid and status == 'AVAILABLE' and _positive(row.get('value')):
                usable += 1
        if usable == len(grid) and grid:
            reason = 'AVAILABLE'
        elif usable:
            reason = 'PARTIAL_COVERAGE'
        else:
            reason = 'NO_USABLE_OBSERVATIONS' if any_available else 'UNAVAILABLE_AS_OF'
        result.append(dict(instrument_id=instrument_id, supplied_start=dates[0], supplied_end=dates[-1],
                           available_count=usable, grid_count=len(grid), reason=reason,
                           source_url=next(iter(source_urls)) if len(source_urls) == 1 else None))
    return result
