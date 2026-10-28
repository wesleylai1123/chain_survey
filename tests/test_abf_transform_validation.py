import importlib.util
import unittest

import numpy as np
import pandas as pd


def history():
    rng = np.random.default_rng(25)
    periods = pd.period_range('2015-01', periods=96, freq='M')
    x = rng.normal(0, 10, len(periods))
    rows = []
    for i, period in enumerate(periods):
        for metric, value, p in [('pcb_revenue_yoy',x[i],period)] + [
            (f'abf_company_revenue_yoy::{code}.TW', x[i] + rng.normal(0,.2), period+1)
            for code in ('3037','3189','8046')]:
            rows.append(dict(metric_id=metric,period=str(p),change_pct=value,
                published_at=(p.end_time+pd.Timedelta(days=12)).tz_localize('UTC').isoformat(),
                knowledge_time_method='source_reported',source_url='https://example.com/'+metric))
    return pd.DataFrame(rows)


class AbfTransformValidationTests(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('core.abf_transform_validation'), 'transform comparison missing')
        from core import abf_transform_validation
        return abf_transform_validation

    def report(self, frame=None):
        return self.api().compare_abf_transforms(history() if frame is None else frame,
            as_of='2026-01-01T00:00:00Z', metrics=('pcb_revenue_yoy',), iterations=99)

    def test_comparison_keeps_company_product_and_all_four_transform_pairs(self):
        table, details = self.report()
        self.assertEqual(len(table), 24)
        self.assertEqual(set(table['company']), {'3037.TW','3189.TW','8046.TW'})
        self.assertEqual(set(table['product']), {'ABF'})
        self.assertEqual(set(zip(table.feature_transform, table.target_transform)),
            {('LEVEL','LEVEL'),('LEVEL','CHANGE'),('CHANGE','LEVEL'),('CHANGE','CHANGE')})
        self.assertTrue(table['is_proxy'].all())
        self.assertNotIn('eligible', set(table['eligibility']))
        self.assertEqual(len(details), len(table))

    def test_each_side_retains_its_own_samples_stats_and_lineage(self):
        table, details = self.report()
        up = next(d for d in details.values() if d['scenario']=='UPSIDE' and d['feature_transform']=='LEVEL' and d['target_transform']=='LEVEL')
        down = next(d for d in details.values() if d['company']==up['company'] and d['scenario']=='DOWNSIDE' and d['feature_transform']=='LEVEL' and d['target_transform']=='LEVEL')
        self.assertTrue(all(r['x']>0 for r in up['sample_rows']))
        self.assertTrue(all(r['x']<0 for r in down['sample_rows']))
        for d in (up,down):
            for key in ('bootstrap_ci_low','bootstrap_ci_high','permutation_p','fdr_q','oos_folds','cross_company','gates','source_urls'):
                self.assertIn(key,d)
            for row in d['sample_rows']:
                self.assertLessEqual(row['feature_available_at'],row['target_observation_date'])
        self.assertIsNot(up['gates'],down['gates'])
        self.assertEqual(set(table.groupby('scenario')['fdr_family_size'].first()),{12})

    def test_missing_history_returns_explicit_unavailable_rows(self):
        table, details = self.report(pd.DataFrame())
        self.assertEqual(len(table),24)
        self.assertEqual(set(table.data_status),{'UNAVAILABLE'})
        self.assertEqual(set(table.eligibility),{'reject'})
        self.assertTrue(all(not d['sample_rows'] for d in details.values()))

    def test_missing_company_counts_against_sign_agreement(self):
        frame = history()
        frame = frame[~frame.metric_id.str.contains('3189|8046')]
        table,_ = self.report(frame)
        self.assertTrue((table.company_sign_agreement <= 1/3).all())

    def test_oos_training_labels_are_known_before_holdout(self):
        _, details = self.report()
        for detail in details.values():
            for fold in detail['oos_folds']:
                if fold['train_last_label_available_at']:
                    self.assertLess(fold['train_last_label_available_at'],fold['test_first_feature_available_at'])

    def test_predeclared_inverse_relation_is_not_forced_positive(self):
        frame=history()
        frame.loc[frame.metric_id.eq('pcb_revenue_yoy'),'change_pct'] *= -1
        table,details=self.api().compare_abf_transforms(frame,as_of='2026-01-01T00:00:00Z',
            metrics=('pcb_revenue_yoy',),iterations=99,expected_signs={'pcb_revenue_yoy':-1})
        row=table.query("scenario == 'UPSIDE' and feature_transform == 'LEVEL' and target_transform == 'LEVEL'").iloc[0]
        self.assertLess(row.spearman,-.9)
        self.assertTrue(details[row.comparison_id]['gates']['correlation_direction'])

    def test_any_missing_dependency_source_blocks_support(self):
        frame=history()
        frame.loc[frame.metric_id.str.startswith('abf_company'),'source_url']=''
        table,details=self.report(frame)
        self.assertEqual(set(table.eligibility),{'reject'})
        self.assertTrue(all(not d['gates']['source_lineage'] for d in details.values()))


if __name__ == '__main__':
    unittest.main()
