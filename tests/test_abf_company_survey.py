"""Company reports preserve audited evidence and conservative knowledge times."""
from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import unittest

import numpy as np
import pandas as pd


AS_OF = '2025-06-30T15:59:59+00:00'
COMPANIES = ('3037.TW', '3189.TW', '8046.TW')


def audit_fixture():
    details = {}
    for company in COMPANIES:
        for scenario in ('UPSIDE', 'DOWNSIDE'):
            for ft in ('LEVEL', 'CHANGE'):
                for tt in ('LEVEL', 'CHANGE'):
                    cid = f'{scenario}|pcb_revenue_yoy|{company}|{ft}|{tt}|1'
                    sample = dict(period='2025-01', x=3.0 if scenario == 'UPSIDE' else -2.0,
                        y=4.0 if scenario == 'UPSIDE' else -1.0,
                        observation_date='2025-01-31T00:00:00+08:00',
                        release_date=None, available_at='2025-02-12T15:59:59+00:00',
                        signal_generated_at='2025-06-20T00:00:00+00:00',
                        feature_available_at='2025-02-12T15:59:59+00:00',
                        target_available_at='2025-03-10T15:59:59+00:00',
                        target_observation_date='2025-02-28T00:00:00+08:00',
                        target_release_date=None, dependency_ids=['industry-jan', company+'-feb'],
                        source_urls=['https://example.com/industry', 'https://example.com/'+company],
                        source_lineage_complete=True, pit_exact=False, is_proxy=True)
                    details[cid] = dict(comparison_id=cid, company=company, product='ABF',
                        scenario=scenario, metric_id='pcb_revenue_yoy',
                        target_metric='abf_company_revenue_yoy::'+company,
                        feature_transform=ft, target_transform=tt, lag_months=1,
                        timing_class='LEADING', source_scope='INDUSTRY_AGGREGATE',
                        target_scope='COMPANY_TOTAL', is_proxy=True,
                        feature_unit='percent' if ft == 'LEVEL' else 'percentage_points',
                        target_unit='percent' if tt == 'LEVEL' else 'percentage_points',
                        evidence_status='DERIVED', data_status='AVAILABLE',
                        sample_size=1, spearman=.6 if scenario == 'UPSIDE' else -.4,
                        bootstrap_ci_low=-.2, bootstrap_ci_high=.9, permutation_p=.2,
                        fdr_q=.4, eligibility='reject', source_lineage_complete=True,
                        pit_exact=False, gates={'sample_size': False},
                        oos_folds=[dict(train_size=0, test_size=1, test_spearman=None,
                            first_test_period='2025-01', last_test_period='2025-01')],
                        sample_rows=[sample], source_urls=sample['source_urls'])
    observations = []
    for company in ('INDUSTRY', *COMPANIES):
        for transform in ('LEVEL', 'CHANGE'):
            observations.append(dict(observation_id=company+'-'+transform, company=company,
                product='ABF', metric_id='pcb_revenue_yoy' if company == 'INDUSTRY'
                else 'abf_company_revenue_yoy::'+company,
                period='2025-01', transform=transform, signal_value=3.0,
                unit='percent' if transform == 'LEVEL' else 'percentage_points',
                source_scope='INDUSTRY_AGGREGATE' if company == 'INDUSTRY' else 'COMPANY_TOTAL',
                source_product='PCB' if company == 'INDUSTRY' else 'All company products',
                is_proxy=True, evidence_status='DERIVED', pit_basis='PROXY',
                observation_date='2025-01-31T00:00:00+08:00', release_date=None,
                available_at='2025-02-12T15:59:59+00:00',
                signal_generated_at='2025-06-20T00:00:00+00:00',
                source_urls=['https://example.com/'+company], dependency_ids=[company+'-jan']))
    return dict(contract='ABFSemanticsValidationV1', owner='chain_survey',
        as_of='2025-06-20T00:00:00+00:00', generated_at='2025-06-20T01:00:00+00:00',
        policy={'lag_months': 1, 'transform_selection': 'NONE_PREDECLARED_2x2'},
        comparisons=[{k: v for k, v in d.items() if k not in {'sample_rows', 'oos_folds', 'gates'}}
                     for d in details.values()], details=details, observations=observations,
        calibration_handoff=[dict(company=c, product='ABF', stages=[
            dict(stage='Revenue → GM', status='CANDIDATE_ONLY', beta=None)]) for c in COMPANIES],
        downside_source_priorities=[])


