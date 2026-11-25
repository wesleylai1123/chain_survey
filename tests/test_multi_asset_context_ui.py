from pathlib import Path
import tempfile
import threading
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch

from app.multi_asset_lab import MultiAssetLab
from core.multi_asset.official_capture import load_capture
from test_multi_asset_context_capture import capture_from_fixtures, LEGACY, NOVEMBER


class ETFContextUITests(unittest.TestCase):
    def setUp(self):
        try:
            self.app = MultiAssetLab()
            self.app.withdraw()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.addCleanup(self.app.destroy)
        self.addCleanup(self.app.update_idletasks)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)

    def context_request(self, original=NOVEMBER):
        return load_capture(capture_from_fixtures(self.directory, original, include_etf_context=True))

    def rows(self, key):
        self.assertIn(key, self.app.tables)
        tree = self.app.tables[key]
        return [tree.item(item, 'values') for item in tree.get_children()]

    def test_append_tab_preserves_all_existing_positions(self):
        titles = [self.app.book.tab(tab, 'text') for tab in self.app.book.tabs()]
        self.assertEqual(titles, [
            '資產比較', '配息與現金流', '滾動報酬', '相關性 / OOS / 市場狀態', '持股與外匯曝險',
            '指標與研究證據', '資料品質與假設', '官方原始資料', '淨值與基準',
        ])
        self.assertEqual(self.app.book.index(self.app.etf_context), 8)

    def test_nav_and_independent_references_show_values_dates_and_sources(self):
        request, lineage = self.context_request()
        self.app.set_request(request, lineage)
        nav = {row[0]: row for row in self.rows('etf_nav')}
        self.assertEqual(nav['0050.TW'][1:7], ('2026-11-20', '84.67', 'TWD', '84.45', '-0.26%', '可用'))
        self.assertEqual(nav['00981A.TW'][1:7], ('2026-11-20', '18.81', 'TWD', '18.58', '-1.22%', '可用'))
        sources = {source['source_id']: source['source_url'] for source in request['adapter_lineage']['sources']}
        self.assertEqual(nav['0050.TW'][7:], (sources['nav'], sources['price:0050:20261101']))
        self.assertEqual(nav['00981A.TW'][7:], (sources['nav'], sources['price:00981A:20261101']))

        references = self.rows('etf_reference')
        self.assertEqual(len(references), 2)
        for row, name, source in zip(references, ('臺灣50', '發行量加權'), ('index:TAI50', 'index:TAIEX')):
            self.assertIn(name, row[0])
            self.assertEqual(row[1:], ('2026-11-02', '2026-11-20', '15/15', 'TWD',
                                      '含息報酬指數', '可用', sources[source]))
        banner = self.app.etf_context.banner.get()
        for phrase in ('獨立研究參考', '契約基準', '收盤估值比率', '最新', '供應日期', '日期聯集', '發布時間未知', '取得時間'):
            self.assertIn(phrase, banner)

    def test_exact_zero_premium_is_shown_as_percent(self):
        request, lineage = self.context_request()
        close = next(row for row in request['observations']
                     if row['instrument_id'] == '0050.TW' and row['period'] == '2026-11-20')
        close['value'] = 84.67
        self.app.set_request(request, lineage)
        self.assertEqual(self.rows('etf_nav')[0][5:7], ('0.00%', '可用'))

    def test_missing_same_date_close_does_not_use_prior_close(self):
        request, lineage = self.context_request()
        request['observations'] = [row for row in request['observations']
                                   if (row['instrument_id'], row['period']) != ('0050.TW', '2026-11-20')]
        self.app.set_request(request, lineage)
        row = self.rows('etf_nav')[0]
        self.assertEqual(row[1:6], ('2026-11-20', '84.67', 'TWD', '—', '—'))
        self.assertIn('缺少同日收盤價', row[6])
        self.assertTrue(row[7].startswith('https://'))
        self.assertEqual(row[8], '—')

    def test_mismatched_native_currency_prevents_ratio_even_with_reporting_currency(self):
        request, lineage = self.context_request()
        nav = next(row for row in request['adapter_lineage']['etf_context']['nav_observations']
                   if row['instrument_id'] == '0050.TW')
        nav['currency'] = 'USD'
        self.app.set_request(request, lineage)
        self.app.currency.set('USD')
        row = self.rows('etf_nav')[0]
        self.assertEqual(row[1:6], ('2026-11-20', '84.67', 'USD', '84.45', '—'))
        self.assertIn('原幣不同', row[6])

    def test_cutoff_before_acquisition_and_invalid_typing_mark_facts_unavailable(self):
        self.app.set_request(*self.context_request())
        for cutoff in ('2026-11-20T00:00:00Z', '2026-11-'):
            with self.subTest(cutoff=cutoff):
                self.app.cutoff.set(cutoff)
                row = self.rows('etf_nav')[0]
                self.assertEqual(row[1:6], ('2026-11-20', '84.67', 'TWD', '84.45', '—'))
                self.assertIn('截止時不可用', row[6])
                self.assertEqual(self.rows('etf_reference')[0][3], '0/15')
                self.assertIn('截止時不可用', self.rows('etf_reference')[0][6])
                if cutoff == '2026-11-':
                    self.assertIn('截止時間格式不完整或無效', self.app.etf_context.banner.get())

    def test_conflicting_nav_does_not_present_a_value_or_ratio(self):
        request, lineage = self.context_request()
        nav = request['adapter_lineage']['etf_context']['nav_observations']
        original = next(row for row in nav if row['instrument_id'] == '0050.TW')
        nav.append(dict(original, nav=original['nav'] + 1))
        self.app.set_request(request, lineage)
        row = self.rows('etf_nav')[0]
        self.assertEqual((row[2], row[5]), ('—', '—'))
        self.assertIn('淨值紀錄互相衝突', row[6])

    def test_partial_references_and_nav_outside_window_keep_source_dates(self):
        self.app.set_request(*self.context_request(LEGACY))
        for row in self.rows('etf_nav'):
            self.assertEqual(row[1], '2026-11-20')
            self.assertNotEqual(row[2], '—')
            self.assertEqual(row[4:6], ('—', '—'))
            self.assertIn('研究期間外', row[6])
        for row in self.rows('etf_reference'):
            self.assertEqual(row[1:4], ('2026-11-02', '2026-11-20', '14/53'))
            self.assertIn('僅涵蓋部分', row[6])

    def test_older_capture_replaces_context_with_explanation(self):
        self.app.set_request(*self.context_request())
        self.app.set_request(*load_capture(NOVEMBER))
        self.assertEqual(self.rows('etf_nav'), [])
        self.assertEqual(self.rows('etf_reference'), [])
        self.assertIn('這份資料檔未包含', self.app.etf_context.banner.get())
        self.assertIn('ETF 淨值', self.app.etf_context.banner.get())

    def test_settings_result_and_failures_keep_loaded_context_visible(self):
        self.app.set_request(*self.context_request())
        nav, references = self.rows('etf_nav'), self.rows('etf_reference')
        self.app.objective.set('income')
        self.app.currency.set('USD')
        self.app.cutoff.set('2026-11-22T00:00:00Z')
        for update in (
            lambda: self.app.render_result(dict(instruments=[], correlations=[], quality=[], methodology={})),
            self.simulate_engine_failure, self.simulate_source_failure,
        ):
            self.assertEqual(self.rows('etf_nav'), nav)
            self.assertEqual(self.rows('etf_reference'), references)
            update()
        self.assertEqual(self.rows('etf_nav'), nav)
        self.assertEqual(self.rows('etf_reference'), references)
        self.assertIn('擷取失敗', self.app.status.get())

    def simulate_engine_failure(self):
        self.app.pending.put((self.app.generation, None, 'test engine failure'))
        self.app._poll()
        self.assertIn('計算未完成', self.app.status.get())

    def simulate_source_failure(self):
        self.app.source_pending.put((self.app.generation, None, None, 'test source failure'))
        self.app._poll_source()

    def test_capture_checkbox_passes_plain_boolean_from_dialog_to_worker(self):
        caller_thread = threading.get_ident()
        calls = []

        def capture(symbols, start, end, output, *, base_currency, include_etf_context):
            calls.append((threading.get_ident(), include_etf_context))
            return capture_from_fixtures(self.directory, include_etf_context=include_etf_context,
                                         base_currency=base_currency)

        with patch('app.multi_asset_lab.capture_official_data', side_effect=capture):
            for enabled in (True, False):
                with self.subTest(enabled=enabled):
                    existing = set(self.app.winfo_children())
                    self.app.open_source_dialog()
                    dialog, = set(self.app.winfo_children()) - existing
                    self.assertIsInstance(dialog, tk.Toplevel)
                    frame, = dialog.winfo_children()
                    boxes = [widget for widget in frame.winfo_children() if isinstance(widget, ttk.Checkbutton)]
                    self.assertEqual(len(boxes), 1)
                    checkbox = boxes[0]
                    self.assertIn('淨值', checkbox.cget('text'))
                    self.assertIn('報酬指數', checkbox.cget('text'))
                    self.assertTrue(checkbox.instate(['selected']))
                    if not enabled:
                        checkbox.invoke()
                    submit, = (widget for widget in frame.winfo_children() if isinstance(widget, ttk.Button))
                    submit.invoke()
                    self.assertTrue(self.app.source_busy)
                    self.assertTrue(self.app.source_button.instate(['disabled']))
                    self.assertTrue(self.app.run_button.instate(['disabled']))
                    self.finish_source_worker()
                    self.assertFalse(self.app.source_busy)
                    self.assertFalse(self.app.source_button.instate(['disabled']))
                    self.assertFalse(self.app.run_button.instate(['disabled']))
                    worker_thread, flag = calls[-1]
                    self.assertNotEqual(worker_thread, caller_thread)
                    self.assertIs(flag, enabled)
                    self.assertEqual(len(self.app.request['instruments']), 5 if enabled else 3)
                    self.assertEqual(bool(self.rows('etf_nav')), enabled)

    def finish_source_worker(self):
        def stop_when_finished():
            nonlocal check
            if self.app.source_busy:
                check = self.app.after(10, stop_when_finished)
            else:
                self.app.quit()

        timeout = self.app.after(5000, self.app.quit)
        check = self.app.after(10, stop_when_finished)
        self.app.mainloop()
        self.app.after_cancel(check)
        self.app.after_cancel(timeout)

    def test_stale_context_worker_cannot_replace_loaded_snapshot(self):
        request, lineage = self.context_request()
        self.app.set_request(request, lineage)
        old_generation = self.app.generation
        self.app.objective.set('income')
        self.app.source_busy = True
        self.app.source_pending.put((old_generation, *load_capture(NOVEMBER), None))
        self.app._poll_source()
        self.assertIn('略過', self.app.status.get())
        self.assertEqual(self.app.request['objective'], 'income')
        self.assertEqual(len(self.rows('etf_nav')), 2)
        self.assertEqual(len(self.rows('etf_reference')), 2)

    def test_reference_indices_do_not_appear_as_raw_closes_or_plots(self):
        request, lineage = self.context_request()
        self.app.set_request(request, lineage)
        raw_quote_ids = {row[2] for row in self.rows('official') if row[1] == '官方收盤價'}
        self.assertEqual(raw_quote_ids, {'0050.TW', '00981A.TW'})
        expected_symbols = {item['symbol'] for item in request['instruments']
                            if item['asset_type'] in {'etf', 'fx'}}
        self.assertEqual({line.get_label() for line in self.app.official.ax.lines}, expected_symbols)


if __name__ == '__main__':
    unittest.main()
