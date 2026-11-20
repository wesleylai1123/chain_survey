import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from core.multi_asset.adapters import load_request, load_csv_bundle, validate_request
from core.multi_asset.context import build_exposures, build_research_context
from core.multi_asset.service import validate_result


def request_fixture():
    """Synthetic TEST ONLY data; never a market observation."""
    stamp = '2026-01-01T00:00:00Z'
    return {
        'contract': 'MultiAssetResearchV1', 'schema_version': '1.0.0',
        'as_of': '2026-11-01T00:00:00Z', 'base_currency': 'USD',
        'objective': 'accumulation', 'periods_per_year': 12,
        'period_grid': ['2026-01-01', '2026-02-01', '2026-03-01'],
        'risk_free_rate': 0.0, 'rolling_windows': [2, 12],
        'instruments': [{
            'instrument_id': 'TEST-ETF', 'symbol': 'TEST', 'name': 'TEST ONLY ETF',
            'asset_type': 'etf', 'exchange': 'TEST', 'quote_currency': 'USD',
            'domicile': None, 'management_style': 'passive', 'benchmark_id': None,
            'return_basis': 'split_adjusted_price', 'distributions_complete': True,
            'corporate_actions_complete': True,
        }],
        'observations': [dict(instrument_id='TEST-ETF', period=period, value=value,
            published_at=period+'T23:00:00Z', acquired_at=period+'T23:00:00Z',
            source_url='https://example.org/test-only', snapshot_id='test-only')
            for period, value in [('2026-01-01', 100), ('2026-02-01', 90), ('2026-03-01', 110)]],
        'distributions': [], 'fx_rates': [], 'regimes': [],
        'cash_flow_assumptions': dict(initial_capital=10000, withholding_tax_rate=0.0,
            distribution_fee_rate=0.0, fx_fee_rate=0.0, buy_fee_rate=0.0, reinvest_fee_rate=0.0),
        'holdings': [dict(instrument_id='TEST-ETF', period='2026-01-01',
            published_at=stamp, acquired_at=stamp, source_url='https://example.org/test-only',
            snapshot_id='test-holdings', positions=[
                dict(security_id='3037.TW', weight=0.4, sector='Semiconductors', currency='TWD', factors={'value': 0.3}),
                dict(security_id='OTHER', weight=0.3, sector=None, currency=None, factors={})])],
        'evidence': [],
    }


class AdapterTests(unittest.TestCase):
    def test_versioned_raw_prices_are_accepted_without_relabeling(self):
        request = request_fixture()
        request['schema_version'] = '1.1.0'
        request['instruments'][0]['return_basis'] = 'unadjusted_price'
        validate_request(request)
        self.assertEqual(request['instruments'][0]['return_basis'], 'unadjusted_price')

    def test_unknown_schema_version_is_rejected_before_path_resolution(self):
        for version in ('1.2.0', '../../v1', None):
            request = request_fixture()
            request['schema_version'] = version
            with self.assertRaises(ValueError):
                validate_request(request)

    def test_load_hashes_exact_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'request.json'
            raw = json.dumps(request_fixture()).encode()
            path.write_bytes(raw)
            request, lineage = load_request(path)
            self.assertEqual(request['objective'], 'accumulation')
            self.assertEqual(lineage['sha256'], hashlib.sha256(raw).hexdigest())

    def test_schema_rejects_ambiguous_asset_and_naive_cutoff(self):
        for key, value in [('asset_type', 'crypto'), ('quote_currency', 'usd')]:
            request = request_fixture()
            request['instruments'][0][key] = value
            with self.assertRaises(ValueError):
                validate_request(request)
        request = request_fixture()
        request['as_of'] = '2026-10-01'
        with self.assertRaises(ValueError):
            validate_request(request)

    def test_unknown_row_values_remain_visible(self):
        request = request_fixture()
        request['observations'][0]['published_at'] = None
        request['observations'][0]['value'] = None
        validate_request(request)
        self.assertIsNone(request['observations'][0]['value'])

    def test_duplicate_identity_unknown_reference_and_nan_rejected(self):
        for change in ('duplicate', 'unknown', 'nan'):
            request = request_fixture()
            if change == 'duplicate':
                request['instruments'].append(copy.deepcopy(request['instruments'][0]))
            elif change == 'unknown':
                request['observations'][0]['instrument_id'] = 'NOT-KNOWN'
            else:
                request['observations'][0]['value'] = float('nan')
            with self.assertRaises(ValueError):
                validate_request(request)

    def test_csv_bundle_maps_types_preserves_null_and_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            request = request_fixture()
            request['observations'] = []
            (path/'prices.csv').write_text('instrument_id,period,value,published_at,acquired_at,source_url,snapshot_id\nTEST-ETF,2026-01-01,,2026-01-01T23:00:00Z,,https://example.org/test-only,test\n')
            manifest = {'request': request, 'files': {'observations': 'prices.csv'}}
            (path/'bundle.json').write_text(json.dumps(manifest))
            loaded, lineage = load_csv_bundle(path/'bundle.json')
            self.assertIsNone(loaded['observations'][0]['value'])
            self.assertIsNone(loaded['observations'][0]['acquired_at'])
            self.assertIn('observations', lineage['files'])

    def test_result_cannot_be_displayed_for_wrong_request(self):
        result = dict(contract='MultiAssetResultV1', schema_version='1.0.0',
            input_sha256='a'*64, as_of='2026-11-01T00:00:00Z', base_currency='USD',
            objective='accumulation', instruments=[], correlations=[], methodology={}, quality=[])
        with self.assertRaises(ValueError):
            validate_result(result, request_fixture(), 'b'*64)


