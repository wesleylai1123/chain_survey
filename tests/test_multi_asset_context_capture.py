import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core.multi_asset import official_capture
from core.multi_asset.official_context import (
    context_source_requests, reference_instruments, reference_rows, valuation_rows,
)
from scripts import collect_taiwan_official_data


FIXTURES = Path(__file__).parent / 'fixtures'
CONTEXT = FIXTURES / 'taiwan_etf_context'
NOVEMBER = CONTEXT / 'base-capture' / 'manifest.json'
LEGACY = FIXTURES / 'taiwan_official' / 'capture' / 'manifest.json'
CONTEXT_FILES = {
    'nav': 'sitca-nav',
    'index:TAI50': 'tai50',
    'index:TAIEX': 'taiextr',
}
SYMBOLS = ['0050', '00981A']
REFERENCE_IDS = ['TWSE.TAI50.TR', 'TWSE.TAIEX.TR']
# Test-only capture completion time. Every fixture response retains its actual acquisition time.
TEST_CUTOFF = '2026-11-21T00:00:00+00:00'


def read_json(path):
    return json.loads(path.read_bytes())


def request_bytes(request):
    return (json.dumps(request, ensure_ascii=False, sort_keys=True, allow_nan=False) + '\n').encode()


def frozen_fetch(manifest, spec):
    source_id = spec['source_id']
    if source_id in CONTEXT_FILES:
        stem = CONTEXT_FILES[source_id]
        metadata = read_json(CONTEXT / (stem + '-provenance.json'))
        raw = (CONTEXT / (stem + '.bin')).read_bytes()
    else:
        metadata = next(entry for entry in read_json(manifest)['sources'] if entry['source_id'] == source_id)
        raw = (manifest.parent / metadata['path']).read_bytes()
    if metadata['source_url'] != spec['source_url']:
        raise AssertionError('The fixture URL differs from the requested URL')
    if hashlib.sha256(raw).hexdigest() != metadata['sha256'] or len(raw) != metadata['bytes']:
        raise AssertionError('The fixture body differs from its original proof')
    return raw, {'status': metadata['status'], 'acquired_at': metadata['acquired_at']}


def capture_from_fixtures(output_dir, original=NOVEMBER, *, fetcher=None, **kwargs):
    base = read_json(original)
    return official_capture.capture_official_data(
        base['symbols'], base['start'], base['end'], output_dir,
        fetcher=fetcher or (lambda spec: frozen_fetch(original, spec)),
        clock=lambda: TEST_CUTOFF, pace_seconds=0, **kwargs,
    )


class ContextCaptureTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        network = patch.object(official_capture.requests, 'get', side_effect=AssertionError('Unexpected network access'))
        network.start()
        self.addCleanup(network.stop)

    def capture(self, original=NOVEMBER, **kwargs):
        return capture_from_fixtures(self.directory, original, **kwargs)

    def test_both_old_frozen_requests_replay_byte_identically(self):
        for manifest in (LEGACY, NOVEMBER):
            with self.subTest(manifest=manifest):
                request, proof = official_capture.load_capture(manifest)
                self.assertEqual(request_bytes(request), (manifest.parent / 'request.json').read_bytes())
                self.assertEqual(proof['source_count'], len(read_json(manifest)['sources']))
                self.assertNotIn('etf_context', request['adapter_lineage'])

    def test_default_and_explicit_false_capture_equivalent_legacy_requests(self):
        default_path = self.capture()
        explicit_path = self.capture(include_etf_context=False)
        default, explicit = (official_capture.load_capture(path)[0] for path in (default_path, explicit_path))
        for path in (default_path, explicit_path):
            manifest = read_json(path)
            self.assertEqual((manifest['schema_version'], manifest['parser_version']),
                             ('1.0.0', 'taiwan-official-1.0.1'))
            self.assertEqual(manifest['sources'], read_json(NOVEMBER)['sources'])
            self.assertNotIn('reference_instruments', manifest)
        explicit['adapter_lineage']['capture_id'] = default['adapter_lineage']['capture_id']
        self.assertEqual(request_bytes(default), request_bytes(explicit))

    def test_opt_in_appends_three_sources_and_independent_references(self):
        path = self.capture(include_etf_context=True)
        manifest = read_json(path)
        request, proof = official_capture.load_capture(path)
        original, _ = official_capture.load_capture(NOVEMBER)
        self.assertEqual((manifest['schema_version'], manifest['parser_version']),
                         ('1.1.0', 'taiwan-official-1.1.0'))
        self.assertEqual(proof['source_count'], 9)
        self.assertEqual(manifest['sources'][:6], read_json(NOVEMBER)['sources'])
        self.assertEqual(manifest['reference_instruments'], reference_instruments())
        self.assertEqual(request['schema_version'], '1.1.0')
        self.assertEqual(request['instruments'][:3], original['instruments'])
        self.assertEqual(request['instruments'][3:], manifest['reference_instruments'])
        for fund in request['instruments'][:2]:
            self.assertEqual(fund['return_basis'], 'unadjusted_price')
            self.assertIsNone(fund['benchmark_id'])
            self.assertFalse(fund['corporate_actions_complete'])
            self.assertFalse(fund['distributions_complete'])
        self.assertEqual(request['period_grid'], original['period_grid'])
        self.assertEqual(request['observations'][:len(original['observations'])], original['observations'])
        self.assertEqual(request['distributions'], original['distributions'])
        self.assertEqual(request['fx_rates'], original['fx_rates'])
        self.assertEqual(request_bytes(request), (path.parent / 'request.json').read_bytes())

        lineage = request['adapter_lineage']
        self.assertEqual(lineage['parser_version'], manifest['parser_version'])
        self.assertEqual(lineage['sources'], manifest['sources'])
        self.assertEqual(len(manifest['attempts']), len(manifest['sources']))
        for spec, source, attempt in zip(context_source_requests(), manifest['sources'][6:], manifest['attempts'][6:]):
            raw, metadata = frozen_fetch(NOVEMBER, spec)
            self.assertEqual(source, dict(spec, **metadata, sha256=hashlib.sha256(raw).hexdigest(),
                                          bytes=len(raw), path=source['path']))
            self.assertEqual((path.parent / source['path']).read_bytes(), raw)
            self.assertEqual(attempt['sha256'], source['sha256'])
            self.assertEqual(attempt['acquired_at'], source['acquired_at'])
        context = lineage['etf_context']
        self.assertEqual(context['schema_version'], '1.0.0')
        self.assertEqual(context['reference_role'], 'independent_research_only')
        self.assertEqual(len(context['nav_observations']), 2)
        self.assertEqual(len(context['index_observations']), 30)
        raw_tai50 = [row for row in context['index_observations'] if row['instrument_id'] == REFERENCE_IDS[0]]
        canonical_tai50 = [row for row in request['observations'] if row['instrument_id'] == REFERENCE_IDS[0]]
        self.assertTrue(all('price_index' in row for row in raw_tai50))
        self.assertEqual(canonical_tai50, [
            {key: value for key, value in row.items() if key != 'price_index'} for row in raw_tai50
        ])
        self.assertTrue(all(row['reason'] == 'AVAILABLE' for row in valuation_rows(request)))
        self.assertTrue(all(row['available_count'] == 15 for row in reference_rows(request)))

    def test_partial_month_coverage_and_out_of_window_nav_keep_source_facts(self):
        request, _ = official_capture.load_capture(self.capture(LEGACY, include_etf_context=True))
        self.assertEqual(request['period_grid'], official_capture.load_capture(LEGACY)[0]['period_grid'])
        index_observations = [row for row in request['observations'] if row['instrument_id'] in REFERENCE_IDS]
        self.assertEqual(len(index_observations), 28)
        self.assertEqual(max(row['period'] for row in index_observations), '2026-11-19')
        for reference in reference_rows(request):
            self.assertEqual((reference['supplied_start'], reference['supplied_end']), ('2026-11-02', '2026-11-20'))
            self.assertEqual((reference['available_count'], reference['grid_count'], reference['reason']),
                             (14, 53, 'PARTIAL_COVERAGE'))
        for row in valuation_rows(request):
            self.assertEqual(row['period'], '2026-11-20')
            self.assertGreater(row['nav'], 0)
            self.assertIsNone(row['premium_discount'])
            self.assertEqual(row['reason'], 'OUTSIDE_PERIOD_GRID')

    def test_supplied_index_dates_with_no_grid_overlap_remain_in_lineage(self):
        def fetch(spec):
            raw, metadata = frozen_fetch(LEGACY, spec)
            if spec['source_id'] in {'index:TAI50', 'index:TAIEX'}:
                # Test-only responses with one supplied date after the original grid.
                raw = json.dumps([row for row in json.loads(raw) if row['Date'] == '1151120']).encode()
            return raw, metadata

        request, _ = official_capture.load_capture(self.capture(LEGACY, fetcher=fetch, include_etf_context=True))
        self.assertTrue(set(REFERENCE_IDS).isdisjoint(row['instrument_id'] for row in request['observations']))
        references = reference_rows(request)
        self.assertEqual(len(references), 2)
        for reference in references:
            self.assertEqual((reference['supplied_start'], reference['supplied_end']), ('2026-11-20', '2026-11-20'))
            self.assertEqual((reference['available_count'], reference['reason']), (0, 'NO_USABLE_OBSERVATIONS'))

    def test_empty_index_responses_keep_declared_references(self):
        def fetch(spec):
            raw, metadata = frozen_fetch(NOVEMBER, spec)
            return (b'[]', metadata) if spec['source_id'] in {'index:TAI50', 'index:TAIEX'} else (raw, metadata)

        request, _ = official_capture.load_capture(self.capture(fetcher=fetch, include_etf_context=True))
        self.assertEqual(request['adapter_lineage']['etf_context']['index_observations'], [])
        references = reference_rows(request)
        self.assertEqual([row['instrument_id'] for row in references], REFERENCE_IDS)
        self.assertTrue(all(row['reason'] == 'NO_SUPPLIED_OBSERVATIONS' for row in references))

    def test_context_flag_is_boolean_and_source_order_is_explicit(self):
        args = (SYMBOLS, '2026-11-02', '2026-11-20')
        original = official_capture.source_requests(*args)
        self.assertEqual(official_capture.source_requests(*args, include_etf_context=False), original)
        self.assertEqual(official_capture.source_requests(*args, include_etf_context=True),
                         original + context_source_requests())
        for invalid in (None, 0, 1, 'false', []):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, 'include_etf_context.*boolean'):
                    official_capture.source_requests(*args, include_etf_context=invalid)
                with self.assertRaisesRegex(ValueError, 'include_etf_context.*boolean'):
                    self.capture(include_etf_context=invalid)
        self.assertFalse((self.directory / 'runs').exists())

    def test_failed_context_source_preserves_latest_good_and_failed_evidence(self):
        self.capture()
        pointer = self.directory / 'latest-good.json'
        before = pointer.read_bytes()

        def fetch(spec):
            raw, metadata = frozen_fetch(NOVEMBER, spec)
            if spec['source_id'] == 'index:TAIEX':
                return b'provider unavailable', dict(metadata, status=503)
            return raw, metadata

        with self.assertRaisesRegex(ValueError, 'HTTP status'):
            self.capture(fetcher=fetch, include_etf_context=True)
        self.assertEqual(pointer.read_bytes(), before)
        failed_path, = self.directory.glob('runs/*/failed.json')
        failed = read_json(failed_path)
        self.assertEqual(failed['status'], 'FAILED')
        self.assertEqual(failed['schema_version'], '1.1.0')
        last = failed['attempts'][-1]
        self.assertEqual((last['source_id'], last['status']), ('index:TAIEX', 503))
        self.assertEqual((failed_path.parent / last['path']).read_bytes(), b'provider unavailable')
        self.assertFalse((failed_path.parent / 'manifest.json').exists())

    def test_replay_uses_frozen_reference_names(self):
        path = self.capture(include_etf_context=True)
        expected, _ = official_capture.load_capture(path)
        renamed = [dict(item, name='New registry display name') for item in reference_instruments()]
        with patch.object(official_capture, 'reference_instruments', return_value=renamed):
            replayed, _ = official_capture.load_capture(path)
        self.assertEqual(replayed, expected)

    def test_replay_rejects_context_manifest_and_request_tampering(self):
        path = self.capture(include_etf_context=True)
        original = path.read_bytes()

        def write_manifest(change):
            payload = json.loads(original)
            change(payload)
            path.write_bytes(request_bytes(payload))

        cases = [
            ('Unsupported', lambda m: m.update(schema_version='1.0.0')),
            ('Unsupported', lambda m: m.update(parser_version='taiwan-official-1.0.1')),
            ('Unsupported', lambda m: m.update(schema_version='2.0.0', parser_version='taiwan-official-2.0.0')),
            ('required source', lambda m: m['sources'].pop()),
            ('source identity', lambda m: m['sources'].append(m['sources'].pop(-2))),
            ('source identity', lambda m: m['sources'][-3].update(source_url='https://www.sitca.org.tw/alternate.csv')),
            ('source identity', lambda m: m['sources'][-2].update(symbol='0050')),
            ('unavailable at cutoff', lambda m: m['sources'][-2].update(acquired_at='2027-01-01T00:00:00Z')),
            ('path escapes', lambda m: m['sources'][-2].update(path='../outside.bin')),
            ('hash or byte count', lambda m: m['sources'][-2].update(sha256='0' * 64)),
            ('reference instrument', lambda m: m.pop('reference_instruments')),
            ('reference instrument', lambda m: m['reference_instruments'].reverse()),
            ('reference instrument', lambda m: m['reference_instruments'][0].update(instrument_id='FAKE')),
            ('reference instrument', lambda m: m['reference_instruments'][0].update(quote_currency='USD')),
            ('reference instrument', lambda m: m['reference_instruments'][0].update(return_basis='unadjusted_price')),
            ('reference instrument', lambda m: m['reference_instruments'][0].update(distributions_complete=1)),
            ('reference instrument', lambda m: m['reference_instruments'][0].update(name=' ')),
            ('deterministic replay', lambda m: m['reference_instruments'][0].update(name='Tampered frozen name')),
            ('deterministic replay', lambda m: m.update(request_sha256='0' * 64)),
        ]
        for number, (message, change) in enumerate(cases, start=1):
            with self.subTest(message=message, case=number):
                write_manifest(change)
                with self.assertRaisesRegex(ValueError, message):
                    official_capture.load_capture(path)

        path.write_bytes(original)
        manifest = json.loads(original)
        raw_path = path.parent / manifest['sources'][-1]['path']
        raw = raw_path.read_bytes()
        raw_path.write_bytes(raw + b' ')
        with self.assertRaisesRegex(ValueError, 'hash or byte count'):
            official_capture.load_capture(path)
        raw_path.write_bytes(raw)
        saved_path = path.parent / manifest['request_path']
        altered = saved_path.read_bytes() + b' '
        saved_path.write_bytes(altered)
        write_manifest(lambda m: m.update(request_sha256=hashlib.sha256(altered).hexdigest()))
        with self.assertRaisesRegex(ValueError, 'deterministic replay'):
            official_capture.load_capture(path)

    def test_cli_only_opts_in_when_requested(self):
        args = ['collector', '--start', '2026-11-02', '--end', '2026-11-20',
                '--output-dir', str(self.directory)]
        for flag in ([], ['--include-etf-context']):
            with self.subTest(flag=flag), patch('sys.argv', args + flag), patch(
                'scripts.collect_taiwan_official_data.capture_official_data', return_value=NOVEMBER,
            ) as capture, patch('builtins.print'):
                self.assertEqual(collect_taiwan_official_data.main(), 0)
                self.assertIs(capture.call_args.kwargs['include_etf_context'], bool(flag))

    def test_cli_replay_uses_only_the_saved_capture_in_either_mode(self):
        modern = self.capture(include_etf_context=True)
        for path, count in ((LEGACY, 3), (modern, 5)):
            for flag in ([], ['--include-etf-context']):
                with self.subTest(path=path, flag=flag), patch(
                    'sys.argv', ['collector', '--replay', str(path)] + flag,
                ), patch('builtins.print') as output, patch(
                    'scripts.collect_taiwan_official_data.capture_official_data',
                    side_effect=AssertionError('Replay must not run live collection'),
                ):
                    self.assertEqual(collect_taiwan_official_data.main(), 0)
                    self.assertTrue(output.call_args.args[0].startswith(f'OFFICIAL_REPLAY_OK assets={count} '))


if __name__ == '__main__':
    unittest.main()
