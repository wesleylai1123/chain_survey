import unittest
import pandas as pd

from scripts.run_abf_semantics_validation import build_report


class AbfSemanticsReportTests(unittest.TestCase):
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
