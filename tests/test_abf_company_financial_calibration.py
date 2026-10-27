from copy import deepcopy
from datetime import datetime,timezone
import unittest
from unittest.mock import patch

import pandas as pd

from core.abf_company_survey import build_company_survey
from core.abf_financial_evidence import reconcile_financial_evidence
from tests import test_abf_financial_evidence as financial_fixtures
from tests.test_abf_company_survey import factor_row


class CompanyFinancialCalibrationTests(unittest.TestCase):
    cutoff='2026-10-26T06:00:00Z'

    def setUp(self):
        class ReportClock(datetime):
            @classmethod
            def now(cls,tz=None):
                value=cls(2026,10,26,6,tzinfo=timezone.utc)
                return value.astimezone(tz) if tz else value.replace(tzinfo=None)
        clock=patch('core.abf_company_survey.datetime',ReportClock)
        clock.start();self.addCleanup(clock.stop)

    def verified_panel(self):
        fixture=financial_fixtures.FinancialEvidenceTests()
        return reconcile_financial_evidence(fixture.panel(),
            {'contract':'ABFQuarterlyFinancialEvidenceV1','quarter_records':[fixture.record()]},as_of=self.cutoff)

    def test_company_financial_context_reports_verified_basis_and_actual_knowledge_bound(self):
        report=build_company_survey({},self.verified_panel(),[],as_of=self.cutoff)
        context=report['companies'][2]['financial_context']
        self.assertEqual(context['basis_coverage']['verified_standalone'],1)
        row=context['rows'][0]
        self.assertEqual(row['accounting_basis'],'STANDALONE_QUARTER')
        self.assertEqual(row['financial_value_verification'],'MATCH')
        self.assertEqual(row['available_at'],'2026-10-26T01:00:00+00:00')
        self.assertIn('nanyapcb.com.tw',row['primary_financial_source_url'])
        self.assertEqual(row['fundamental_source'],'FinMind')
        self.assertFalse(row['pit_exact'])

    def test_new_basis_proof_cannot_appear_in_an_earlier_report(self):
        report=build_company_survey({},self.verified_panel(),[],as_of='2026-10-25T00:00:00Z')
        self.assertEqual(report['companies'][2]['financial_context']['rows'],[])

    def test_verified_non_standalone_basis_cannot_promote_company_context(self):
        for basis in ('YTD','TTM','CONSOLIDATED_REPORTED'):
            with self.subTest(basis=basis):
                factor=pd.DataFrame([factor_row(accounting_basis=basis,accounting_basis_verified=True)])
                context=build_company_survey({},factor,[],as_of=self.cutoff)['companies'][0]['financial_context']
                self.assertEqual(context['rows'][0]['accounting_basis'],basis)
                self.assertTrue(context['rows'][0]['accounting_basis_verified'])
                self.assertEqual(context['basis_coverage']['verified_standalone'],0)
                self.assertEqual(context['basis_coverage']['unverified'],1)
                self.assertEqual(context['accounting_basis'],'UNKNOWN')

    def test_mixed_verified_basis_counts_only_standalone_quarters(self):
        factor=pd.DataFrame([
            factor_row(accounting_basis='STANDALONE_QUARTER',accounting_basis_verified=True),
            factor_row(report_date='2024-12-31',accounting_basis='YTD',accounting_basis_verified=True)])
        context=build_company_survey({},factor,[],as_of=self.cutoff)['companies'][0]['financial_context']
        self.assertEqual(context['basis_coverage']['verified_standalone'],1)
        self.assertEqual(context['basis_coverage']['unverified'],1)
        self.assertEqual(context['accounting_basis'],'PARTIALLY_VERIFIED')

    def test_company_preserves_primary_document_acquisition_separately_from_snapshot(self):
        row=build_company_survey({},self.verified_panel(),[],as_of=self.cutoff)['companies'][2]['financial_context']['rows'][0]
        self.assertEqual(row.get('financial_evidence_acquired_at'),'2026-10-26T01:00:00+00:00')

    def test_margin_handoff_retains_only_own_company_and_withholds_proxy_forecast(self):
        own=dict(comparison_id='margin-own',company='3037.TW',product='ABF',scenario='DOWNSIDE',
            feature='revenue_yoy',target='gross_margin_qoq',lag_quarters=1,
            descriptive_beta=0.5,forecast_beta=123.,evidence_status='ESTIMATED',
            is_proxy=True,source_scope='COMPANY_TOTAL',eligibility='eligible',sample_rows=[])
        other=deepcopy(own);other.update(company='8046.TW',comparison_id='margin-other')
        audit={'as_of':self.cutoff,'margin_validation':{'contract':'ABFMarginValidationV1',
            'as_of':self.cutoff,'comparisons':[own,other]}}
        report=build_company_survey(audit,pd.DataFrame(),[],as_of=self.cutoff)
        margin=report['companies'][0]['financial_bridge']['margin_audit']
        self.assertEqual([r['comparison_id'] for r in margin['comparisons']],['margin-own'])
        row=margin['comparisons'][0]
        self.assertEqual(row['descriptive_beta'],.5)
        self.assertIsNone(row['forecast_beta'])
        self.assertEqual(row['eligibility'],'reject')
        self.assertIsNone(report['companies'][0]['financial_bridge']['beta'])
        self.assertEqual(margin['data_status'],'UNAVAILABLE')


if __name__=='__main__':unittest.main()
