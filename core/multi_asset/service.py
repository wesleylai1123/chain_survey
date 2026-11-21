"""Subprocess JSON boundary prevents colliding core packages across repositories."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from jsonschema import Draft202012Validator, FormatChecker

from core.multi_asset.adapters import _finite, validate_request, schema_path


def validate_result(result, request, input_sha256):
    _finite(result)
    schema = json.loads(schema_path('multi-asset-result', request.get('schema_version')).read_text(encoding='utf-8'))
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(result))
    if errors:
        raise ValueError(f'Invalid service response at {list(errors[0].path)}: {errors[0].message}')
    expected = dict(contract='MultiAssetResultV1', schema_version=request['schema_version'],
        as_of=request['as_of'], base_currency=request['base_currency'],
        objective=request['objective'], input_sha256=input_sha256)
    for key, value in expected.items():
        if result.get(key) != value:
            raise ValueError(f'Service response does not match request: {key}')
    rows = result.get('instruments')
    if not isinstance(rows, list) or len(rows) != len(request['instruments']):
        raise ValueError('Service response is missing instruments')
    expected_ids = {i['instrument_id'] for i in request['instruments']}
    if {i.get('instrument_id') for i in rows} != expected_ids:
        raise ValueError('Service response has unexpected instrument identities')
    identities = {i['instrument_id']: i for i in request['instruments']}
    for row in rows:
        for key, value in identities[row['instrument_id']].items():
            if row.get(key) != value:
                raise ValueError(f'Service response changed instrument identity: {key}')
        for key, kind in [('metrics', dict), ('unavailable', dict), ('returns', list), ('rolling_returns', list), ('cash_flows', list), ('quality', list)]:
            if not isinstance(row.get(key), kind):
                raise ValueError(f'Invalid service field {key}')
    if not isinstance(result.get('correlations'), list):
        raise ValueError('Invalid correlations')
    return result


def run_research(request, engine_repo=None, *, timeout=120):
    validate_request(request)
    configured = engine_repo or os.environ.get('INVEST_BACKTEST_REPO')
    repo = Path(configured).expanduser().resolve() if configured else Path(__file__).resolve().parents[3] / 'invest_backtest'
    script = repo / 'scripts/run_multi_asset_research.py'
    if not script.is_file():
        raise ValueError('Select the invest_backtest checkout containing the multi-asset service.')
    raw = (json.dumps(request, ensure_ascii=False, sort_keys=True, allow_nan=False) + '\n').encode('utf-8')
    work = Path(__file__).resolve().parents[2] / 'artifacts/multi_asset_jobs'
    work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='job-', dir=work) as directory:
        source, target = Path(directory)/'request.json', Path(directory)/'result.json'
        source.write_bytes(raw)
        completed = subprocess.run([sys.executable, str(script), '--input', str(source), '--output', str(target)],
            cwd=repo, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if completed.returncode:
            raise ValueError(f'Research service failed: {(completed.stderr or completed.stdout)[-2000:]}')
        try:
            result = json.loads(target.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError('Research service did not produce a valid response') from exc
    return validate_result(result, request, hashlib.sha256(raw).hexdigest())
