"""Explicit peer integration, optional locally and mandatory in dedicated CI."""
import copy
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import shutil
import unittest

from core.multi_asset.official_capture import load_capture
from core.multi_asset.service import run_research, validate_result
from multi_asset_fixture import make_request

ROOT = Path(__file__).resolve().parents[1]
ENGINE = Path(os.environ.get('INVEST_BACKTEST_REPO', ROOT.parent/'invest_backtest'))
MARKET = Path(os.environ.get('MARKET_REPO', ROOT.parent/'market-temperature-dashboard'))
ETF_CONTEXT_CAPTURE = ROOT/'tests/fixtures/taiwan_etf_context/capture'
REFERENCE_SOURCES = {
    'TWSE.TAI50.TR': ('index:TAI50', 'Taiwan50TotalReturnIndex'),
    'TWSE.TAIEX.TR': ('index:TAIEX', 'TAIEXTotalReturnIndex'),
}


class MultiAssetIntegrationTests(unittest.TestCase):
    def setUp(self):
        if not (ENGINE/'scripts/run_multi_asset_research.py').exists():
            if os.environ.get('MULTI_ASSET_REQUIRE_PEERS') == '1':
                self.fail('Required metrics service checkout is absent')
            self.skipTest('Metrics service checkout is absent; dedicated multi-asset CI requires it')

    def test_real_service_deterministic_across_objectives_and_currencies(self):
        request = make_request()
        first = run_research(request, ENGINE)
        self.assertEqual(first, run_research(request, ENGINE))
        self.assertEqual(len(first['instruments']), 5)
        self.assertTrue(first['correlations'])
        for objective, currency in [('income', 'USD'), ('accumulation', 'TWD')]:
            request.update(objective=objective, base_currency=currency)
            result = run_research(request, ENGINE)
            self.assertEqual(result['objective'], objective)
            self.assertEqual(result['base_currency'], currency)

    def test_gaps_stay_unknown_in_real_service(self):
        request = make_request()
        request['observations'][0]['value'] = None
        result = run_research(request, ENGINE)
        passive = next(r for r in result['instruments'] if r['instrument_id'] == 'TEST-PASSIVE')
        self.assertIsNone(passive['metrics']['total_return'])
        self.assertTrue(passive['unavailable'])

    def test_request_schema_is_exact_consumer_snapshot(self):
        expected = (ROOT/'contracts/multi-asset/v1/schema.json').read_bytes()
        self.assertEqual(expected, (ENGINE/'contracts/multi-asset/v1/schema.json').read_bytes())
        result_schema = (ROOT/'contracts/multi-asset-result/v1/schema.json').read_bytes()
        self.assertEqual(result_schema, (ENGINE/'contracts/multi-asset-result/v1/schema.json').read_bytes())
        for contract in ('multi-asset', 'multi-asset-result'):
            self.assertEqual((ROOT/f'contracts/{contract}/v1.1/schema.json').read_bytes(),
                             (ENGINE/f'contracts/{contract}/v1.1/schema.json').read_bytes())

    def test_official_raw_fixture_never_claims_total_return(self):
        request = json.loads((ROOT/'contracts/multi-asset/v1.1/examples/valid-raw-prices-test-only.json').read_text(encoding='utf-8'))
        result = run_research(request, ENGINE)
        self.assertEqual(result['schema_version'], '1.1.0')
        raw = next(r for r in result['instruments'] if r['return_basis'] == 'unadjusted_price')
        self.assertIsNone(raw['metrics']['total_return'])
        self.assertIsNone(raw['metrics']['gross_paid_cash'])
        self.assertIn('total_return', raw['unavailable'])

    def test_response_boundary_rejects_missing_provenance_and_malformed_records(self):
        request = make_request()
        result = run_research(request, ENGINE)
        for corruption in ('quality', 'methodology', 'identity', 'returns'):
            invalid = copy.deepcopy(result)
            if corruption in ('quality', 'methodology'):
                del invalid[corruption]
            elif corruption == 'identity':
                invalid['instruments'][0]['quote_currency'] = 'TWD'
            else:
                invalid['instruments'][0]['returns'] = ['unbound return']
            with self.subTest(corruption=corruption), self.assertRaises(ValueError):
                validate_result(invalid, request, result['input_sha256'])

    def test_private_service_recomputes_public_golden_metrics(self):
        for name in ('accumulation', 'income', 'missing'):
            directory = ROOT/'tests/fixtures/multi_asset'
            request = json.loads((directory/f'{name}.request.json').read_text(encoding='utf-8'))
            expected = json.loads((directory/f'{name}.result.json').read_text(encoding='utf-8'))
            actual = run_research(request, ENGINE)
            self.assertEqual(actual['input_sha256'], expected['input_sha256'])
            for a, b in zip(actual['instruments'], expected['instruments']):
                self.assertEqual(a['instrument_id'], b['instrument_id'])
                self.assertEqual(a['unavailable'], b['unavailable'])
                for key, value in b['metrics'].items():
                    if value is None:
                        self.assertIsNone(a['metrics'][key])
                    else:
                        self.assertAlmostEqual(a['metrics'][key], value, places=9, msg=f'{name}/{a["instrument_id"]}/{key}')

    def test_real_regime_export_does_not_backdate_history(self):
        if not (MARKET/'export_market_regime.py').exists():
            if os.environ.get('MULTI_ASSET_REQUIRE_PEERS') == '1':
                self.fail('Required regime producer checkout absent')
            self.skipTest('Market regime producer absent')
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)/'regimes.json'
            completed = subprocess.run([sys.executable, str(MARKET/'export_market_regime.py'),
                '--input', str(MARKET/'data.json'), '--market', 'TW',
                '--captured-at', '2026-11-19T00:00:00Z', '--as-of', '2026-11-19T00:00:00Z',
                '--output', str(target)], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            request = make_request()
            request['as_of'] = '2026-11-19T00:00:00Z'
            before = run_research(request, ENGINE)
            request['regimes'] = json.loads(target.read_text(encoding='utf-8'))
            after = run_research(request, ENGINE)
            for a, b in zip(before['instruments'], after['instruments']):
                self.assertEqual(a['returns'], b['returns'])

    def test_main_cli_emits_valid_result_inside_research_report(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory)/'input.json', Path(directory)/'report.json'
            request = make_request()
            source.write_text(json.dumps(request), encoding='utf-8')
            command = [sys.executable, str(ROOT/'scripts/run_multi_asset_research.py'),
                '--input', str(source), '--output', str(target), '--engine-repo', str(ENGINE)]
            completed = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            report = json.loads(target.read_text(encoding='utf-8'))
            self.assertEqual(report['contract'], 'MultiAssetResearchReportV1')
            validate_result(report['result'], request, report['result']['input_sha256'])
            self.assertTrue(report['research_context']['indicators'])
            original = source.read_bytes()
            command[command.index('--output')+1] = str(source)
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertEqual(source.read_bytes(), original)

    def test_main_cli_verifies_official_capture_and_cannot_overwrite_it(self):
        fixture = ROOT/'tests/fixtures/taiwan_official/capture'
        with tempfile.TemporaryDirectory() as directory:
            frozen = Path(directory)/'capture'
            shutil.copytree(fixture, frozen)
            target = Path(directory)/'report.json'
            command = [sys.executable, str(ROOT/'scripts/run_multi_asset_research.py'),
                '--official-capture', '--input', str(frozen/'manifest.json'), '--output', str(target),
                '--engine-repo', str(ENGINE)]
            done = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr)
            report = json.loads(target.read_text(encoding='utf-8'))
            self.assertEqual(report['result']['schema_version'], '1.1.0')
            original = (frozen/'request.json').read_bytes()
            command[command.index('--output')+1] = str(frozen/'request.json')
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertEqual((frozen/'request.json').read_bytes(), original)

    def _load_etf_context_capture(self):
        manifest = ETF_CONTEXT_CAPTURE/'manifest.json'
        self.assertTrue(manifest.is_file(), 'Frozen real ETF context capture is missing')
        return load_capture(manifest)

    def _assert_frozen_result(self, actual, expected, path='result'):
        if isinstance(expected, dict):
            self.assertEqual(actual.keys(), expected.keys(), path)
            for key, value in expected.items():
                self._assert_frozen_result(actual[key], value, f'{path}.{key}')
        elif isinstance(expected, list):
            self.assertEqual(len(actual), len(expected), path)
            for index, (actual_item, expected_item) in enumerate(zip(actual, expected)):
                self._assert_frozen_result(actual_item, expected_item, f'{path}[{index}]')
        elif isinstance(expected, float):
            self.assertTrue(math.isfinite(actual) and math.isfinite(expected), path)
            self.assertAlmostEqual(actual, expected, delta=1e-12, msg=path)
        else:
            self.assertEqual(actual, expected, path)

    def _assert_official_index_returns(self, request, result):
        self.assertEqual(result['schema_version'], '1.1.0')
        instruments = {row['instrument_id']: row for row in result['instruments']}
        self.assertEqual(set(instruments), {'0050.TW', '00981A.TW', 'USD-TWD', *REFERENCE_SOURCES})
        for identity in ('0050.TW', '00981A.TW'):
            etf = instruments[identity]
            self.assertEqual(etf['return_basis'], 'unadjusted_price')
            self.assertIsNone(etf['benchmark_id'])
            self.assertFalse(etf['corporate_actions_complete'])
            self.assertFalse(etf['distributions_complete'])
            self.assertTrue(all(value is None for value in etf['metrics'].values()))
            self.assertTrue(all(row['value'] is None and row['local_return'] is None for row in etf['returns']))
            self.assertTrue(all(row['gross_cash'] is None and row['net_cash'] is None for row in etf['cash_flows']))

        manifest = json.loads((ETF_CONTEXT_CAPTURE/'manifest.json').read_bytes())
        source_paths = {row['source_id']: row['path'] for row in manifest['sources']}
        cbc_rows = json.loads((ETF_CONTEXT_CAPTURE/source_paths['fx']).read_bytes())
        cbc_rates = {row['日期']: Decimal(row['NTD_USD']) for row in cbc_rows}
        grid = request['period_grid']
        self.assertEqual(len(grid), 15)
        self.assertEqual((grid[0], grid[-1]), ('2026-11-02', '2026-11-20'))

        def return_between(levels, start, end, currency):
            factor = levels[end]/levels[start]
            if currency == 'USD':
                factor *= cbc_rates[start.replace('-', '')]/cbc_rates[end.replace('-', '')]
            return float(factor - 1)

        for identity, (source_id, total_return_field) in REFERENCE_SOURCES.items():
            with self.subTest(identity=identity, currency=result['base_currency']):
                index = instruments[identity]
                self.assertEqual(index['return_basis'], 'total_return_index')
                self.assertEqual(index['quote_currency'], 'TWD')
                self.assertIsNone(index['benchmark_id'])
                raw_index_rows = json.loads((ETF_CONTEXT_CAPTURE/source_paths[source_id]).read_bytes())
                levels = {
                    f'{1911 + int(row["Date"][:3])}-{row["Date"][3:5]}-{row["Date"][5:]}': Decimal(row[total_return_field])
                    for row in raw_index_rows
                }
                intervals = list(zip(grid, grid[1:]))
                self.assertEqual([(row['start'], row['end']) for row in index['returns']], intervals)
                for row, (start, end) in zip(index['returns'], intervals):
                    self.assertIsNone(row['reason'])
                    self.assertAlmostEqual(row['local_return'], return_between(levels, start, end, 'TWD'), delta=1e-12)
                    self.assertAlmostEqual(row['value'], return_between(levels, start, end, result['base_currency']), delta=1e-12)
                total = return_between(levels, grid[0], grid[-1], result['base_currency'])
                self.assertAlmostEqual(index['metrics']['total_return'], total, delta=1e-12)

    def test_official_etf_context_cli_recomputes_frozen_result_from_real_sources(self):
        request, lineage = self._load_etf_context_capture()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)/'report.json'
            completed = subprocess.run([sys.executable, str(ROOT/'scripts/run_multi_asset_research.py'),
                '--official-capture', '--input', str(ETF_CONTEXT_CAPTURE/'manifest.json'),
                '--output', str(target), '--engine-repo', str(ENGINE)],
                capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            report = json.loads(target.read_bytes())
        self.assertEqual(report['contract'], 'MultiAssetResearchReportV1')
        self.assertEqual(report['adapter_lineage'], lineage)
        result = report['result']
        expected = json.loads((ETF_CONTEXT_CAPTURE/'result.json').read_bytes())
        input_sha256 = hashlib.sha256((ETF_CONTEXT_CAPTURE/'request.json').read_bytes()).hexdigest()
        validate_result(expected, request, input_sha256)
        validate_result(result, request, input_sha256)
        self.assertEqual(result['base_currency'], 'TWD')
        self._assert_official_index_returns(request, result)
        self._assert_frozen_result(result, expected)

    def test_official_etf_context_usd_returns_use_exact_date_cbc_rates(self):
        request, _ = self._load_etf_context_capture()
        request['base_currency'] = 'USD'
        result = run_research(request, ENGINE)
        self.assertEqual(result['base_currency'], 'USD')
        self._assert_official_index_returns(request, result)


if __name__ == '__main__':
    unittest.main()