def factor_row(**changes):
    row = dict(ticker='3037.TW', report_date='2025-03-31', available_date='2025-05-15',
        filing_published_at='2025-05-14T18:00:00+08:00',
        filing_source_url='https://doc.twse.com.tw/example.pdf',
        filing_document_name='202501_3037_AI1.pdf', acquired_at='2025-05-16T12:00:00+08:00',
        gross_margin=.248, revenue=1000000.0, revenue_yoy=.12, eps=0.0)
    row.update(changes)
    return row


def fact_row(**changes):
    row = dict(fact_id='3037-backlog', stock_id='3037', product='ABF',
        metric_id='abf_orders_backlog', value=0, unit='months', statement='Disclosed backlog.',
        source_url='https://www.unimicron.com/investor.pdf',
        document='Investor presentation', page=4, evidence_status='DISCLOSED',
        source_scope='COMPANY_PRODUCT', is_proxy=False, accounting_basis='NOT_APPLICABLE',
        observation_date='2025-03-31T00:00:00+08:00',
        release_date='2025-05-14T15:00:00+08:00', available_at='2025-05-14T15:00:00+08:00',
        acquired_at='2025-05-16T12:00:00+08:00',
        signal_generated_at='2025-05-17T00:00:00+08:00')
    row.update(changes)
    return row


