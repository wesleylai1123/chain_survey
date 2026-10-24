import importlib.util
import unittest

import pandas as pd


class MetricSemanticsTests(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('core.metric_semantics'), 'machine-readable semantics API missing')
        from core import metric_semantics
        return metric_semantics

    def test_yoy_identity_is_change_not_an_accounting_level(self):
        api = self.api()
        spec = api.metric_semantics('pcb_revenue_yoy')
        self.assertEqual(spec['measure_kind'], 'CHANGE')
        self.assertEqual(spec['change_basis'], 'YOY')
        self.assertEqual(spec['return_basis'], 'NOT_APPLICABLE')
        self.assertTrue(spec['is_proxy'])
        self.assertEqual(spec['accounting_basis'], 'INDUSTRY_AGGREGATE')

    def test_company_total_is_never_disclosed_abf_product_revenue(self):
        spec = self.api().metric_semantics('abf_company_revenue_yoy::3037.TW')
        self.assertEqual(spec['source_scope'], 'COMPANY_TOTAL')
        self.assertTrue(spec['is_proxy'])
        self.assertEqual(spec['product'], 'ABF')

    def test_unknown_metric_fails_closed(self):
        with self.assertRaises(ValueError):
            self.api().metric_semantics('invented_actual_eps')

    def test_missing_release_stays_null_and_timezone_is_required(self):
        api = self.api()
        frame = pd.DataFrame([dict(metric_id='pcb_revenue_yoy', period='2020-01', change_pct=10,
            published_at='2020-02-12T00:00:00+08:00', knowledge_time_method='regulatory_deadline_proxy',
            source_url='https://example.com/industry')])
        signals = api.normalize_history(frame, as_of='2021-01-01T00:00:00Z')
        signal = signals.iloc[0].to_dict()
        self.assertIsNone(signal['release_date'])
        self.assertEqual(signal['pit_basis'], 'PROXY')
        for key in ('available_at', 'observation_date', 'release_date', 'signal_generated_at'):
            self.assertIn(key, signal)
        with self.assertRaises(ValueError):
            api.normalize_history(frame, as_of='2021-01-01')

    def test_future_and_late_acquisition_are_excluded(self):
        api = self.api()
        rows = [dict(metric_id='pcb_revenue_yoy', period='2020-01', change_pct=10,
            published_at='2020-02-12T00:00:00Z', available_at='2022-01-01T00:00:00Z',
            knowledge_time_method='source_reported', source_url='https://example.com/industry')]
        self.assertTrue(api.normalize_history(pd.DataFrame(rows), as_of='2021-01-01T00:00:00Z').empty)

    def test_change_uses_adjacent_months_and_max_dependency_availability(self):
        api = self.api()
        rows = []
        for period, value, available in [('2020-01',10,'2020-04-01T00:00:00Z'),
                                          ('2020-02',13,'2020-03-10T00:00:00Z'),
                                          ('2020-04',20,'2020-05-10T00:00:00Z')]:
            rows.append(dict(metric_id='pcb_revenue_yoy',period=period,change_pct=value,
                published_at=available,knowledge_time_method='source_reported',source_url='https://example.com'))
        normalized = api.normalize_history(pd.DataFrame(rows), as_of='2021-01-01T00:00:00Z')
        changed = api.transform_observations(normalized, 'CHANGE')
        self.assertEqual(len(changed), 1)
        self.assertEqual(changed.iloc[0]['signal_value'], 3)
        self.assertEqual(changed.iloc[0]['available_at'], '2020-04-01T00:00:00+00:00')
        self.assertEqual(changed.iloc[0]['evidence_status'], 'DERIVED')
        self.assertEqual(len(changed.iloc[0]['dependency_ids']), 2)

    def test_conflicting_duplicate_cannot_multiply_samples(self):
        api = self.api()
        row = dict(metric_id='pcb_revenue_yoy',period='2020-01',change_pct=10,
            published_at='2020-02-12T00:00:00Z',knowledge_time_method='source_reported',source_url='https://example.com')
        with self.assertRaises(ValueError):
            api.normalize_history(pd.DataFrame([row,dict(row,change_pct=20)]),as_of='2021-01-01T00:00:00Z')

    def test_schema_rejects_noncanonical_evidence_and_incomplete_dates(self):
        api = self.api()
        with self.assertRaises(Exception):
            api.validate_signal({'evidence_status':'OBSERVED'})

    def test_accounting_and_return_bases_are_independent(self):
        api=self.api()
        self.assertEqual(api.financial_semantics('operating_cash_flow_ytd')['accounting_basis'],'YTD')
        self.assertEqual(api.financial_semantics('operating_cash_flow')['accounting_basis'],'STANDALONE_QUARTER')
        self.assertEqual(api.financial_semantics('future_3m_return')['return_basis'],'PRICE_RETURN')
        self.assertEqual(api.financial_semantics('future_3m_return')['accounting_basis'],'UNKNOWN')
        self.assertEqual(api.financial_semantics('gross_margin')['return_basis'],'NOT_APPLICABLE')

    def test_missing_values_do_not_crash_change_transform(self):
        api=self.api()
        rows=[dict(metric_id='pcb_revenue_yoy',period=p,change_pct=v,
            published_at=a,knowledge_time_method='source_reported',source_url='https://example.com')
            for p,v,a in [('2020-01',10,'2020-02-12T00:00:00Z'),
                           ('2020-02',None,'2020-03-12T00:00:00Z'),
                           ('2020-03',15,'2020-04-12T00:00:00Z')]]
        observations=api.normalize_history(pd.DataFrame(rows),as_of='2021-01-01T00:00:00Z')
        self.assertTrue(api.transform_observations(observations,'CHANGE').empty)

    def test_inferred_inputs_never_become_disclosed_or_derived_actuals(self):
        api=self.api()
        rows=[dict(metric_id='pcb_revenue_yoy',period=p,change_pct=v,
            published_at=a,knowledge_time_method='source_reported',source_url='https://example.com',evidence_status='INFERRED')
            for p,v,a in [('2020-01',10,'2020-02-12T00:00:00Z'),('2020-02',15,'2020-03-12T00:00:00Z')]]
        observations=api.normalize_history(pd.DataFrame(rows),as_of='2021-01-01T00:00:00Z')
        self.assertEqual(set(observations.evidence_status),{'INFERRED'})
        self.assertEqual(set(api.transform_observations(observations,'CHANGE').evidence_status),{'INFERRED'})

    def test_schema_rejects_missing_individual_times_and_false_proxy_scope(self):
        import json
        from pathlib import Path
        api=self.api()
        fixture=json.loads((Path(__file__).resolve().parents[1]/'contracts/metric-semantics/v1/examples/valid.json').read_text())
        api.validate_signal(fixture)
        for field in ('observation_date','release_date','available_at','signal_generated_at'):
            invalid=dict(fixture)
            del invalid[field]
            with self.assertRaises(Exception):
                api.validate_signal(invalid)
        with self.assertRaises(Exception):
            api.validate_signal(dict(fixture,is_proxy=False))


if __name__ == '__main__':
    unittest.main()
