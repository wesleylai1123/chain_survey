"""Original official captures, plus explicit mutations for invalid source cases."""
import copy
import csv
import hashlib
import io
import json
from pathlib import Path
import unittest

from core.multi_asset import official_context as context

FIXTURES = Path(__file__).parent / 'fixtures/taiwan_etf_context'


def fixture(name):
    return ((FIXTURES / (name + '.bin')).read_bytes(),
            json.loads((FIXTURES / (name + '-provenance.json')).read_text(encoding='utf-8')))


def signed(raw, metadata):
    return raw, dict(metadata, sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))


def nav_records():
    raw, _ = fixture('sitca-nav')
    return list(csv.reader(io.StringIO(raw.decode('utf-8-sig'), newline='')))


def nav_mutation(change):
    records = nav_records()
    change(records)
    out = io.StringIO(newline='')
    csv.writer(out).writerows(records)
    return signed(out.getvalue().encode('utf-8-sig'), fixture('sitca-nav')[1])


def selected(records, symbol='0050'):
    return next(row for row in records[1:] if row[-1] == symbol)


def index_mutation(change, name='tai50'):
    raw, metadata = fixture(name)
    payload = json.loads(raw)
    change(payload)
    return signed(json.dumps(payload).encode('utf-8'), metadata)


def observation(period='2026-11-20', value=90.0, **extra):
    return dict(instrument_id='0050.TW', period=period, value=value,
                published_at='2026-11-20T23:00:00Z', acquired_at='2026-11-20T23:00:00Z',
                source_url='https://example.test/close', snapshot_id='close', **extra)


def nav_row(period='2026-11-20', nav=84.67, currency='TWD'):
    row = observation(period)
    row.pop('value')
    row.update(nav=nav, currency=currency, source_url='https://example.test/nav', snapshot_id='nav')
    return row


def request(nav=None, indices=None):
    result = dict(as_of='2026-11-21T00:00:00Z', period_grid=['2026-11-19', '2026-11-20'],
                instruments=[dict(instrument_id='0050.TW', asset_type='etf', quote_currency='TWD')],
                observations=[observation()],
                adapter_lineage=dict(etf_context=dict(schema_version='1.0.0',
                    nav_observations=nav if nav is not None else [nav_row()],
                    index_observations=indices or [])))
    supplied = {r.get('instrument_id') for r in (indices or [])
                if isinstance(r, dict) and isinstance(r.get('instrument_id'), str)}
    for instrument in context.reference_instruments():
        if instrument['instrument_id'] in supplied:
            result['instruments'].append(instrument)
            result['observations'].extend({key: value for key, value in row.items() if key != 'price_index'}
                for row in indices if isinstance(row, dict) and row.get('instrument_id') == instrument['instrument_id'])
    return result


