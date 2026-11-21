from __future__ import annotations

import copy
import unittest

import pandas as pd

from core import abf_financial_evidence as financial


class FinancialEvidenceTests(unittest.TestCase):
    cutoff = '2026-10-26T06:00:00Z'

    def panel(self):
        return pd.DataFrame([dict(ticker='8046.TW', report_date='2026-06-30',
            revenue=13575475000., gross_profit=3359610000., gross_margin=3359610/13575475,
            available_date='2026-08-07', snapshot_acquired_at='2026-10-24T08:00:00Z',
            fundamental_source='FinMind', fundamental_source_url='https://api.finmindtrade.com/api/v4/data')])

    def record(self):
        return dict(evidence_id='8046-2026Q2-primary',company='8046.TW',product='ABF',
            period_start='2026-04-01',period_end='2026-06-30',revenue=13575475,gross_profit=3359610,
            unit='TWD thousand',published_decimal_places=0,
            accounting_basis='STANDALONE_QUARTER',consolidation='CONSOLIDATED',source_scope='COMPANY_TOTAL',
            evidence_status='DISCLOSED',source_url='https://www.nanyapcb.com.tw/nypcb/images/InvestorRelations/FinancialReport/115Q2ENG(Consolidated).pdf',
            source_document='2026 Q2 consolidated statements',source_page=6,source_excerpt='Three months ended June 30, 2026',
            release_date=None,acquired_at='2026-10-26T01:00:00Z',available_at='2026-10-26T01:00:00Z',
            source_sha256='a'*64)

    def reconcile(self, record=None, panel=None):
        fn=getattr(financial,'reconcile_financial_evidence',None)
        self.assertIsNotNone(fn,'financial accounting basis requires primary-document reconciliation')
        return fn(self.panel() if panel is None else panel,
            {'contract':'ABFQuarterlyFinancialEvidenceV1','quarter_records':[self.record() if record is None else record]},
            as_of=self.cutoff)

    def test_matching_quarter_verifies_basis_but_preserves_value_provider_and_missing_release(self):
        row=self.reconcile().iloc[0]
        self.assertEqual(row.accounting_basis,'STANDALONE_QUARTER')
        self.assertEqual(row.financial_value_verification,'MATCH')
        self.assertEqual(row.fundamental_source,'FinMind')
        self.assertEqual(row.revenue,13575475000.)
        self.assertEqual(row.financial_basis_verification_available_at,'2026-10-26T01:00:00+00:00')
        self.assertTrue(pd.isna(row.financial_release_date))
        self.assertFalse(row.financial_pit_exact)

    def test_mismatch_wrong_period_scope_or_ytd_cannot_verify_quarter(self):
        for change in ({'revenue':24752716},{'period_end':'2026-03-31'},
                       {'accounting_basis':'YTD'},{'source_scope':'COMPANY_PRODUCT'},
                       {'company':'3037.TW'},{'consolidation':'PARENT_ONLY'}):
            a=self.record();a.update(change)
            with self.subTest(change=change):
                row=self.reconcile(a).iloc[0]
                self.assertEqual(row.accounting_basis,'UNKNOWN')
                self.assertNotEqual(row.financial_value_verification,'MATCH')

    def test_only_documented_rounding_tolerance_is_allowed(self):
        panel=self.panel();panel.loc[0,'revenue']+=400
        row=self.reconcile(panel=panel).iloc[0]
        self.assertEqual(row.financial_value_verification,'ROUNDED_MATCH')
        panel.loc[0,'revenue']+=200
        row=self.reconcile(panel=panel).iloc[0]
        self.assertEqual(row.financial_value_verification,'MISMATCH')
        self.assertEqual(row.accounting_basis,'UNKNOWN')

    def test_future_or_untraceable_record_is_not_promoted(self):
        for change in ({'acquired_at':'2026-10-27T00:00:00Z'}, {'available_at':'2026-10-27T00:00:00Z'},
                       {'source_url':'https://analyst.example/report'}, {'source_page':None},
                       {'source_sha256':None}, {'unit':'USD million'}):
            a=self.record();a.update(change)
            with self.subTest(change=change):
                row=self.reconcile(a).iloc[0]
                self.assertEqual(row.accounting_basis,'UNKNOWN')

    def test_derived_quarter_requires_same_document_period_columns_and_arithmetic(self):
        a=self.record();a.update(evidence_status='DERIVED',period_start='2026-01-01',period_end='2026-03-31',
            revenue=11177241,gross_profit=1771445)
        panel=self.panel();panel.loc[0,['report_date','revenue','gross_profit']]=['2026-03-31',11177241000,1771445000]
        self.assertEqual(self.reconcile(a,panel).iloc[0].accounting_basis,'UNKNOWN')
        a['derivation']={'method':'H1_MINUS_Q2','inputs':{
            'h1':{'period_start':'2026-01-01','period_end':'2026-06-30','revenue':24752716,'gross_profit':5131055,'unit':'TWD thousand'},
            'q2':{'period_start':'2026-04-01','period_end':'2026-06-30','revenue':13575475,'gross_profit':3359610,'unit':'TWD thousand'}}}
        self.assertEqual(self.reconcile(a,panel).iloc[0].accounting_basis,'STANDALONE_QUARTER')
        for key,value in [('gross_profit',3359611),('period_start','2025-04-01'),('source_url','https://www.nanyapcb.com.tw/other.pdf')]:
            b=copy.deepcopy(a);b['derivation']['inputs']['q2'][key]=value
            self.assertEqual(self.reconcile(b,panel).iloc[0].accounting_basis,'UNKNOWN')

        for change in ({'consolidation':'PARENT_ONLY'},{'source_document':'unrelated.pdf'},
                       {'source_sha256':'b'*64},{'available_at':'2026-10-27T00:00:00Z'}):
            b=copy.deepcopy(a);b['derivation']['inputs']['q2'].update(change)
            with self.subTest(change=change):
                self.assertEqual(self.reconcile(b,panel).iloc[0].accounting_basis,'UNKNOWN')
        a['derivation']['inputs']['q2']['available_at']='2026-10-26T02:00:00Z'
        self.assertEqual(self.reconcile(a,panel).iloc[0].financial_basis_verification_available_at,'2026-10-26T02:00:00+00:00')
        a['derivation']['inputs']['q2'].pop('available_at')
        a.update(acquired_at='2026-05-01T00:00:00Z',available_at='2026-05-01T00:00:00Z')
        self.assertEqual(self.reconcile(a,panel).iloc[0].accounting_basis,'UNKNOWN')

    def test_explicit_half_year_span_cannot_be_promoted_as_a_quarter(self):
        a=self.record();a['period_start']='2026-01-01'
        self.assertEqual(self.reconcile(a).iloc[0].accounting_basis,'UNKNOWN')

    def test_tolerance_uses_disclosed_decimal_precision_not_currency_scale_alone(self):
        a=self.record();a.update(unit='TWD million',revenue=13575.475,gross_profit=3359.610,published_decimal_places=3)
        panel=self.panel();panel.loc[0,'revenue']+=400000
        self.assertEqual(self.reconcile(a,panel).iloc[0].financial_value_verification,'MISMATCH')
        a=self.record();a.pop('published_decimal_places')
        self.assertEqual(self.reconcile(a).iloc[0].accounting_basis,'UNKNOWN')

    def test_a_document_cannot_verify_a_quarter_that_has_not_ended(self):
        a=self.record();a['period_end']='2026-12-31'
        panel=self.panel();panel.loc[0,'report_date']='2026-12-31'
        self.assertEqual(self.reconcile(a,panel).iloc[0].accounting_basis,'UNKNOWN')

    def test_conflicting_company_quarter_requires_review(self):
        fn=getattr(financial,'reconcile_financial_evidence',None)
        self.assertIsNotNone(fn)
        b=copy.deepcopy(self.record());b['evidence_id']='revised';b['gross_profit']+=100
        with self.assertRaises(ValueError):
            fn(self.panel(),{'contract':'ABFQuarterlyFinancialEvidenceV1',
                'quarter_records':[self.record(),b]},as_of=self.cutoff)

    def test_duplicate_dataframe_labels_cannot_transfer_verification_to_another_company(self):
        other=self.panel();other.loc[0,['ticker','revenue','gross_profit']]=['3037.TW',1,1]
        panel=pd.concat([self.panel(),other])
        result=self.reconcile(panel=panel)
        self.assertEqual(result.index.tolist(),[0,0])
        self.assertEqual(result.iloc[0].financial_value_verification,'MATCH')
        self.assertEqual(result.iloc[1].financial_value_verification,'UNVERIFIED')
        self.assertFalse(result.iloc[1].accounting_basis_verified)
        self.assertTrue(pd.isna(result.iloc[1].financial_evidence_id))


if __name__=='__main__': unittest.main()
