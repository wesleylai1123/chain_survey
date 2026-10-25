"""Portable company views retain reviewed facts and the audited chart samples."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

import pandas as pd

from core.abf_company_survey import build_company_survey
from tests.test_abf_company_survey import AS_OF, audit_fixture, fact_row


ROOT = Path(__file__).resolve().parents[1]


class CompanySurveyHtmlTests(unittest.TestCase):
    def renderer(self):
        self.assertIsNotNone(importlib.util.find_spec('core.abf_company_survey_html'),
                             'Portable company renderer is missing')
        from core import abf_company_survey_html
        return abf_company_survey_html

    def report(self):
        return build_company_survey(audit_fixture(), pd.DataFrame(), [], as_of=AS_OF)

    def embedded(self, html):
        block = re.search(r'<script id="company-survey-data" type="application/json">(.*?)</script>',
                          html, re.S)
        self.assertIsNotNone(block, 'The standalone report needs its own embedded evidence')
        return json.loads(block.group(1))

    def test_html_safe_json_round_trip_and_escape_source_injection(self):
        renderer = self.renderer()
        report = self.report()
        attack = '</script><img src=x onerror="alert(1)"><script>bad()</script>'
        report['companies'][0]['name'] = attack
        report['companies'][0]['primary_facts'] = [fact_row(statement=attack, document=attack,
            source_url='javascript:alert(1)', source_urls=['javascript:alert(1)'])]
        rendered = renderer.render_company_survey(report)
        self.assertEqual(self.embedded(rendered), report)
        self.assertNotIn(attack, rendered)
        self.assertNotIn('<img src=x', rendered)
        self.assertIn('\\u003c/script\\u003e', rendered)
        self.assertNotIn('href="javascript:', rendered)

    def test_all_company_scenario_transform_choices_survive_without_winner_selection(self):
        rendered = self.renderer().render_company_survey(self.report())
        report = self.embedded(rendered)
        self.assertEqual([c['company'] for c in report['companies']], ['3037.TW', '3189.TW', '8046.TW'])
        for company in report['companies']:
            for scenario in ('UPSIDE', 'DOWNSIDE'):
                options = company['scenarios'][scenario]['options']
                self.assertEqual(len(options), 20)
                self.assertEqual({(o['feature_transform'], o['target_transform']) for o in options},
                                 {('LEVEL', 'LEVEL'), ('LEVEL', 'CHANGE'), ('CHANGE', 'LEVEL'), ('CHANGE', 'CHANGE')})
        for control in ('company-select', 'scenario-select', 'metric-select', 'feature-select', 'target-select'):
            self.assertIn(f'id="{control}"', rendered)
        self.assertNotRegex(rendered, r'<script[^>]+src=|<link[^>]+href=')
        self.assertNotRegex(rendered, r'\bfetch\s*\(|XMLHttpRequest|https://cdn')

    def test_empty_inputs_explain_missing_pit_and_uncalibrated_bridge(self):
        report = build_company_survey({}, pd.DataFrame(), [], as_of=AS_OF)
        rendered = self.renderer().render_company_survey(report)
        for label in ('UNAVAILABLE', 'PIT', 'NOT_CALIBRATED', '缺少', '公司整體', 'Driver → Revenue → GM → EPS'):
            self.assertIn(label, rendered)

    def test_plot_helpers_preserve_audited_values_and_fixed_oos_membership(self):
        renderer = self.renderer()
        company = self.report()['companies'][0]
        detail = next(iter(company['details'].values()))
        original = deepcopy(detail)
        points = renderer.scatter_points(detail)
        self.assertEqual([(p['period'], p['x'], p['y'], p['is_oos']) for p in points],
                         [('2025-01', 3., 4., True)])
        self.assertEqual(detail, original)
        industry = [s for s in renderer.trend_series(company, 'pcb_revenue_yoy') if s['company'] == 'INDUSTRY']
        self.assertEqual(industry[0]['points'][0]['value'], 3.)
        self.assertEqual(industry[0]['points'][0]['period'], '2025-01')

    def test_manager_brief_uses_actual_fact_values_and_cites_fact_ids(self):
        renderer = self.renderer()
        facts = json.loads((ROOT/'data/abf_company_research_evidence.json').read_text(encoding='utf-8'))
        report = build_company_survey({}, pd.DataFrame(), facts, as_of='2026-10-24T23:59:59+08:00')
        lines = renderer.company_brief(report['companies'][0])
        text = '\n'.join(row['statement'] for row in lines)
        for value in ('46', '49', '52', '51', '22', '24.8', '57.30'):
            self.assertIn(value, text)
        ids = {f['fact_id'] for f in report['companies'][0]['primary_facts']}
        self.assertTrue(all(row['fact_ids'] and set(row['fact_ids']) <= ids for row in lines))
        for company in report['companies']:
            gm = renderer.latest_gross_margin_fact(company)
            self.assertEqual(gm['source_scope'], 'COMPANY_TOTAL')
        nan_ya_text = '\n'.join(row['statement'] for row in renderer.company_brief(report['companies'][2]))
        self.assertIn('前瞻', nan_ya_text)
        self.assertIn('稼動率', nan_ya_text)

    def test_partial_qualitative_brief_uses_each_actual_statement_and_own_fact_id(self):
        renderer = self.renderer()
        cases = [('product_development_guidance', 'Only optical development is planned.'),
                 ('application_demand_driver', 'Management attributes sales changes only to customer restocking.'),
                 ('downside_signal', 'Only automotive demand weakened.')]
        for metric, statement in cases:
            with self.subTest(metric=metric):
                fact = fact_row(fact_id='one-'+metric, metric_id=metric, value=None, statement=statement)
                company = build_company_survey({}, pd.DataFrame(), [fact], as_of=AS_OF)['companies'][0]
                lines = renderer.company_brief(company)
                self.assertEqual(len(lines), 1)
                self.assertIn(statement, lines[0]['statement'])
                self.assertEqual(lines[0]['fact_ids'], [fact['fact_id']])
                for unsupported in ('1.6T', 'ASIC', 'CPU', 'PC／消費電子'):
                    self.assertNotIn(unsupported, lines[0]['statement'])

    def test_qualitative_brief_prefers_reviewed_translation_without_combining_downside_facts(self):
        renderer = self.renderer()
        first = fact_row(fact_id='auto', metric_id='downside_signal', value=None,
                         statement='Automotive demand weakened.', statement_zh='車用需求轉弱。')
        second = fact_row(fact_id='pc', metric_id='downside_signal', value=None,
                          statement='Only PC component shortages were disclosed.')
        company = build_company_survey({}, pd.DataFrame(), [first, second], as_of=AS_OF)['companies'][0]
        lines = renderer.company_brief(company)
        self.assertEqual(len(lines), 2)
        by_id = {row['fact_ids'][0]: row['statement'] for row in lines}
        self.assertIn(first['statement_zh'], by_id['auto'])
        self.assertNotIn(first['statement'], by_id['auto'])
        self.assertIn(second['statement'], by_id['pc'])
        self.assertNotIn('車用', by_id['pc'])

    def test_application_and_segment_briefs_do_not_invent_product_names_from_company(self):
        renderer = self.renderer()
        facts = [fact_row(fact_id='app', metric_id='application_revenue_mix', value=12,
                          statement='Automotive application mix.', source_product='All company products'),
                 fact_row(fact_id='segment', metric_id='segment_revenue', value=100,
                          statement='Optics segment revenue.', source_product='Optics')]
        company = build_company_survey({}, pd.DataFrame(), facts, as_of=AS_OF)['companies'][0]
        text = '\n'.join(row['statement'] for row in renderer.company_brief(company))
        for fact in facts:
            self.assertIn(fact['statement'], text)
        self.assertIn('Optics', text)
        for invented in ('HPC', 'AI Data Center', 'IC 載板部門'):
            self.assertNotIn(invented, text)

    def test_headline_gross_margin_uses_only_observed_verified_company_total_facts(self):
        renderer = self.renderer()
        actual = fact_row(fact_id='actual-gm', metric_id='company_gross_margin_reported', value=20,
                          product='All company products', source_scope='COMPANY_TOTAL', is_proxy=True)
        alternatives = [dict(fact_id='guidance-gm', value=35, measure_kind='GUIDANCE'),
                        dict(fact_id='estimated-gm', value=36, evidence_status='ESTIMATED'),
                        dict(fact_id='product-gm', value=37, product='ABF', source_scope='COMPANY_PRODUCT', is_proxy=False)]
        for overrides in alternatives:
            with self.subTest(fact_id=overrides['fact_id']):
                changed = dict(actual, observation_date='2025-04-30T00:00:00+08:00', **overrides)
                company = build_company_survey({}, pd.DataFrame(), [actual, changed], as_of=AS_OF)['companies'][0]
                self.assertEqual(renderer.latest_gross_margin_fact(company)['fact_id'], 'actual-gm')
                only_changed = build_company_survey({}, pd.DataFrame(), [changed], as_of=AS_OF)['companies'][0]
                self.assertIsNone(renderer.latest_gross_margin_fact(only_changed))

    def test_direct_abf_brief_rejects_guidance_estimates_and_company_total_mix(self):
        renderer = self.renderer()
        for metric in ('abf_product_mix', 'abf_revenue_yoy', 'abf_revenue_qoq'):
            for overrides in (dict(evidence_status='ESTIMATED'), dict(measure_kind='GUIDANCE'),
                              dict(source_scope='COMPANY_TOTAL', is_proxy=True)):
                with self.subTest(metric=metric, overrides=overrides):
                    fact = fact_row(metric_id=metric, value=60, **overrides)
                    company = build_company_survey({}, pd.DataFrame(), [fact], as_of=AS_OF)['companies'][0]
                    text = '\n'.join(row['statement'] for row in renderer.company_brief(company))
                    self.assertNotIn('直接揭露', text)
                    self.assertNotIn('60%', text)

    def test_inferred_operating_mechanism_remains_explicitly_unvalidated_in_html(self):
        report = self.report()
        html = self.renderer().render_company_survey(report)
        self.assertIn('id="mechanisms"', html)
        self.assertIn('營運傳導假說', html)
        self.assertIn('operating_mechanism', html)
        self.assertIn('UNVALIDATED_HYPOTHESIS', html)

    def test_actual_tpca_metrics_have_specific_chinese_names(self):
        renderer = self.renderer()
        expected = {'pcb_revenue_yoy': 'PCB 產業營收年增率',
            'rigid_pcb_export_yoy': '硬板出口年增率',
            'pcb_material_revenue_yoy': 'PCB 材料營收年增率',
            'ccl_export_yoy': '銅箔基板出口年增率',
            'ccl_import_yoy': '銅箔基板進口年增率'}
        for metric, label in expected.items():
            self.assertEqual(renderer.metric_label(metric), label)

    def test_monthly_segments_break_missing_values_and_calendar_gaps(self):
        renderer = self.renderer()
        points = [dict(period='2024-12', value=2), dict(period='2025-01', value=0),
                  dict(period='2025-02', value=None), dict(period='2025-03', value=4),
                  dict(period='2025-05', value=5)]
        self.assertEqual([[p['period'] for p in s] for s in renderer.monthly_segments(points)],
                         [['2024-12', '2025-01'], ['2025-03'], ['2025-05']])
        self.assertEqual(points[1]['value'], 0)

    def test_source_link_preserves_pdf_page_and_blocks_non_web_schemes(self):
        renderer = self.renderer()
        self.assertEqual(renderer.source_link(dict(source_url='https://company.tw/a.pdf#old', page=7)),
                         'https://company.tw/a.pdf#page=7')
        self.assertIsNone(renderer.source_link(dict(source_url='javascript:alert(1)', page=7)))
        self.assertIsNone(renderer.source_link(dict(source_url='file:///private/a.pdf')))

    def test_static_overview_compares_sourced_company_total_gross_margins(self):
        facts = json.loads((ROOT/'data/abf_company_research_evidence.json').read_text(encoding='utf-8'))
        report = build_company_survey({}, pd.DataFrame(), facts, as_of='2026-10-25T23:59:59+08:00')
        html = self.renderer().render_company_survey(report)
        table = re.search(r'<table id="gross-margin-overview">(.*?)</table>', html, re.S)
        self.assertIsNotNone(table)
        for value in ('24.80%', '26.09%', '24.75%', 'COMPANY_TOTAL'):
            self.assertIn(value, table.group(1))
        self.assertEqual(table.group(1).count('target="_blank"'), 3)

    def test_cli_writes_three_unavailable_companies_when_files_are_absent(self):
        path = ROOT/'scripts/run_abf_company_survey.py'
        self.assertTrue(path.exists(), 'Company survey CLI is missing')
        with tempfile.TemporaryDirectory(dir=ROOT/'artifacts') as tmp:
            output = Path(tmp)/'output'
            absent = Path(tmp)/'missing'
            result = subprocess.run([sys.executable, str(path), '--audit', str(absent),
                '--factor', str(absent), '--facts', str(absent), '--as-of', AS_OF,
                '--output-dir', str(output)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            raw = (output/'abf_company_survey.json').read_text(encoding='utf-8')
            self.assertNotRegex(raw, r'\bNaN\b|\bInfinity\b')
            report = json.loads(raw)
            self.assertEqual(len(report['companies']), 3)
            self.assertTrue(all(c['data_status'] == 'UNAVAILABLE' for c in report['companies']))
            self.assertTrue(all(row['sha256'] is None for row in report['input_manifest'].values()))
            self.assertIsInstance(report['working_tree_dirty'], bool)
            self.assertRegex(report['code_revision'], r'^[0-9a-f]{40}$')
            self.assertEqual(self.embedded((output/'abf_company_survey.html').read_text(encoding='utf-8')), report)


class CompanySurveyDesktopTests(unittest.TestCase):
    def test_desktop_selectors_preserve_company_scenario_and_audited_points(self):
        import tkinter as tk
        from app.abf_company_survey_view import CompanySurveyView
        root = tk.Tk()
        root.withdraw()
        self.addCleanup(root.destroy)
        report = build_company_survey(audit_fixture(), pd.DataFrame(), [], as_of=AS_OF)
        view = CompanySurveyView(root, report)
        for company in report['companies']:
            for scenario in ('UPSIDE', 'DOWNSIDE'):
                for ft, tt in (('LEVEL', 'LEVEL'), ('LEVEL', 'CHANGE'), ('CHANGE', 'LEVEL'), ('CHANGE', 'CHANGE')):
                    view.company_var.set(company['company'])
                    view.scenario_var.set(scenario)
                    view.metric_var.set('pcb_revenue_yoy')
                    view.feature_var.set(ft)
                    view.target_var.set(tt)
                    view.render()
                    detail = view.selected_detail
                    self.assertEqual(view.selected_company['company'], company['company'])
                    self.assertEqual((detail['scenario'], detail['feature_transform'], detail['target_transform']),
                                     (scenario, ft, tt))
                    offsets = view.scatter_ax.collections[0].get_offsets().tolist()
                    self.assertEqual(offsets, [[3., 4.]] if scenario == 'UPSIDE' else [[-2., -1.]])
        self.assertEqual(view.report, report)

    def test_desktop_empty_report_is_readable_and_uncalibrated(self):
        import tkinter as tk
        from app.abf_company_survey_view import CompanySurveyView
        root = tk.Tk()
        root.withdraw()
        self.addCleanup(root.destroy)
        view = CompanySurveyView(root, build_company_survey({}, pd.DataFrame(), [], as_of=AS_OF))
        view.render()
        self.assertIn('NOT_CALIBRATED', view.research_text.get('1.0', 'end'))
        self.assertIn('UNAVAILABLE', view.facts_text.get('1.0', 'end'))

    def test_acquisition_labels_do_not_claim_historical_first_seen(self):
        import tkinter as tk
        from app.abf_company_survey_view import CompanySurveyView
        from tests.test_abf_company_survey import factor_row
        root = tk.Tk()
        root.withdraw()
        self.addCleanup(root.destroy)
        report = build_company_survey({}, pd.DataFrame([factor_row()]), [fact_row()], as_of=AS_OF)
        view = CompanySurveyView(root, report)
        for text in (view.facts_text.get('1.0', 'end'), view.finance_text.get('1.0', 'end')):
            self.assertIn('本次取得／快照取得', text)
            self.assertNotIn('首次取得：', text)
            self.assertIn('歷史首次取得時間未驗證', text)
        html = self.renderer_html(report)
        self.assertIn('本次取得／快照取得', html)
        self.assertNotIn('<br>首次取得 ', html)
        self.assertIn('歷史首次取得時間未驗證', html)

    def test_operating_mechanism_is_qualified_and_cites_its_own_evidence(self):
        import tkinter as tk
        from app.abf_company_survey_view import CompanySurveyView
        root = tk.Tk()
        root.withdraw()
        self.addCleanup(root.destroy)
        report = build_company_survey(audit_fixture(), pd.DataFrame(), [], as_of=AS_OF)
        view = CompanySurveyView(root, report)
        text = view.summary_text.get('1.0', 'end')
        mechanism = view.selected_company['operating_mechanism'][0]
        for value in ('營運傳導假說', mechanism['statement'], mechanism['status'], mechanism['evidence_status'],
                      *mechanism['evidence_ids']):
            self.assertIn(value, text)

    @staticmethod
    def renderer_html(report):
        from core.abf_company_survey_html import render_company_survey
        return render_company_survey(report)


if __name__ == '__main__':
    unittest.main()
