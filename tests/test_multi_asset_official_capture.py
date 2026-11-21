import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs

from core.multi_asset.official_capture import capture_official_data, load_capture, source_requests, UNIVERSE
from test_multi_asset_official_sources import source_fixture

STAMP = '2026-11-20T01:00:00+00:00'


def frozen_fetch(spec):
    if spec['kind'] == 'price':
        name = 'price-'+spec['symbol']
    elif spec['kind'] == 'dividend':
        name = 'div-'+spec['symbol']
    else:
        name = 'cbc-fx' if spec['kind'] == 'fx' else 'splits'
    raw, _ = source_fixture(name)
    return raw, {'status': 200, 'acquired_at': STAMP}


class OfficialCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def capture(self, fetcher=frozen_fetch):
        return capture_official_data(['0050', '00981A'], '2026-09-01', '2026-09-30',
            self.directory, fetcher=fetcher, clock=lambda: STAMP, pace_seconds=0)

    def test_capture_raw_request_and_offline_replay_preserve_times(self):
        manifest = self.capture()
        with patch('requests.get', side_effect=AssertionError('Replay must not fetch')):
            request, lineage = load_capture(manifest)
        self.assertEqual(request['schema_version'], '1.1.0')
        self.assertEqual(len(request['instruments']), 3)
        self.assertEqual(request['base_currency'], 'TWD')
        self.assertEqual(request['as_of'], STAMP)
        self.assertEqual(request['period_grid'][0], '2026-09-01')
        self.assertEqual(request['period_grid'][-1], '2026-09-30')
        self.assertEqual(request['instruments'][0]['return_basis'], 'unadjusted_price')
        self.assertFalse(request['instruments'][0]['corporate_actions_complete'])
        self.assertIsNone(request['cash_flow_assumptions']['withholding_tax_rate'])
        self.assertIsNone(request['cash_flow_assumptions']['buy_fee_rate'])
        self.assertEqual(request['observations'][0]['acquired_at'], STAMP)
        self.assertIn('OBSERVED_AT_ACQUISITION', request['adapter_lineage']['availability_method'])
        self.assertEqual(load_capture(manifest)[0], request)
        pointer = json.loads((self.directory/'latest-good.json').read_text(encoding='utf-8'))
        self.assertEqual(pointer['manifest_sha256'], hashlib.sha256(manifest.read_bytes()).hexdigest())
        self.assertEqual(lineage['sha256'], pointer['manifest_sha256'])

    def test_failure_retains_latest_good(self):
        self.capture()
        before = (self.directory/'latest-good.json').read_bytes()
        def fail(spec):
            raise ValueError('HTTP source failure')
        with self.assertRaises(ValueError):
            self.capture(fail)
        self.assertEqual((self.directory/'latest-good.json').read_bytes(), before)
        self.assertTrue(list(self.directory.glob('runs/*/failed.json')))

    def test_raw_tampering_and_path_escape_rejected(self):
        manifest = self.capture()
        payload = json.loads(manifest.read_text(encoding='utf-8'))
        raw = manifest.parent/payload['sources'][0]['path']
        raw.write_bytes(raw.read_bytes()+b' ')
        with self.assertRaises(ValueError):
            load_capture(manifest)
        payload['sources'][0]['path'] = '../../outside.json'
        manifest.write_text(json.dumps(payload), encoding='utf-8')
        with self.assertRaises(ValueError):
            load_capture(manifest)

    def test_request_tampering_and_missing_sources_rejected(self):
        manifest = self.capture()
        payload = json.loads(manifest.read_text(encoding='utf-8'))
        request_path = manifest.parent/'request.json'
        request_path.write_bytes(request_path.read_bytes()+b' ')
        with self.assertRaises(ValueError):
            load_capture(manifest)
        payload['sources'].pop()
        manifest.write_text(json.dumps(payload), encoding='utf-8')
        with self.assertRaises(ValueError):
            load_capture(manifest)

    def test_month_budget_and_supported_symbols_are_enforced_before_fetch(self):
        for symbols, start, end in [(['UNKNOWN'], '2026-09-01', '2026-09-30'),
                                    (['0050'], '2020-01-01', '2026-09-30'),
                                    (['0050'], '2026-10-01', '2026-09-30')]:
            with self.assertRaises(ValueError):
                source_requests(symbols, start, end)

    def test_future_capture_window_is_rejected(self):
        with self.assertRaises(ValueError):
            capture_official_data(['0050'], '2027-01-01', '2027-01-31', self.directory,
                fetcher=frozen_fetch, clock=lambda: STAMP, pace_seconds=0)

    def test_offline_metadata_uses_frozen_capture_not_new_registry_values(self):
        manifest = self.capture()
        original = load_capture(manifest)[0]
        with patch.dict(UNIVERSE['0050'], {'name': 'DIFFERENT FUTURE NAME'}):
            replayed = load_capture(manifest)[0]
        self.assertEqual(replayed, original)

    def test_http_retries_retain_failed_response_evidence(self):
        calls = []
        class Response:
            headers = {'Content-Type': 'application/json'}
            def __init__(self, status, raw):
                self.status_code, self.raw = status, raw
            def __enter__(self): return self
            def __exit__(self, *_): return None
            def iter_content(self, _): yield self.raw
        def get(url, **kwargs):
            calls.append(url)
            if len(calls) == 1:
                return Response(429, b'{"message":"rate limited"}')
            query = parse_qs(urlparse(url).query)
            if 'STOCK_DAY' in url:
                name = 'price-'+query['stockNo'][0]
            elif 'etfDiv' in url:
                name = 'div-'+query['stkNo'][0]
            else:
                name = 'cbc-fx' if 'cbc.gov.tw' in url else 'splits'
            return Response(200, source_fixture(name)[0])
        with patch('requests.get', side_effect=get), patch('time.sleep'):
            manifest = capture_official_data(['0050', '00981A'], '2026-09-01', '2026-09-30',
                self.directory, pace_seconds=0)
        payload = json.loads(manifest.read_text(encoding='utf-8'))
        self.assertEqual(len(payload['attempts']), len(payload['sources'])+1)
        first = payload['attempts'][0]
        self.assertEqual(first['status'], 429)
        self.assertEqual((manifest.parent/first['path']).read_bytes(), b'{"message":"rate limited"}')
        self.assertTrue(first['body_complete'])


if __name__ == '__main__':
    unittest.main()
