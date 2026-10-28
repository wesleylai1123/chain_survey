"""The company tab reads the same saved statistical authority as the CLI."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from app import abf_research_lab as lab
from tests.test_abf_company_survey import AS_OF, audit_fixture


class ResearchLabCompanyReportTests(unittest.TestCase):
    def load(self, directory):
        self.assertTrue(hasattr(lab.AbfResearchLab, '_load_company_report'),
                        'The company reader must load the saved canonical audit')
        with patch.object(lab, 'SEMANTICS_AUDIT', Path(directory)/'audit.json'), \
             patch.object(lab, 'COMPANY_FACTS', Path(directory)/'facts.json'), \
             patch('core.abf_margin_validation.validate_margin_transmission',
                   side_effect=AssertionError('Company reader must not fit a new margin model')):
            return lab.AbfResearchLab._load_company_report(
                SimpleNamespace(factor=pd.DataFrame(), as_of=AS_OF))

    def test_saved_margin_statistics_folds_and_samples_are_preserved(self):
        audit = audit_fixture()
        comparison = dict(comparison_id='saved-margin', company='3037.TW', product='ABF',
            scenario='UPSIDE', feature='revenue_yoy', target='gross_margin_qoq', lag_quarters=1,
            source_scope='COMPANY_TOTAL', is_proxy=True, eligibility='reject', forecast_beta=None,
            sample_size=17, descriptive_beta=.312, beta_ci_low=-.04, beta_ci_high=.67,
            permutation_p=.073, fdr_q=.219, spearman=.48, gates={'oos_stability': False},
            oos_folds=[dict(fold=1, valid=False, train_sample_size=12, test_sample_size=5)],
            sample_rows=[dict(feature_period='2025Q1', target_period='2025Q2', x=12.3, y=.7,
                              source_urls=['https://company.tw/quarter.pdf'])])
        audit['margin_validation'] = dict(contract='ABFMarginValidationV1', as_of=audit['as_of'],
            policy={'iterations': 999}, comparisons=[comparison])
        original = deepcopy(audit)
        with tempfile.TemporaryDirectory(dir=lab.ROOT) as directory:
            (Path(directory)/'audit.json').write_text(json.dumps(audit), encoding='utf-8')
            report = self.load(directory)
        margin = report['companies'][0]['financial_bridge']['margin_audit']
        self.assertEqual(margin['comparisons'], [comparison])
        self.assertEqual(margin['policy'], {'iterations': 999})
        self.assertEqual(margin['data_status'], 'AVAILABLE')
        self.assertEqual(report['audit_metadata']['as_of'], audit['as_of'])
        self.assertEqual(audit, original)

    def test_absent_saved_audit_leaves_company_margin_explicitly_unavailable(self):
        with tempfile.TemporaryDirectory(dir=lab.ROOT) as directory:
            report = self.load(directory)
        for company in report['companies']:
            margin = company['financial_bridge']['margin_audit']
            self.assertEqual(margin['data_status'], 'UNAVAILABLE')
            self.assertEqual(margin['comparisons'], [])
            self.assertIsNone(margin['forecast_beta'])


if __name__ == '__main__':
    unittest.main()
