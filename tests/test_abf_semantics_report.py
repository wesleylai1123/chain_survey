import unittest
import pandas as pd

from scripts.run_abf_semantics_validation import build_report


class AbfSemanticsReportTests(unittest.TestCase):
    def test_company_margin_handoff_has_own_audit_instead_of_pooled_significance(self):
        from tests.test_abf_margin_validation import panel
        factor=panel(quarters=24,companies=('3037.TW',),acquired='2026-10-24T08:00:00Z')
        report=build_report(pd.DataFrame(),factor,as_of='2026-10-25T12:00:00Z',iterations=19)
        self.assertEqual(len(report['margin_validation']['comparisons']),72)
        for scenario in ('UPSIDE','DOWNSIDE'):
            self.assertEqual(sum(r['scenario']==scenario for r in report['margin_validation']['comparisons']),36)
        stage=report['calibration_handoff'][0]['stages'][1]
        self.assertEqual(stage['status'],'AUDIT_COMPLETE_NOT_CALIBRATED')
        self.assertTrue(stage['evidence'])
        self.assertTrue(all(r['company_result']['company']=='3037.TW' for r in stage['evidence']))
        self.assertTrue(all(r['company_result']['forecast_beta'] is None for r in stage['evidence']))
        self.assertTrue(all('not yet validated' not in r['reason'] for r in stage['evidence']))

    def test_future_financial_labels_cannot_enter_historical_handoff(self):
        factor=pd.DataFrame([dict(ticker='3037.TW',report_date='2025-03-31',available_date='2025-05-15',
                                 revenue_yoy=.1,gross_margin_qoq=.01),
                             dict(ticker='3037.TW',report_date='2025-06-30',available_date='2025-08-15',
                                 revenue_yoy=.2,gross_margin_qoq=.02)])
        report=build_report(pd.DataFrame(),factor,as_of='2020-01-01T00:00:00Z',iterations=19)
        for handoff in report['calibration_handoff']:
            self.assertEqual(handoff['stages'][1]['status'],'UNAVAILABLE')
            self.assertEqual(handoff['stages'][1]['evidence'],[])


if __name__=='__main__':
    unittest.main()