class AbfCompanySurveyTests(unittest.TestCase):
    def build(self, audit=None, factor=None, facts=None, as_of=AS_OF):
        self.assertIsNotNone(importlib.util.find_spec('core.abf_company_survey'),
                             'ABF company survey builder is missing')
        from core.abf_company_survey import build_company_survey
        return build_company_survey(audit_fixture() if audit is None else audit,
            pd.DataFrame() if factor is None else factor, [] if facts is None else facts, as_of=as_of)

    def test_contract_always_has_three_company_product_records_and_true_generation_time(self):
        before = datetime.now(timezone.utc)
        report = self.build(audit={})
        after = datetime.now(timezone.utc)
        self.assertEqual(report['contract'], 'ABFCompanySurveyV1')
        self.assertEqual(report['owner'], 'chain_survey')
        self.assertEqual(report['as_of'], AS_OF)
        self.assertLessEqual(before, datetime.fromisoformat(report['generated_at']))
        self.assertLessEqual(datetime.fromisoformat(report['generated_at']), after)
        self.assertEqual([(r['company'], r['name'], r['product']) for r in report['companies']],
                         [('3037.TW', '欣興', 'ABF'), ('3189.TW', '景碩', 'ABF'), ('8046.TW', '南電', 'ABF')])
        for record in report['companies']:
            self.assertEqual(record['data_status'], 'UNAVAILABLE')
            self.assertEqual(record['scenario_options'], ['UPSIDE', 'DOWNSIDE'])
            self.assertEqual(len(record['details']), 40)
            self.assertEqual(record['financial_context']['rows'], [])
            self.assertEqual(record['financial_bridge']['status'], 'NOT_CALIBRATED')
            self.assertIsNone(record['financial_bridge']['beta'])

    def test_scenarios_keep_own_exact_audit_evidence_and_all_predeclared_choices(self):
        audit = audit_fixture()
        original = deepcopy(audit)
        report = self.build(audit=audit)
        for record in report['companies']:
            for scenario in record['scenario_options']:
                options = record['scenarios'][scenario]['options']
                self.assertEqual(len(options), 20)
                self.assertEqual({(o['feature_transform'], o['target_transform']) for o in options},
                                 {('LEVEL', 'LEVEL'), ('LEVEL', 'CHANGE'), ('CHANGE', 'LEVEL'), ('CHANGE', 'CHANGE')})
                self.assertTrue(all(record['details'][o['comparison_id']]['scenario'] == scenario for o in options))
            for cid, source in audit['details'].items():
                if source['company'] == record['company']:
                    self.assertEqual(record['details'][cid], source)
                    self.assertIsNot(record['details'][cid], source)
                    self.assertIsNot(record['details'][cid]['sample_rows'], source['sample_rows'])
            self.assertTrue(all(d['company'] == record['company'] for d in record['details'].values()))
        self.assertEqual(audit, original)

    def test_trend_uses_only_level_observations_for_industry_and_own_company(self):
        audit = audit_fixture()
        for record in self.build(audit=audit)['companies']:
            expected = [o for o in audit['observations'] if o['transform'] == 'LEVEL'
                        and o['company'] in {'INDUSTRY', record['company']}]
            self.assertEqual(record['trend']['observations'], expected)
            self.assertTrue(all(o['is_proxy'] for o in record['trend']['observations']))

    def test_financial_context_preserves_fraction_units_unknown_basis_and_four_dates(self):
        record = self.build(factor=pd.DataFrame([factor_row(accounting_basis='STANDALONE_QUARTER')]))['companies'][0]
        row = record['financial_context']['rows'][0]
        self.assertEqual(row['gross_margin'], .248)
        self.assertEqual(row['revenue_yoy'], .12)
        self.assertEqual(row['eps'], 0)
        self.assertEqual(row['units']['gross_margin'], 'ratio')
        self.assertEqual(row['units']['revenue_yoy'], 'ratio')
        self.assertEqual(row['source_scope'], 'COMPANY_TOTAL')
        self.assertEqual(row['source_product'], 'All company products')
        self.assertTrue(row['is_proxy'])
        self.assertEqual(row['accounting_basis'], 'UNKNOWN')
        self.assertEqual(row['release_date'], '2025-05-14T10:00:00+00:00')
        self.assertEqual(row['available_at'], '2025-05-16T04:00:00+00:00')
        for field in ('observation_date', 'release_date', 'available_at', 'signal_generated_at'):
            self.assertIn(field, row)
        self.assertEqual(row['source_urls'], ['https://doc.twse.com.tw/example.pdf'])

    def test_financial_value_provider_is_separate_from_filing_time_verification(self):
        provider_url = 'https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockFinancialStatements&data_id=3037'
        raw = factor_row(fundamental_source='FinMind', fundamental_source_url=provider_url,
                         market_source='TWSE')
        row = self.build(factor=pd.DataFrame([raw]))['companies'][0]['financial_context']['rows'][0]
        self.assertEqual(row.get('fundamental_source'), 'FinMind')
        self.assertEqual(row['market_source'], 'TWSE')
        self.assertEqual(row['value_source_urls'], [provider_url])
        self.assertEqual(row['filing_source_url'], raw['filing_source_url'])
        self.assertEqual(row['filing_source_role'], 'PUBLICATION_TIME_VERIFICATION')
        self.assertIn(provider_url, row['source_urls'])

    def test_financial_dataframe_date_objects_keep_taiwan_end_of_day_rule(self):
        raw = factor_row(report_date=pd.Timestamp('2025-03-31'),
                         available_date=pd.Timestamp('2025-05-15'), acquired_at=None)
        try:
            report = self.build(factor=pd.DataFrame([raw]), as_of='2025-05-15T16:00:00Z')
        except ValueError as exc:
            self.fail(f'Financial date columns should accept pandas dates: {exc}')
        row = report['companies'][0]['financial_context']['rows'][0]
        self.assertEqual(row['available_at'], '2025-05-15T15:59:59+00:00')

    def test_date_only_availability_is_taiwan_end_of_day_and_acquisition_caps_replay(self):
        raw = factor_row(acquired_at=None)
        frame = pd.DataFrame([raw])
        self.assertEqual(self.build(factor=frame, as_of='2025-05-15T08:00:00Z')['companies'][0]['financial_context']['rows'], [])
        row = self.build(factor=frame, as_of='2025-05-15T16:00:00Z')['companies'][0]['financial_context']['rows'][0]
        self.assertTrue(row['available_at'].startswith('2025-05-15T15:59:59'))
        self.assertFalse(row['pit_exact'])
        self.assertIsNone(row['acquired_at'])
        future = pd.DataFrame([factor_row(acquired_at='2025-07-01T00:00:00Z')])
        self.assertEqual(self.build(factor=future)['companies'][0]['financial_context']['rows'], [])

    def test_financial_history_respects_later_release_and_stock_id_without_ticker(self):
        raw = factor_row(stock_id='3189', release_date='2025-07-01T00:00:00Z')
        raw.pop('ticker')
        report = self.build(factor=pd.DataFrame([raw]))
        self.assertEqual(report['companies'][1]['financial_context']['rows'], [])
        raw['release_date'] = None
        row = self.build(factor=pd.DataFrame([raw]))['companies'][1]['financial_context']['rows'][0]
        self.assertEqual(row['company'], '3189.TW')
        self.assertEqual(row['accounting_basis'], 'UNKNOWN')

    def test_verified_financial_basis_needs_explicit_verification(self):
        row = self.build(factor=pd.DataFrame([factor_row(accounting_basis='STANDALONE_QUARTER',
                            accounting_basis_verified=True)]))['companies'][0]['financial_context']['rows'][0]
        self.assertEqual(row['accounting_basis'], 'STANDALONE_QUARTER')

    def test_primary_facts_zero_is_valid_and_availability_includes_acquisition(self):
        fact = self.build(facts={'facts': [fact_row()]})['companies'][0]['primary_facts'][0]
        self.assertEqual(fact['value'], 0)
        self.assertEqual(fact['company'], '3037.TW')
        self.assertEqual(fact['available_at'], '2025-05-16T04:00:00+00:00')
        self.assertTrue(fact['pit_exact'])
        self.assertTrue(fact['source_lineage_complete'])
        self.assertEqual(fact['evidence_status'], 'DISCLOSED')

    def test_all_company_product_facts_cannot_become_abf_actuals(self):
        fact = self.build(facts=[fact_row(product='All company products', source_scope='COMPANY_PRODUCT',
                             is_proxy=False)])['companies'][0]['primary_facts'][0]
        self.assertEqual(fact['product'], 'All company products')
        self.assertEqual(fact['source_scope'], 'COMPANY_TOTAL')
        self.assertTrue(fact['is_proxy'])

    def test_missing_release_stays_null_and_missing_metadata_never_implies_exactness(self):
        facts = [fact_row(release_date=None), fact_row(fact_id='unknown-first-seen', acquired_at=None)]
        raw = factor_row(filing_published_at=None, acquired_at=None, filing_source_url=None)
        company = self.build(factor=pd.DataFrame([raw]), facts=facts)['companies'][0]
        self.assertIsNone(company['primary_facts'][0]['release_date'])
        self.assertFalse(company['primary_facts'][0]['pit_exact'])
        self.assertFalse(company['primary_facts'][1]['pit_exact'])
        self.assertIsNone(company['primary_facts'][1]['acquired_at'])
        row = company['financial_context']['rows'][0]
        self.assertIsNone(row['release_date'])
        self.assertFalse(row['pit_exact'])
        self.assertFalse(row['source_lineage_complete'])
        self.assertEqual(row['evidence_status'], 'UNKNOWN')

    def test_future_or_untraceable_facts_are_excluded_with_visible_reasons(self):
        facts = [fact_row(acquired_at='2025-07-01T00:00:00Z', signal_generated_at='2025-07-02T00:00:00Z'),
                 fact_row(fact_id='no-source', source_url=''),
                 fact_row(fact_id='future-observation', observation_date='2025-08-01T00:00:00Z',
                          release_date='2025-08-02T00:00:00Z', available_at='2025-08-02T00:00:00Z',
                          acquired_at='2025-08-03T00:00:00Z', signal_generated_at='2025-08-04T00:00:00Z')]
        company = self.build(facts=facts)['companies'][0]
        self.assertEqual(company['primary_facts'], [])
        self.assertEqual({r['fact_id'] for r in company['rejected_facts']},
                         {'3037-backlog', 'no-source', 'future-observation'})

    def test_conflicting_fact_ids_and_invalid_status_or_dates_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Conflicting.*fact'):
            self.build(facts=[fact_row(), fact_row(value=2)])
        with self.assertRaisesRegex(ValueError, 'evidence status'):
            self.build(facts=[fact_row(evidence_status='VERIFIED')])
        with self.assertRaisesRegex(ValueError, 'date|timestamp'):
            self.build(facts=[fact_row(release_date='not-a-date')])
        with self.assertRaisesRegex(ValueError, 'observation|release'):
            self.build(facts=[fact_row(release_date='2025-01-01T00:00:00Z')])

    def test_nan_is_null_and_missing_abf_operating_inputs_remain_explicit(self):
        report = self.build(factor=pd.DataFrame([factor_row(eps=np.nan)]),
                            facts=[fact_row(value=np.nan, statement='Qualitative evidence only.')])
        company = report['companies'][0]
        self.assertIsNone(company['financial_context']['rows'][0]['eps'])
        self.assertIsNone(company['primary_facts'][0]['value'])
        missing = {r['metric_id']: r for r in company['missing_inputs']}
        for metric in ('abf_customer_inventory', 'abf_utilization', 'abf_pricing', 'abf_product_mix'):
            self.assertIsNone(missing[metric]['value'])
            self.assertEqual(missing[metric]['evidence_status'], 'UNKNOWN')
        json.dumps(report, allow_nan=False, ensure_ascii=False)

    def test_research_assessment_and_invalidation_reference_company_evidence(self):
        company = self.build(facts=[fact_row()])['companies'][0]
        ids = set(company['details']) | {f['fact_id'] for f in company['primary_facts']}
        self.assertTrue(company['assessment']['evidence_ids'])
        for item in [company['assessment'], *company['research_questions'], *company['invalidation_conditions']]:
            self.assertTrue(item['evidence_ids'])
            self.assertTrue(set(item['evidence_ids']) <= ids)
        self.assertEqual(company['financial_bridge']['status'], 'NOT_CALIBRATED')
        self.assertIsNone(company['financial_bridge']['beta'])

    def test_audit_after_cutoff_is_unavailable_instead_of_reusing_future_statistics(self):
        audit = audit_fixture()
        audit['as_of'] = '2025-07-01T00:00:00Z'
        company = self.build(audit=audit)['companies'][0]
        self.assertEqual(company['trend']['observations'], [])
        self.assertTrue(all(d['sample_rows'] == [] and d['spearman'] is None
                            and d['data_status'] == 'UNAVAILABLE' for d in company['details'].values()))

    def test_missing_sample_lineage_cannot_retain_audit_eligibility(self):
        audit = audit_fixture()
        cid = next(iter(audit['details']))
        detail = audit['details'][cid]
        detail['eligibility'] = 'eligible'
        detail['pit_exact'] = True
        detail['source_lineage_complete'] = True
        detail['sample_rows'][0]['source_urls'] = []
        detail['sample_rows'][0].pop('available_at')
        copied = self.build(audit=audit)['companies'][0]['details'][cid]
        self.assertFalse(copied['source_lineage_complete'])
        self.assertFalse(copied['pit_exact'])
        self.assertEqual(copied['data_status'], 'UNAVAILABLE')
        self.assertEqual(copied['eligibility'], 'reject')

    def test_future_sample_cannot_keep_full_sample_statistics_after_row_filtering(self):
        audit = audit_fixture()
        cid = next(iter(audit['details']))
        audit['details'][cid]['sample_rows'][0]['target_available_at'] = '2025-07-01T00:00:00Z'
        copied = self.build(audit=audit)['companies'][0]['details'][cid]
        self.assertEqual(copied['sample_rows'], [])
        self.assertIsNone(copied['spearman'])
        self.assertEqual(copied['sample_size'], 0)

    def test_invalid_observation_release_and_acquisition_order_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'acquisition|acquired'):
            self.build(facts=[fact_row(acquired_at='2025-01-01T00:00:00Z')])
        with self.assertRaisesRegex(ValueError, 'signal_generated_at'):
            self.build(facts=[fact_row(signal_generated_at='2025-04-01T00:00:00Z')])

    def test_audit_observation_release_date_is_validated(self):
        audit = audit_fixture()
        audit['observations'][0]['release_date'] = 'not-a-date'
        with self.assertRaisesRegex(ValueError, 'date|timestamp'):
            self.build(audit=audit)

    def test_research_summary_includes_objective_primary_statements_without_a_beta(self):
        statement = 'ABF sales were 52% of company revenue in 2026 Q2.'
        company = self.build(facts=[fact_row(statement=statement)])['companies'][0]
        self.assertIn(statement, company['assessment']['summary'])
        self.assertEqual(company['assessment']['fact_summary'][0]['fact_id'], '3037-backlog')
        self.assertIsNone(company['financial_bridge']['beta'])

    def test_timezone_aware_eod_proxy_release_is_never_exact(self):
        for metadata in ({'release_time_basis': 'DATE_ONLY'}, {'release_time_basis': 'MONTH_ONLY'},
                         {'pit_basis': 'PROXY'}, {'knowledge_time_method': 'regulatory_deadline_proxy'},
                         {'time_basis': 'Conference date only; no intraday time; Taiwan EOD proxy.'}):
            with self.subTest(metadata=metadata):
                raw = fact_row(release_date='2025-05-14T23:59:59+08:00', **metadata)
                fact = self.build(facts=[raw])['companies'][0]['primary_facts'][0]
                self.assertFalse(fact['pit_exact'])

    def test_operating_input_uses_latest_economic_period_when_acquisition_ties(self):
        older = fact_row(fact_id='mix-old', metric_id='abf_product_mix', value=46)
        latest = fact_row(fact_id='mix-new', metric_id='abf_product_mix', value=52,
                          observation_date='2025-04-30T00:00:00+08:00')
        company = self.build(facts=[older, latest])['companies'][0]
        mix = next(r for r in company['missing_inputs'] if r['metric_id'] == 'abf_product_mix')
        self.assertEqual(mix['value'], 52)
        self.assertEqual(mix['evidence_ids'], ['mix-new'])

    def test_calculation_dependencies_are_retained_and_bound_derived_availability(self):
        source = fact_row(fact_id='source', acquired_at='2025-05-18T00:00:00Z',
                          signal_generated_at='2025-05-19T00:00:00Z')
        derived = fact_row(fact_id='derived', evidence_status='DERIVED', value=2,
            calculation={'formula': 'source * 2', 'dependencies': ['source']},
            signal_generated_at='2025-05-20T00:00:00Z')
        facts = self.build(facts=[derived, source])['companies'][0]['primary_facts']
        result = next(f for f in facts if f['fact_id'] == 'derived')
        self.assertEqual(result['dependency_ids'], ['source'])
        self.assertEqual(result['available_at'], '2025-05-18T00:00:00+00:00')
        self.assertEqual(result['acquired_at'], '2025-05-18T00:00:00+00:00')

    def test_missing_or_future_dependency_excludes_derived_fact(self):
        derived = fact_row(fact_id='derived', evidence_status='DERIVED',
            calculation={'formula': 'source * 2', 'dependencies': ['source']})
        for facts in ([derived], [derived, fact_row(fact_id='source',
                acquired_at='2025-07-01T00:00:00Z', signal_generated_at='2025-07-02T00:00:00Z')]):
            with self.subTest(facts=len(facts)):
                company = self.build(facts=facts)['companies'][0]
                self.assertEqual(company['primary_facts'], [])
                rejected = next(f for f in company['rejected_facts'] if f['fact_id'] == 'derived')
                self.assertEqual(rejected['reason'], 'DEPENDENCY_UNAVAILABLE')

    def test_reviewed_production_facts_conform_without_promoting_mixed_substrates(self):
        path = Path(__file__).resolve().parents[1]/'data/abf_company_research_evidence.json'
        if not path.exists():
            self.skipTest('Optional reviewed evidence has not been populated yet')
        facts = json.loads(path.read_text(encoding='utf-8'))
        now = datetime.now(timezone.utc).isoformat()
        report = self.build(facts=facts, as_of=now)
        accepted = [f for c in report['companies'] for f in c['primary_facts']]
        self.assertEqual(len(accepted), len(facts))
        self.assertEqual(report['rejected_facts'], [])
        for fact in accepted:
            self.assertIn(fact['product'], {'ABF', 'All company products'})
            self.assertLessEqual(pd.Timestamp(fact['available_at']), pd.Timestamp(now))
            if fact.get('calculation'):
                self.assertEqual(fact['dependency_ids'], fact['calculation']['dependencies'])
            if fact.get('source_product', '').startswith('IC substrates'):
                self.assertEqual(fact['source_scope'], 'COMPANY_TOTAL')
                self.assertTrue(fact['is_proxy'])
            if fact.get('time_basis') and 'proxy' in fact['time_basis'].lower():
                self.assertFalse(fact['pit_exact'])
        json.dumps(report, allow_nan=False)

    def test_late_sample_first_seen_or_snapshot_excludes_the_whole_comparison(self):
        for field in ('first_seen_at', 'snapshot_acquired_at'):
            with self.subTest(field=field):
                audit = audit_fixture()
                cid = next(iter(audit['details']))
                audit['details'][cid]['sample_rows'][0][field] = '2025-07-01T00:00:00Z'
                detail = self.build(audit=audit)['companies'][0]['details'][cid]
                self.assertEqual(detail['sample_rows'], [])
                self.assertIsNone(detail['spearman'])
                self.assertEqual(detail['data_status'], 'UNAVAILABLE')

    def test_later_acquisition_than_audited_availability_requires_revalidation(self):
        for field in ('acquired_at', 'first_seen_at', 'snapshot_acquired_at'):
            with self.subTest(field=field):
                audit = audit_fixture()
                cid = next(iter(audit['details']))
                audit['details'][cid]['sample_rows'][0][field] = '2025-05-01T00:00:00Z'
                detail = self.build(audit=audit)['companies'][0]['details'][cid]
                self.assertEqual(detail['sample_rows'], [])
                self.assertIsNone(detail['spearman'])
                self.assertIn('AUDIT_REQUIRES_REVALIDATION', detail['reasons'])

    def test_trend_acquisition_aliases_cap_availability_and_exclude_future_rows(self):
        for field in ('acquired_at', 'first_seen_at', 'snapshot_acquired_at'):
            with self.subTest(field=field):
                audit = audit_fixture()
                observation = audit['observations'][0]
                observation[field] = '2025-05-20T00:00:00Z'
                company = self.build(audit=audit)['companies'][0]
                result = next(o for o in company['trend']['observations']
                              if o['observation_id'] == observation['observation_id'])
                self.assertEqual(result['available_at'], '2025-05-20T00:00:00+00:00')
                observation[field] = '2025-07-01T00:00:00Z'
                try:
                    company = self.build(audit=audit)['companies'][0]
                except ValueError as exc:
                    self.fail(f'Future-acquired trend evidence must be excluded from replay: {exc}')
                self.assertNotIn(observation['observation_id'],
                                 {o['observation_id'] for o in company['trend']['observations']})

    def test_derived_fact_requires_nonself_inputs_even_without_calculation_metadata(self):
        for dependencies in (None, [], ['derived']):
            with self.subTest(dependencies=dependencies):
                raw = fact_row(fact_id='derived', evidence_status='DERIVED')
                if dependencies is not None:
                    raw['dependency_ids'] = dependencies
                company = self.build(facts=[raw])['companies'][0]
                self.assertEqual(company['primary_facts'], [])
                self.assertEqual(company['rejected_facts'][0]['reason'], 'DEPENDENCY_UNAVAILABLE')

    def test_arithmetic_propagates_unknown_estimated_or_inferred_input_status(self):
        for status in ('UNKNOWN', 'ESTIMATED', 'INFERRED'):
            with self.subTest(status=status):
                source = fact_row(fact_id='source', evidence_status=status, value=3)
                derived = fact_row(fact_id='derived', evidence_status='DERIVED', value=6,
                    calculation={'formula': 'source * 2', 'dependencies': ['source']})
                facts = self.build(facts=[source, derived])['companies'][0]['primary_facts']
                result = next(f for f in facts if f['fact_id'] == 'derived')
                self.assertEqual(result['evidence_status'], status)
                self.assertFalse(result['usable'])

    def test_null_qualitative_input_cannot_support_computed_numeric_fact(self):
        source = fact_row(fact_id='source', value=None, statement='Management qualitative statement.')
        derived = fact_row(fact_id='derived', evidence_status='DERIVED', value=6,
            calculation={'formula': 'source * 2', 'dependencies': ['source']})
        company = self.build(facts=[source, derived])['companies'][0]
        self.assertEqual([f['fact_id'] for f in company['primary_facts']], ['source'])
        self.assertEqual(company['rejected_facts'][0]['reason'], 'DEPENDENCY_VALUE_UNAVAILABLE')

    def test_eligible_audit_with_proxy_nonexact_or_incomplete_source_requires_revalidation(self):
        for invalid_field in ('is_proxy', 'pit_exact', 'source_lineage_complete', 'missing_release'):
            with self.subTest(invalid_field=invalid_field):
                audit = audit_fixture()
                cid = next(iter(audit['details']))
                source = audit['details'][cid]
                source.update(eligibility='eligible', is_proxy=False, pit_exact=True,
                              source_lineage_complete=True)
                sample = source['sample_rows'][0]
                sample.update(is_proxy=False, pit_exact=True,
                              release_date='2025-02-12T00:00:00Z',
                              target_release_date='2025-03-10T00:00:00Z')
                if invalid_field == 'missing_release':
                    sample['release_date'] = None
                else:
                    source[invalid_field] = invalid_field == 'is_proxy'
                detail = self.build(audit=audit)['companies'][0]['details'][cid]
                self.assertEqual(detail['eligibility'], 'reject')
                self.assertEqual(detail['data_status'], 'UNAVAILABLE')
                self.assertEqual(detail['sample_rows'], [])
                self.assertIn('AUDIT_REQUIRES_REVALIDATION', detail['reasons'])

    def test_derived_product_claim_inherits_company_total_input_scope_and_proxy(self):
        source = fact_row(fact_id='source', product='All company products',
                          source_scope='COMPANY_TOTAL', is_proxy=True, value=3)
        derived = fact_row(fact_id='derived', evidence_status='DERIVED', value=6,
            calculation={'formula': 'source * 2', 'dependencies': ['source']})
        facts = self.build(facts=[source, derived])['companies'][0]['primary_facts']
        result = next(f for f in facts if f['fact_id'] == 'derived')
        self.assertTrue(result['is_proxy'])
        self.assertEqual(result['source_scope'], 'COMPANY_TOTAL')
        self.assertEqual(result['source_product'], 'All company products')

    def test_other_company_input_cannot_become_own_company_product_actual(self):
        source = fact_row(fact_id='source', stock_id='3189', value=3)
        derived = fact_row(fact_id='derived', evidence_status='DERIVED', value=6,
            calculation={'formula': 'source * 2', 'dependencies': ['source']})
        company = self.build(facts=[source, derived])['companies'][0]
        self.assertEqual(company['primary_facts'], [])
        self.assertEqual(company['rejected_facts'][0]['reason'], 'DEPENDENCY_COMPANY_MISMATCH')

    def test_disclosed_numeric_guidance_cannot_fill_operating_actuals(self):
        for kind in ('GUIDANCE', 'FORWARD_LOOKING', 'FORECAST', 'ESTIMATE'):
            with self.subTest(kind=kind):
                guidance = fact_row(fact_id='guidance', metric_id='abf_utilization',
                                    value=92, measure_kind=kind)
                company = self.build(facts=[guidance])['companies'][0]
                fact = company['primary_facts'][0]
                self.assertEqual(fact['measure_kind'], kind)
                self.assertFalse(fact['usable'])
                utilization = next(r for r in company['missing_inputs'] if r['metric_id'] == 'abf_utilization')
                self.assertIsNone(utilization['value'])

    def test_calculation_of_guidance_stays_forward_looking_and_unusable_as_actual(self):
        guidance = fact_row(fact_id='guidance', value=3, measure_kind='GUIDANCE')
        derived = fact_row(fact_id='derived', evidence_status='DERIVED', value=6,
            measure_kind='CALCULATION', calculation={'formula': 'guidance * 2', 'dependencies': ['guidance']})
        facts = self.build(facts=[guidance, derived])['companies'][0]['primary_facts']
        result = next(f for f in facts if f['fact_id'] == 'derived')
        self.assertTrue(result.get('is_forward_looking'))
        self.assertFalse(result['usable'])

    def test_forward_looking_validation_status_cannot_be_overridden_by_observation_kind(self):
        for kind in (None, 'OBSERVATION'):
            with self.subTest(kind=kind):
                raw = fact_row(metric_id='abf_utilization', value=90,
                    validation_status='FORWARD_LOOKING', measure_kind=kind)
                company = self.build(facts=[raw])['companies'][0]
                self.assertTrue(company['primary_facts'][0]['is_forward_looking'])
                self.assertFalse(company['primary_facts'][0]['usable'])
                utilization = next(r for r in company['missing_inputs'] if r['metric_id'] == 'abf_utilization')
                self.assertIsNone(utilization['value'])


if __name__ == '__main__':
    unittest.main()