class ContextTests(unittest.TestCase):
    def test_partial_holdings_keep_unknown_sector_and_currency_mass(self):
        request = request_fixture()
        exposure = build_exposures(request)[0]
        self.assertAlmostEqual(exposure['coverage'], 0.7)
        self.assertAlmostEqual(exposure['unknown_weight'], 0.3)
        self.assertAlmostEqual(exposure['currencies']['UNKNOWN'], 0.6)
        self.assertAlmostEqual(exposure['sectors']['Semiconductors'], 0.4)
        self.assertAlmostEqual(exposure['factors']['value']['weighted_loading'], 0.12)
        self.assertAlmostEqual(exposure['factors']['value']['coverage'], 0.4)

    def test_future_holdings_are_not_used_and_overweight_is_rejected(self):
        request = request_fixture()
        request['holdings'][0]['acquired_at'] = '2027-01-01T00:00:00Z'
        self.assertEqual(build_exposures(request)[0]['status'], 'MISSING')
        request = request_fixture()
        request['holdings'][0]['positions'][0]['weight'] = 0.9
        with self.assertRaises(ValueError):
            build_exposures(request)

    def test_abf_mapping_links_existing_taxonomy_without_fabricated_beta(self):
        context = build_research_context(request_fixture())
        self.assertTrue(any(row['timing_class'] == 'LEADING' for row in context['indicators']))
        self.assertEqual(context['scenarios']['UPSIDE'], [])
        self.assertEqual(context['scenarios']['DOWNSIDE'], [])
        self.assertIsNone(context['sensitivity'])
        self.assertIn('3037.TW', context['companies'])

    def test_scenarios_are_independent_and_future_evidence_excluded(self):
        request = request_fixture()
        common = dict(instrument_id='TEST-ETF', indicator_id='tpca_pcb_revenue_yoy',
            relative_to='abf_revenue', driver_id='end_demand', model_id='ic_substrate',
            published_at='2026-01-01T00:00:00Z', acquired_at='2026-01-01T00:00:00Z',
            source_url='https://example.org/test-only', snapshot_id='test', status='CANDIDATE',
            evidence_group='test', note='TEST ONLY')
        request['evidence'] = [dict(common, scenario='UPSIDE'), dict(common, scenario='DOWNSIDE', acquired_at='2027-01-01T00:00:00Z')]
        context = build_research_context(request)
        self.assertEqual(len(context['scenarios']['UPSIDE']), 1)
        self.assertEqual(context['scenarios']['DOWNSIDE'], [])

    def test_same_group_cannot_be_presented_as_independent_opposite_support(self):
        request = request_fixture()
        common = dict(instrument_id='TEST-ETF', indicator_id='test', relative_to='abf',
            driver_id='test', model_id='test', published_at='2026-01-01T00:00:00Z',
            acquired_at='2026-01-01T00:00:00Z', source_url='https://example.org/test',
            snapshot_id='test', status='CANDIDATE', evidence_group='one-event', note='TEST')
        request['evidence'] = [dict(common, scenario='UPSIDE'), dict(common, scenario='DOWNSIDE')]
        with self.assertRaises(ValueError):
            build_research_context(request)

    def test_latest_evidence_revision_wins_regardless_of_order(self):
        request = request_fixture()
        common = dict(instrument_id='TEST-ETF', indicator_id='test', relative_to='abf',
            driver_id='test', model_id='test', published_at='2026-01-01T00:00:00Z',
            acquired_at='2026-01-01T00:00:00Z', source_url='https://example.org/test',
            snapshot_id='test', status='CANDIDATE', evidence_group='one-event', note='TEST', scenario='UPSIDE')
        new = dict(common, acquired_at='2026-02-01T00:00:00Z', status='INSUFFICIENT')
        for rows in ([common, new], [new, common]):
            request['evidence'] = rows
            context = build_research_context(request)
            self.assertEqual(context['scenarios']['UPSIDE'][0]['status'], 'INSUFFICIENT')
            self.assertTrue(context['evidence_vintages'])

    def test_abf_sensitivity_reference_is_available_without_transferring_beta(self):
        context = build_research_context(request_fixture())
        self.assertIsNone(context['sensitivity'])
        self.assertEqual(context['sensitivity_references'][0]['availability'], 'REFERENCE_ONLY')

    def test_stock_alias_resolves_by_explicit_symbol(self):
        request = request_fixture()
        request['instruments'][0].update(asset_type='stock', instrument_id='local-stock-1', symbol='3037.TW')
        request['holdings'] = []
        request['observations'] = []
        self.assertTrue(build_research_context(request)['indicators'])


if __name__ == '__main__':
    unittest.main()