class OfficialContextTests(unittest.TestCase):
    def test_fixed_source_specs_and_reference_identities_are_independent(self):
        specs = context.context_source_requests()
        self.assertEqual(context.CONTEXT_PARSER_VERSION, 'taiwan-official-1.1.0')
        self.assertEqual([(s['source_id'], s['kind'], s['symbol'], s['month']) for s in specs],
                         [('nav', 'nav', None, None), ('index:TAI50', 'index_tai50', None, None),
                          ('index:TAIEX', 'index_taiex', None, None)])
        self.assertEqual([s['source_url'] for s in specs], [
            'https://www.sitca.org.tw/MemberK0000/F/03/nav.csv',
            'https://openapi.twse.com.tw/v1/indicesReport/TAI50I',
            'https://openapi.twse.com.tw/v1/indicesReport/MFI94U'])
        refs = context.reference_instruments()
        self.assertEqual([r['instrument_id'] for r in refs], ['TWSE.TAI50.TR', 'TWSE.TAIEX.TR'])
        self.assertEqual([r['symbol'] for r in refs], ['TAI50.TR', 'TAIEX.TR'])
        for row in refs:
            self.assertEqual((row['asset_type'], row['exchange'], row['quote_currency'],
                              row['domicile'], row['market'], row['management_style'], row['return_basis']),
                             ('benchmark', 'TWSE', 'TWD', 'TW', 'TW', 'none', 'total_return_index'))
            self.assertIsNone(row['benchmark_id'])
            self.assertTrue(row['corporate_actions_complete'])
            self.assertTrue(row['distributions_complete'])
        specs[0]['kind'] = 'mutated'
        refs[0]['name'] = 'mutated'
        self.assertEqual(context.context_source_requests()[0]['kind'], 'nav')
        self.assertNotEqual(context.reference_instruments()[0]['name'], 'mutated')

    def test_actual_nav_uses_certificate_identity_date_currency_and_provenance(self):
        raw, metadata = fixture('sitca-nav')
        rows = context.parse_nav(raw, metadata, ['0050', '00981A'])
        self.assertEqual([(r['instrument_id'], r['period'], r['nav'], r['currency']) for r in rows],
                         [('0050.TW', '2026-11-20', 84.67, 'TWD'),
                          ('00981A.TW', '2026-11-20', 18.81, 'TWD')])
        for row in rows:
            self.assertEqual(row['published_at'], metadata['acquired_at'])
            self.assertEqual(row['acquired_at'], metadata['acquired_at'])
            self.assertEqual(row['source_url'], metadata['source_url'])
            self.assertEqual(row['snapshot_id'], metadata['sha256'])
        self.assertEqual(context.parse_nav(raw, metadata, ['DDE02']), [])

    def test_nav_selects_exact_certificate_not_internal_code_name_or_prefix(self):
        def change(records):
            row = selected(records)
            row[4], row[5], row[-1] = '0050', '0050', '0050X'
        self.assertEqual(context.parse_nav(*nav_mutation(change), ['0050']), [])

    def test_nav_unrelated_currency_is_not_rejected(self):
        def change(records):
            records[1][10] = 'USD'
        self.assertEqual(len(context.parse_nav(*nav_mutation(change), ['0050', '00981A'])), 2)

    def test_nav_missing_markers_stay_unknown(self):
        for value in ('', '--', '---'):
            with self.subTest(value=value):
                raw, metadata = nav_mutation(lambda rows: selected(rows).__setitem__(6, value))
                self.assertIsNone(context.parse_nav(raw, metadata, ['0050'])[0]['nav'])

    def test_nav_invalid_values_currency_and_dates_fail_closed(self):
        cases = [(6, '0'), (6, '-1'), (6, 'NaN'), (6, 'Infinity'), (10, 'USD'),
                 (0, '20260230'), (0, '20261122'), (0, '1151120'), (0, 'garbage')]
        for field, value in cases:
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                context.parse_nav(*nav_mutation(lambda rows: selected(rows).__setitem__(field, value)), ['0050'])

    def test_nav_rejects_header_and_row_drift_even_in_unrelated_records(self):
        cases = [lambda r: r[0].__setitem__(0, 'changed'),
                 lambda r: r[0].__setitem__(1, r[0][0]),
                 lambda r: r[1].pop(), lambda r: r[1].append('unexpected')]
        for change in cases:
            with self.subTest(change=change), self.assertRaises(ValueError):
                context.parse_nav(*nav_mutation(change), ['0050'])

    def test_nav_requires_strict_utf8_and_csv_quoting(self):
        raw, metadata = fixture('sitca-nav')
        for invalid in (raw + b'\xff', raw + b'\r\n"unterminated'):
            with self.subTest(invalid=invalid[-15:]), self.assertRaises(ValueError):
                context.parse_nav(*signed(invalid, metadata), ['0050'])

    def test_nav_duplicate_equal_values_coalesce_but_conflicts_fail(self):
        def duplicate(rows, value):
            row = selected(rows).copy()
            row[6] = value
            rows.append(row)
        self.assertEqual(len(context.parse_nav(*nav_mutation(lambda r: duplicate(r, '84.67')), ['0050'])), 1)
        with self.assertRaises(ValueError):
            context.parse_nav(*nav_mutation(lambda r: duplicate(r, '99')), ['0050'])

    def test_source_hash_size_status_and_aware_time_are_required_for_csv_and_json(self):
        for name, parse in [('sitca-nav', lambda r, m: context.parse_nav(r, m, ['0050'])),
                            ('tai50', lambda r, m: context.parse_index(r, m, 'index_tai50'))]:
            raw, metadata = fixture(name)
            for patch in [dict(sha256='0'*64), dict(bytes=len(raw)+1), dict(status=500),
                          dict(acquired_at=None), dict(acquired_at='2026-11-21')]:
                with self.subTest(name=name, patch=patch), self.assertRaises(ValueError):
                    parse(raw, dict(metadata, **patch))

    def test_actual_reference_values_use_total_return_field_and_compact_roc_dates(self):
        tai50 = context.parse_index(*fixture('tai50'), 'index_tai50')
        taiex = context.parse_index(*fixture('taiextr'), 'index_taiex')
        self.assertEqual(len(tai50), 15)
        self.assertEqual(len(taiex), 15)
        self.assertEqual((tai50[0]['instrument_id'], tai50[0]['period'], tai50[0]['value'], tai50[0]['price_index']),
                         ('TWSE.TAI50.TR', '2026-11-02', 95804.85, 41411.33))
        self.assertEqual((taiex[-1]['instrument_id'], taiex[-1]['period'], taiex[-1]['value']),
                         ('TWSE.TAIEX.TR', '2026-11-20', 83329.36))
        self.assertNotIn('price_index', taiex[0])
        self.assertEqual(tai50[0]['snapshot_id'], fixture('tai50')[1]['sha256'])

    def test_missing_total_return_never_falls_back_to_price_index(self):
        for value in (None, '', '--', '---'):
            with self.subTest(value=value):
                raw, metadata = index_mutation(lambda p: p[0].__setitem__('Taiwan50TotalReturnIndex', value))
                row = context.parse_index(raw, metadata, 'index_tai50')[0]
                self.assertIsNone(row['value'])
                self.assertEqual(row['price_index'], 41411.33)

    def test_index_rejects_field_date_shape_and_numeric_drift(self):
        changes = [lambda p: p[0].pop('Taiwan50TotalReturnIndex'),
                   lambda p: p[0].__setitem__('Extra', '1'),
                   lambda p: p.__setitem__(0, [])]
        changes += [lambda p, v=v: p[0].__setitem__('Date', v)
                    for v in ('20261102', '115/11/02', '1150230', '1151122', 1151102)]
        changes += [lambda p, v=v: p[0].__setitem__('Taiwan50TotalReturnIndex', v)
                    for v in ('0', '-1', 'NaN', 'Infinity', True)]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                context.parse_index(*index_mutation(change), 'index_tai50')
        with self.assertRaises(ValueError):
            context.parse_index(*fixture('tai50'), 'unknown')
        with self.assertRaises(ValueError):
            context.parse_index(*fixture('tai50'), 'index_taiex')

    def test_index_json_duplicate_keys_and_nonfinite_literals_are_rejected(self):
        _, metadata = fixture('tai50')
        for raw in [b'[{"Date":"1151102","Date":"1151103"}]',
                    b'[{"Date":"1151102","Taiwan50Index":1,"Taiwan50TotalReturnIndex":NaN}]']:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                context.parse_index(*signed(raw, metadata), 'index_tai50')

    def test_empty_index_array_has_no_supplied_observations(self):
        self.assertEqual(context.parse_index(*index_mutation(lambda p: p.clear()), 'index_tai50'), [])

    def test_index_duplicate_dates_coalesce_equal_values_and_reject_conflict(self):
        def duplicate(payload, change=False):
            row = payload[0].copy()
            if change:
                row['Taiwan50TotalReturnIndex'] = '99999'
            payload.append(row)
        self.assertEqual(len(context.parse_index(*index_mutation(duplicate), 'index_tai50')), 15)
        with self.assertRaises(ValueError):
            context.parse_index(*index_mutation(lambda p: duplicate(p, True)), 'index_tai50')

    def test_both_parser_types_reject_future_economic_dates(self):
        for name, parse in [('sitca-nav', lambda r, m: context.parse_nav(r, m, ['0050'])),
                            ('tai50', lambda r, m: context.parse_index(r, m, 'index_tai50'))]:
            raw, metadata = fixture(name)
            with self.subTest(name=name), self.assertRaises(ValueError):
                parse(raw, dict(metadata, acquired_at='2026-11-01T00:00:00Z'))

    def test_valuation_exact_day_native_currency_ratio_and_source_facts(self):
        row = context.valuation_rows(request())[0]
        self.assertEqual((row['instrument_id'], row['period'], row['nav'], row['close'], row['currency']),
                         ('0050.TW', '2026-11-20', 84.67, 90.0, 'TWD'))
        self.assertAlmostEqual(row['premium_discount'], 90.0 / 84.67 - 1)
        self.assertEqual(row['reason'], 'AVAILABLE')
        self.assertEqual((row['nav_source_url'], row['price_source_url']),
                         ('https://example.test/nav', 'https://example.test/close'))

    def test_valuation_no_nearest_date_or_out_of_window_ratio(self):
        req = request()
        req['observations'][0]['period'] = '2026-11-19'
        row = context.valuation_rows(req)[0]
        self.assertIsNone(row['premium_discount'])
        self.assertIsNone(row['close'])
        self.assertEqual(row['reason'], 'PRICE_MISSING')
        req = request([nav_row('2026-11-18')])
        req['observations'] = [observation('2026-11-18')]
        row = context.valuation_rows(req)[0]
        self.assertEqual((row['nav'], row['close']), (84.67, 90.0))
        self.assertIsNone(row['premium_discount'])
        self.assertEqual(row['reason'], 'OUTSIDE_PERIOD_GRID')

    def test_valuation_currency_mismatch_and_unknown_currency_prevent_ratio(self):
        req = request([nav_row(currency='USD')])
        self.assertEqual(context.valuation_rows(req)[0]['reason'], 'CURRENCY_MISMATCH')
        req = request()
        req['instruments'][0].pop('quote_currency')
        self.assertEqual(context.valuation_rows(req)[0]['reason'], 'CURRENCY_UNKNOWN')
        req = request()
        req['observations'][0]['currency'] = 'USD'
        self.assertEqual(context.valuation_rows(req)[0]['reason'], 'CURRENCY_MISMATCH')
        self.assertIsNone(context.valuation_rows(req)[0]['premium_discount'])

    def test_unavailable_nav_and_price_retain_facts_without_ratio(self):
        for collection, reason in [('nav_observations', 'NAV_UNAVAILABLE_AS_OF'),
                                   ('observations', 'PRICE_UNAVAILABLE_AS_OF')]:
            req = request()
            rows = (req['adapter_lineage']['etf_context'][collection]
                    if collection == 'nav_observations' else req[collection])
            rows[0]['acquired_at'] = '2026-11-22T00:00:00Z'
            row = context.valuation_rows(req)[0]
            self.assertEqual((row['nav'], row['close']), (84.67, 90.0))
            self.assertIsNone(row['premium_discount'])
            self.assertEqual(row['reason'], reason)
        req = request()
        req['adapter_lineage']['etf_context']['nav_observations'][0]['published_at'] = None
        self.assertEqual(context.valuation_rows(req)[0]['reason'], 'NAV_UNAVAILABLE_AS_OF')

    def test_valuation_missing_and_nonpositive_facts_never_divide(self):
        for value in (None, 0, -1, float('nan'), True):
            req = request([nav_row(nav=value)])
            self.assertIsNone(context.valuation_rows(req)[0]['premium_discount'])
            self.assertIn(context.valuation_rows(req)[0]['reason'], ('NAV_MISSING', 'NAV_INVALID'))
            req = request()
            req['observations'][0]['value'] = value
            self.assertIsNone(context.valuation_rows(req)[0]['premium_discount'])

    def test_finite_positive_inputs_cannot_emit_nonfinite_valuation_ratio(self):
        # Test-only numerical boundary; these values are not financial source data.
        req = request([nav_row(nav=1e-308)])
        req['observations'][0]['value'] = 1e308
        row = context.valuation_rows(req)[0]
        self.assertEqual((row['nav'], row['close']), (1e-308, 1e308))
        self.assertIsNone(row['premium_discount'])
        self.assertEqual(row['reason'], 'CALCULATION_NONFINITE')

    def test_huge_json_integers_are_unusable_without_helper_overflow(self):
        # Test-only JSON integer outside the floating-point range.
        huge = json.loads('1' + '0'*400)
        req = request([nav_row(nav=huge)])
        row = context.valuation_rows(req)[0]
        self.assertIsNone(row['premium_discount'])
        self.assertEqual(row['reason'], 'NAV_INVALID')
        req = request()
        req['observations'][0]['value'] = huge
        self.assertEqual(context.valuation_rows(req)[0]['reason'], 'PRICE_INVALID')
        indices = context.parse_index(*fixture('tai50'), 'index_tai50')
        indices[-1]['value'] = huge
        req = request(indices=indices)
        self.assertEqual(context.reference_rows(req)[0]['available_count'], 1)

    def test_valuation_latest_eligible_vintage_ignores_future_revision(self):
        req = request()
        older = nav_row(nav=80)
        future = nav_row(nav=100)
        future.update(published_at='2026-11-22T00:00:00Z', acquired_at='2026-11-22T00:00:00Z')
        req['adapter_lineage']['etf_context']['nav_observations'] = [future, older]
        req['observations'].append(dict(observation(value=88),
                                       published_at='2026-11-20T22:00:00Z', acquired_at='2026-11-20T22:00:00Z'))
        rows = context.valuation_rows(req)
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]['nav'], rows[0]['close']), (80, 90))
        self.assertAlmostEqual(rows[0]['premium_discount'], .125)

    def test_same_latest_vintage_conflicts_cannot_choose_arbitrary_ratio(self):
        for collection, reason in [('nav_observations', 'NAV_CONFLICT'), ('observations', 'PRICE_CONFLICT')]:
            req = request()
            if collection == 'nav_observations':
                req['adapter_lineage']['etf_context'][collection].append(nav_row(nav=90))
            else:
                req[collection].append(observation(value=100))
            for _ in range(2):
                rows = context.valuation_rows(req)
                self.assertEqual(len(rows), 1)
                self.assertIsNone(rows[0]['premium_discount'])
                self.assertEqual(rows[0]['reason'], reason)
                if collection == 'nav_observations':
                    req['adapter_lineage']['etf_context'][collection].reverse()
                else:
                    req[collection].reverse()

    def test_reference_source_range_is_supplied_range_and_missing_months_are_gaps(self):
        indices = context.parse_index(*fixture('tai50'), 'index_tai50')
        req = request(indices=indices)
        req['period_grid'] = ['2026-09-01', '2026-10-01', '2026-11-02', '2026-11-20']
        refs = context.reference_rows(req)
        row = next(r for r in refs if r['instrument_id'] == 'TWSE.TAI50.TR')
        self.assertEqual((row['supplied_start'], row['supplied_end']), ('2026-11-02', '2026-11-20'))
        self.assertEqual((row['available_count'], row['grid_count'], row['reason']), (2, 4, 'PARTIAL_COVERAGE'))
        self.assertEqual(row['source_url'], fixture('tai50')[1]['source_url'])

    def test_reference_coverage_uses_unique_positive_available_nonconflicting_dates(self):
        indices = context.parse_index(*fixture('taiextr'), 'index_taiex')
        req = request(indices=indices)
        req['period_grid'] = ['2026-11-19', '2026-11-20']
        row = next(r for r in context.reference_rows(req) if r['instrument_id'] == 'TWSE.TAIEX.TR')
        self.assertEqual((row['available_count'], row['reason']), (2, 'AVAILABLE'))
        req['adapter_lineage']['etf_context']['index_observations'].append(copy.deepcopy(indices[-1]))
        self.assertEqual(context.reference_rows(req)[0]['available_count'], 2)
        req['as_of'] = '2026-11-01T00:00:00Z'
        row = context.reference_rows(req)[0]
        self.assertEqual((row['available_count'], row['reason']), (0, 'UNAVAILABLE_AS_OF'))
        self.assertEqual(row['supplied_end'], '2026-11-20')
        req['as_of'] = '2026-11-21T00:00:00Z'
        req['adapter_lineage']['etf_context']['index_observations'][-1]['value'] = 1
        self.assertEqual(context.reference_rows(req)[0]['available_count'], 1)
        next(r for r in indices if r['period'] == '2026-11-19')['value'] = None
        self.assertEqual(context.reference_rows(req)[0]['available_count'], 0)

    def test_reference_coverage_requires_matching_canonical_observation(self):
        indices = context.parse_index(*fixture('tai50'), 'index_tai50')
        req = request(indices=indices)
        self.assertEqual(context.reference_rows(req)[0]['available_count'], 2)
        req['observations'] = [r for r in req['observations']
                               if not (r['instrument_id'] == 'TWSE.TAI50.TR' and r['period'] == '2026-11-20')]
        row = context.reference_rows(req)[0]
        self.assertEqual((row['available_count'], row['grid_count'], row['reason']), (1, 2, 'PARTIAL_COVERAGE'))
        self.assertEqual((row['supplied_start'], row['supplied_end']), ('2026-11-02', '2026-11-20'))

    def test_reference_source_disagreement_is_not_usable_canonical_coverage(self):
        indices = context.parse_index(*fixture('tai50'), 'index_tai50')
        req = request(indices=indices)
        next(r for r in req['observations'] if r['instrument_id'] == 'TWSE.TAI50.TR'
             and r['period'] == '2026-11-20')['value'] = 1
        row = context.reference_rows(req)[0]
        self.assertEqual((row['available_count'], row['reason']), (1, 'PARTIAL_COVERAGE'))

    def test_reference_canonical_vintages_must_be_available_and_nonconflicting(self):
        indices = context.parse_index(*fixture('tai50'), 'index_tai50')
        req = request(indices=indices)
        latest = next(r for r in req['observations'] if r['instrument_id'] == 'TWSE.TAI50.TR'
                      and r['period'] == '2026-11-20')
        latest['acquired_at'] = '2026-11-22T00:00:00Z'
        self.assertEqual(context.reference_rows(req)[0]['available_count'], 1)
        latest['acquired_at'] = indices[-1]['acquired_at']
        req['observations'].append(dict(latest, value=1))
        self.assertEqual(context.reference_rows(req)[0]['available_count'], 1)

    def test_declared_reference_instruments_with_empty_source_remain_visible(self):
        req = request(indices=[])
        req['instruments'].extend(context.reference_instruments())
        rows = context.reference_rows(req)
        self.assertEqual([row['instrument_id'] for row in rows], ['TWSE.TAI50.TR', 'TWSE.TAIEX.TR'])
        for row in rows:
            self.assertEqual((row['available_count'], row['grid_count'], row['reason']),
                             (0, 2, 'NO_SUPPLIED_OBSERVATIONS'))
            for field in ('supplied_start', 'supplied_end', 'source_url'):
                self.assertIsNone(row[field])

    def test_source_only_reference_is_not_a_declared_research_instrument(self):
        req = request(indices=context.parse_index(*fixture('tai50'), 'index_tai50'))
        req['instruments'] = [row for row in req['instruments'] if row['asset_type'] != 'benchmark']
        self.assertEqual(context.reference_rows(req), [])

    def test_optional_context_absent_old_unsupported_and_malformed_are_safe(self):
        for value in (None, {}, [], 'old', {'schema_version': '9.0.0'},
                      {'schema_version': '1.0.0', 'nav_observations': None, 'index_observations': 'bad'}):
            req = request()
            req['adapter_lineage']['etf_context'] = value
            self.assertEqual(context.valuation_rows(req), [])
            self.assertEqual(context.reference_rows(req), [])
        req = request()
        req.pop('adapter_lineage')
        self.assertEqual(context.valuation_rows(req), [])
        self.assertEqual(context.reference_rows(req), [])

    def test_malformed_and_unrelated_context_rows_do_not_fabricate_instruments(self):
        req = request(nav=[{}, None, dict(nav_row(), instrument_id='UNRELATED.TW')],
                      indices=[None, {}, dict(observation(), instrument_id='UNRELATED.INDEX')])
        req['instruments'] = []
        self.assertEqual(context.valuation_rows(req), [])
        self.assertEqual(context.reference_rows(req), [])

    def test_valid_context_without_selected_nav_keeps_missing_fund_visible(self):
        req = request(nav=[])
        rows = context.valuation_rows(req)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['instrument_id'], '0050.TW')
        self.assertEqual(rows[0]['currency'], 'TWD')
        self.assertEqual(rows[0]['reason'], 'NAV_MISSING')
        for field in ('period', 'nav', 'close', 'premium_discount'):
            self.assertIsNone(rows[0][field])

    def test_temporarily_invalid_cutoff_marks_rows_unavailable_without_raising(self):
        req = request(indices=context.parse_index(*fixture('tai50'), 'index_tai50'))
        req['as_of'] = '2026-11-'
        self.assertEqual(context.valuation_rows(req)[0]['reason'], 'NAV_UNAVAILABLE_AS_OF')
        self.assertEqual(context.reference_rows(req)[0]['available_count'], 0)

    def test_malformed_instrument_fields_are_ignored(self):
        req = request()
        req['instruments'] = [None, {}, {'instrument_id': [], 'asset_type': 'etf'}]
        self.assertEqual(context.valuation_rows(req), [])


if __name__ == '__main__':
    unittest.main()
