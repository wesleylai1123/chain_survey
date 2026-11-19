"""Explicit normalized JSON/CSV adapters. No inferred timestamps or quotes."""
from __future__ import annotations

import csv
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / 'contracts/multi-asset/v1/schema.json'


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('A timezone-aware timestamp is required')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('Timestamp must include a timezone')
    return parsed


def available(row, cutoff):
    try:
        return max(timestamp(row['published_at']), timestamp(row['acquired_at'])) <= timestamp(cutoff)
    except (KeyError, TypeError, ValueError):
        return False


def _finite(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError('Non-finite numbers are not research data')
    if isinstance(value, dict):
        for item in value.values():
            _finite(item)
    elif isinstance(value, list):
        for item in value:
            _finite(item)


def validate_request(request):
    _finite(request)
    schema = json.loads(SCHEMA.read_text(encoding='utf-8'))
    errors = sorted(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(request), key=lambda e: str(e.path))
    if errors:
        raise ValueError(f'Invalid request at {list(errors[0].path)}: {errors[0].message}')
    ids = [item['instrument_id'] for item in request['instruments']]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate instrument identity')
    grid = request['period_grid']
    if grid != sorted(set(grid)):
        raise ValueError('period_grid must be sorted and unique')
    for row in request['observations']:
        if row['instrument_id'] not in ids or row['period'] not in grid:
            raise ValueError('Observation references an unknown instrument or grid date')
    for item in request['instruments']:
        if item.get('benchmark_id') and item['benchmark_id'] not in ids:
            raise ValueError('Unknown benchmark identity')
        if item['asset_type'] == 'fx':
            if not item.get('fx_base_currency') or item.get('fx_quote_currency') != item['quote_currency']:
                raise ValueError('FX instruments require explicit base/quote currencies')
    for collection in ('distributions', 'holdings', 'evidence'):
        for row in request.get(collection, []):
            if row['instrument_id'] not in ids:
                raise ValueError(f'{collection} references an unknown instrument')
    return request


def _read_json(path):
    raw = Path(path).read_bytes()
    try:
        payload = json.loads(raw.decode('utf-8-sig'), parse_constant=lambda x: (_ for _ in ()).throw(ValueError(f'Invalid number: {x}')))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f'Cannot read JSON: {exc}') from exc
    return payload, {'path': str(Path(path).resolve()), 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def load_request(path):
    request, lineage = _read_json(path)
    return validate_request(request), lineage


def load_csv_bundle(path):
    """Manifest contains request metadata and relative CSVs keyed by collection.

    CSV publication/acquisition blanks become null, never the file modification time.
    The source CSV hashes are retained in addition to the manifest hash.
    """
    manifest, lineage = _read_json(path)
    request = manifest['request']
    lineage['files'] = {}
    parent = Path(path).resolve().parent
    for collection, relative in manifest['files'].items():
        if collection not in {'observations', 'distributions', 'fx_rates'}:
            raise ValueError(f'Unsupported CSV collection: {collection}')
        file = (parent / relative).resolve()
        if not file.is_relative_to(parent):
            raise ValueError('CSV files must be inside the bundle directory')
        raw = file.read_bytes()
        rows = list(csv.DictReader(raw.decode('utf-8-sig').splitlines()))
        for row in rows:
            for key, value in list(row.items()):
                if value == '':
                    row[key] = None
                elif key in {'value', 'rate', 'amount_per_unit'}:
                    row[key] = float(value)
        request[collection] = rows
        lineage['files'][collection] = {'path': relative, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
    request['adapter_lineage'] = lineage
    return validate_request(request), lineage
