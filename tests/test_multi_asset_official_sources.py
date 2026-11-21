"""Actual official response fixtures; mutations below are intentional invalid cases."""
import copy
import hashlib
import json
from pathlib import Path
import unittest

from core.multi_asset.official_sources import parse_prices, parse_distributions, parse_splits, parse_fx

FIXTURES = Path(__file__).parent/'fixtures/taiwan_official'


def source_fixture(name):
    record = next(r for r in json.loads((FIXTURES/'provenance.json').read_text(encoding='utf-8'))['sources'] if r['name'] == name)
    return (FIXTURES/record['path']).read_bytes(), record


def mutated(name, change):
    raw, metadata = source_fixture(name)
    payload = json.loads(raw)
    change(payload)
    raw = json.dumps(payload).encode('utf-8')
    metadata = dict(metadata, sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
    return raw, metadata


class OfficialSourceTests(unittest.TestCase):
    def test_actual_etf_closes_and_conservative_availability(self):
        for symbol, expected in [('0050', 108.45), ('00981A', 30.37)]:
            raw, metadata = source_fixture('price-'+symbol)
            rows = parse_prices(raw, metadata, symbol, '20260901')
            self.assertEqual(rows[0]['period'], '2026-09-01')
            self.assertEqual(rows[0]['value'], expected)
            self.assertEqual(rows[0]['instrument_id'], symbol+'.TW')
            self.assertEqual(rows[0]['published_at'], metadata['acquired_at'])
            self.assertEqual(rows[0]['acquired_at'], metadata['acquired_at'])
            self.assertEqual(rows[0]['snapshot_id'], metadata['sha256'])

    def test_dividends_preserve_actual_dates_and_unknown_classification(self):
        raw, metadata = source_fixture('div-00981A')
        rows = parse_distributions(raw, metadata, '00981A')
        row = next(r for r in rows if r['ex_date'] == '2026-09-16')
        self.assertEqual(row['pay_date'], '2026-10-13')
        self.assertEqual(row['record_date'], '2026-09-22')
        self.assertEqual(row['amount_per_unit'], 0.63)
        self.assertEqual(row['distribution_type'], 'unknown')
        self.assertEqual(row['currency'], 'TWD')

    def test_split_reference_prices_never_become_exact_split_ratio(self):
        raw, metadata = source_fixture('splits')
        rows = parse_splits(raw, metadata)
        row = next(r for r in rows if r['instrument_id'] == '0050.TW')
        self.assertEqual(row['period'], '2025-06-18')
        self.assertEqual(row['reference_before'], 188.65)
        self.assertEqual(row['reference_after'], 47.16)
        self.assertIsNone(row['ratio'])

    def test_cbc_fx_direction_and_actual_value(self):
        rows = parse_fx(*source_fixture('cbc-fx'))
        row = next(r for r in rows if r['period'] == '2026-09-01')
        self.assertEqual((row['base_currency'], row['quote_currency']), ('USD', 'TWD'))
        self.assertEqual(row['rate'], 31.633)

    def test_missing_close_remains_null_not_zero(self):
        raw, metadata = mutated('price-0050', lambda p: p['data'][0].__setitem__(6, '--'))
        self.assertIsNone(parse_prices(raw, metadata, '0050', '20260901')[0]['value'])

    def test_wrong_month_security_or_shape_rejected(self):
        cases = [lambda p: p.__setitem__('date', '20260801'),
                 lambda p: p.__setitem__('title', p['title'].replace('0050', '0051')),
                 lambda p: p['fields'].__setitem__(6, 'changed-field'),
                 lambda p: p['data'][0].pop()]
        for change in cases:
            raw, metadata = mutated('price-0050', change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                parse_prices(raw, metadata, '0050', '20260901')

    def test_conflicting_duplicate_not_silently_overwritten(self):
        def change(p):
            duplicate = copy.deepcopy(p['data'][0])
            duplicate[6] = '999.0'
            p['data'].append(duplicate)
        raw, metadata = mutated('price-0050', change)
        with self.assertRaises(ValueError):
            parse_prices(raw, metadata, '0050', '20260901')

    def test_hash_tampering_and_unknown_time_rejected(self):
        raw, metadata = source_fixture('cbc-fx')
        for invalid in [dict(metadata, sha256='a'*64), dict(metadata, acquired_at=None),
                        dict(metadata, acquired_at='2026-11-20'), dict(metadata, status=500)]:
            with self.assertRaises(ValueError):
                parse_fx(raw, invalid)

    def test_nonfinite_and_negative_values_rejected(self):
        for value in ('NaN', '-1', '0', 'Infinity'):
            raw, metadata = mutated('price-0050', lambda p: p['data'][0].__setitem__(6, value))
            with self.assertRaises(ValueError):
                parse_prices(raw, metadata, '0050', '20260901')

    def test_future_economic_dates_rejected(self):
        raw, metadata = source_fixture('cbc-fx')
        metadata = dict(metadata, acquired_at='2008-01-01T00:00:00Z')
        with self.assertRaises(ValueError):
            parse_fx(raw, metadata)

    def test_wrong_dividend_security_and_inverted_pay_date_rejected(self):
        for change in (lambda p: p['data'][0].__setitem__(0, '0050'),
                       lambda p: p['data'][0].__setitem__(4, '115年01月01日')):
            raw, metadata = mutated('div-00981A', change)
            with self.assertRaises(ValueError):
                parse_distributions(raw, metadata, '00981A')

    def test_record_date_malformed_and_future_split_rows_rejected(self):
        raw, metadata = mutated('div-00981A', lambda p: p['data'][0].__setitem__(3, 'NOT A DATE'))
        with self.assertRaises(ValueError):
            parse_distributions(raw, metadata, '00981A')
        raw, metadata = source_fixture('splits')
        with self.assertRaises(ValueError):
            parse_splits(raw, dict(metadata, acquired_at='2008-01-01T00:00:00Z'))


if __name__ == '__main__':
    unittest.main()
