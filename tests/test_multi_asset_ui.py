import copy
import tkinter as tk
import unittest
from unittest.mock import patch

from app.multi_asset_lab import MultiAssetLab
from test_multi_asset_adapters import request_fixture
import tempfile
from core.multi_asset.official_capture import capture_official_data, load_capture
from test_multi_asset_official_capture import frozen_fetch, STAMP


class MultiAssetUITests(unittest.TestCase):
    def setUp(self):
        try:
            self.app = MultiAssetLab()
            self.app.withdraw()
        except tk.TclError as exc:
            self.skipTest(str(exc))

    def tearDown(self):
        if hasattr(self, 'app'):
            self.app.destroy()

    def test_default_has_no_fabricated_data(self):
        self.assertIsNone(self.app.request)
        self.assertEqual(len(self.app.tables['comparison'].get_children()), 0)
        self.assertIn('載入', self.app.status.get())

    def test_new_request_invalidates_previous_result(self):
        self.app.result = {'old': True}
        self.app.set_request(request_fixture(), {'sha256': 'test'})
        self.assertIsNone(self.app.result)
        self.assertEqual(self.app.objective.get(), 'accumulation')

    def test_objective_and_currency_change_marks_result_obsolete(self):
        self.app.set_request(request_fixture(), {'sha256': 'test'})
        self.app.result = {'old': True}
        self.app.objective.set('income')
        self.app.settings_changed()
        self.assertIsNone(self.app.result)
        self.assertEqual(self.app.request['objective'], 'income')

    def test_typing_cutoff_invalidates_before_focus_leaves_field(self):
        self.app.set_request(request_fixture(), {'sha256': 'test'})
        self.app.result = {'old': True}
        before = self.app.generation
        self.app.cutoff.set('2026-01-15T00:00:00Z')
        self.assertIsNone(self.app.result)
        self.assertGreater(self.app.generation, before)

    def official_request(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        manifest = capture_official_data(['0050', '00981A'], '2026-09-01', '2026-09-30', directory.name,
            fetcher=frozen_fetch, clock=lambda: STAMP, pace_seconds=0)
        return load_capture(manifest)

    def test_official_view_shows_quotes_distribution_dates_and_limitations(self):
        self.app.set_request(*self.official_request())
        rows = self.app.tables['official'].get_children()
        self.assertTrue(rows)
        values = [self.app.tables['official'].item(row, 'values') for row in rows]
        self.assertTrue(any('108.45' in row for row in values))
        self.assertTrue(any('2026-10-13' in ' '.join(row) for row in values))
        self.assertIn('未調整', self.app.source_banner.get())
        self.assertIn('原始發布時間', self.app.source_banner.get())
        self.assertNotIn('TEST ONLY', self.app.status.get())

    def test_old_official_worker_result_is_discarded(self):
        request, lineage = self.official_request()
        old_generation = self.app.generation
        self.app.set_request(request_fixture(), {'sha256': 'newer'})
        self.app.source_pending.put((old_generation, request, lineage, None))
        self.app.source_busy = True
        self.app._poll_source()
        self.assertEqual(self.app.request['instruments'][0]['instrument_id'], 'TEST-ETF')
        self.assertIn('略過', self.app.status.get())

    def test_official_facts_remain_visible_after_setting_change_and_engine_error(self):
        self.app.set_request(*self.official_request())
        before = len(self.app.tables['official'].get_children())
        self.app.objective.set('income')
        self.assertEqual(len(self.app.tables['official'].get_children()), before)
        self.app.pending.put((self.app.generation, None, 'engine unavailable'))
        self.app._poll()
        self.assertEqual(len(self.app.tables['official'].get_children()), before)

    def test_official_view_discloses_coverage_without_implying_complete_calendar(self):
        self.app.set_request(*self.official_request())
        self.assertIn('覆蓋', self.app.source_banner.get())
        self.assertIn('非完整交易日曆', self.app.source_banner.get())


    def test_missing_metrics_render_unknown_with_reason(self):
        request = request_fixture()
        self.app.set_request(request, {'sha256': 'test'})
        row = dict(instrument_id='TEST-ETF', metrics={'total_return': None},
            unavailable={'total_return': 'MISSING_DISTRIBUTIONS'}, returns=[],
            rolling_returns=[], cash_flows=[], quality=['MISSING_DISTRIBUTIONS'])
        result = dict(instruments=[row], correlations=[], quality=[], methodology={})
        self.app.render_result(result)
        self.assertEqual(len(self.app.tables['comparison'].get_children()), 1)
        text = self.app.details['quality'].get('1.0', 'end')
        self.assertIn('MISSING_DISTRIBUTIONS', text)
        self.assertEqual(len(self.app.tables['cash_summary'].get_children()), 1)

    def test_cash_view_displays_amounts_in_named_columns(self):
        self.assertEqual(len(self.app.tables['cash']['columns']), 8)
        self.assertIn('稅費後現金', self.app.tables['cash']['columns'])

    def test_abf_cli_route_remains_and_multi_asset_route_is_additive(self):
        from app.main import main
        with patch('sys.argv', ['main.py', '--multi-asset']), patch('app.multi_asset_lab.launch_multi_asset_lab') as launch:
            main()
            launch.assert_called_once()
        with patch('sys.argv', ['main.py', '--abf-research']), patch('app.abf_research_lab.launch_abf_research_lab') as launch:
            main()
            launch.assert_called_once()


if __name__ == '__main__':
    unittest.main()
