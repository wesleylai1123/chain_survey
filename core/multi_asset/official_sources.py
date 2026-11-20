"""Strict parsers for official TWSE/CBC responses, without inferred adjustments."""
from __future__ import annotations

from datetime import date
import hashlib
import json
import math
import re
from zoneinfo import ZoneInfo

from core.multi_asset.adapters import timestamp

PARSER_VERSION = 'taiwan-official-1.0.1'
AVAILABILITY_METHOD = 'OBSERVED_AT_ACQUISITION_NOT_ORIGINAL_PUBLICATION'


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate JSON key: {key}')
        result[key] = value
    return result


def _payload(raw, metadata):
    if metadata.get('status') != 200:
        raise ValueError('Official response HTTP status is not successful')
    if hashlib.sha256(raw).hexdigest() != metadata.get('sha256') or len(raw) != metadata.get('bytes'):
        raise ValueError('Official response hash or byte count mismatch')
    timestamp(metadata.get('acquired_at'))
    try:
        return json.loads(raw.decode('utf-8-sig'), object_pairs_hook=_unique_object,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f'Nonfinite JSON number: {value}')))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError('Official response is not valid UTF-8 JSON') from exc


def _provenance(metadata):
    return dict(published_at=metadata['acquired_at'], acquired_at=metadata['acquired_at'],
        source_url=metadata['source_url'], snapshot_id=metadata['sha256'])


def official_date(value):
    """Only documented Gregorian/ROC date forms; invalid calendar dates fail."""
    text = str(value).strip()
    if re.fullmatch(r'\d{8}', text):
        return date(int(text[:4]), int(text[4:6]), int(text[6:])).isoformat()
    match = re.fullmatch(r'(\d{3,4})(?:/|-|年)(\d{1,2})(?:/|-|月)(\d{1,2})日?', text)
    if not match:
        raise ValueError(f'Unrecognized official date: {text}')
    year, month, day = map(int, match.groups())
    if len(match.group(1)) == 3:
        year += 1911
    return date(year, month, day).isoformat()


def _number(value, *, zero=False, missing=False):
    if missing and (value is None or str(value).strip() in {'', '--', '---'}):
        return None
    if isinstance(value, bool):
        raise ValueError('Boolean is not a market number')
    try:
        number = float(str(value).replace(',', '').strip())
    except (ValueError, TypeError) as exc:
        raise ValueError(f'Invalid official numeric value: {value}') from exc
    if not math.isfinite(number) or number < 0 or (not zero and number == 0):
        raise ValueError(f'Nonpositive or nonfinite official numeric value: {value}')
    return number


def _table(payload, required_fields):
    if not isinstance(payload, dict) or payload.get('stat', payload.get('status')) not in {'OK', 'ok'}:
        raise ValueError('Official response does not report successful data')
    fields, data = payload.get('fields'), payload.get('data')
    if not isinstance(fields, list) or len(fields) != len(set(fields)) or not set(required_fields) <= set(fields):
        raise ValueError('Official response fields changed or are missing')
    if not isinstance(data, list) or any(not isinstance(row, list) or len(row) != len(fields) for row in data):
        raise ValueError('Official table row shape changed')
    return [dict(zip(fields, row)) for row in data]


def _deduplicate(rows, keys, values):
    result = {}
    for row in rows:
        key = tuple(row[k] for k in keys)
        if key in result and any(result[key][field] != row[field] for field in values):
            raise ValueError(f'Conflicting duplicate official row: {key}')
        result[key] = row
    return [result[key] for key in sorted(result, key=lambda key: tuple('' if v is None else str(v) for v in key))]


def _not_future(period, metadata):
    if period > timestamp(metadata['acquired_at']).astimezone(ZoneInfo('Asia/Taipei')).date().isoformat():
        raise ValueError('Official price/FX date is later than acquisition')


def parse_prices(raw, metadata, symbol, month):
    payload = _payload(raw, metadata)
    if payload.get('date') != month or not re.search(rf'(?<![A-Z0-9]){re.escape(symbol)}(?![A-Z0-9])', payload.get('title', '')):
        raise ValueError('Official price security or month mismatch')
    records = _table(payload, ['日期', '收盤價'])
    if not records:
        raise ValueError('No official trading observations in requested month')
    rows = []
    for record in records:
        period = official_date(record['日期'])
        if period.replace('-', '')[:6] != month[:6]:
            raise ValueError('Official price row is outside requested month')
        _not_future(period, metadata)
        rows.append(dict(instrument_id=symbol+'.TW', period=period,
            value=_number(record['收盤價'], missing=True), **_provenance(metadata)))
    return _deduplicate(rows, ['instrument_id', 'period'], ['value'])


def parse_distributions(raw, metadata, symbol):
    records = _table(_payload(raw, metadata), ['證券代號', '除息交易日', '收益分配基準日', '收益分配發放日', '收益分配金額 (每1受益權益單位)'])
    rows = []
    for record in records:
        if record['證券代號'] != symbol:
            raise ValueError('Official distribution security mismatch')
        ex = official_date(record['除息交易日'])
        record_day = official_date(record['收益分配基準日']) if record['收益分配基準日'] not in (None, '', '--') else None
        pay = official_date(record['收益分配發放日']) if record['收益分配發放日'] not in (None, '', '--') else None
        if pay is not None and pay < ex:
            raise ValueError('Official distribution pay date precedes ex date')
        if record_day is not None and (record_day < ex or (pay is not None and record_day > pay)):
            raise ValueError('Official distribution record date is outside ex/pay dates')
        rows.append(dict(instrument_id=symbol+'.TW', ex_date=ex, pay_date=pay, record_date=record_day,
            amount_per_unit=_number(record['收益分配金額 (每1受益權益單位)'], zero=True),
            currency='TWD', distribution_type='unknown', **_provenance(metadata)))
    return _deduplicate(rows, ['instrument_id', 'ex_date', 'pay_date', 'distribution_type'], ['amount_per_unit', 'record_date'])


def parse_splits(raw, metadata):
    records = _table(_payload(raw, metadata), ['恢復買賣日期', 'ETF代號', '分割(反分割)', '停止買賣前收盤價格', '恢復買賣參考價'])
    rows = []
    for record in records:
        period = official_date(record['恢復買賣日期'])
        _not_future(period, metadata)
        rows.append(dict(instrument_id=record['ETF代號']+'.TW', period=period,
            kind=record['分割(反分割)'], reference_before=_number(record['停止買賣前收盤價格']),
            reference_after=_number(record['恢復買賣參考價']), ratio=None, **_provenance(metadata)))
    return _deduplicate(rows, ['instrument_id', 'period'], ['reference_before', 'reference_after', 'kind'])


def parse_fx(raw, metadata):
    records = _payload(raw, metadata)
    if not isinstance(records, list) or not records:
        raise ValueError('Official CBC response has no rate rows')
    rows = []
    for record in records:
        if not isinstance(record, dict) or set(record) != {'日期', 'NTD_USD'}:
            raise ValueError('Official CBC fields changed')
        period = official_date(record['日期'])
        _not_future(period, metadata)
        rows.append(dict(period=period, base_currency='USD', quote_currency='TWD',
            rate=_number(record['NTD_USD'], missing=True), **_provenance(metadata)))
    return _deduplicate(rows, ['period', 'base_currency', 'quote_currency'], ['rate'])
