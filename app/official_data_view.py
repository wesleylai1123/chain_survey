"""Human-readable official facts and explicitly unadjusted quote paths."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from core.multi_asset.adapters import available, timestamp
from zoneinfo import ZoneInfo


class OfficialDataView(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.banner = tk.StringVar(value='尚未載入官方快照。可擷取官方資料，或載入已保存的 manifest.json 離線重播。')
        ttk.Label(self, textvariable=self.banner, wraplength=1320, foreground='#176b78', justify='left').pack(anchor='w', pady=(0, 12))
        frame = ttk.Frame(self)
        frame.pack(fill='both', expand=True)
        columns = ('日期', '資料類型', '資產', '數值', '幣別 / 方向', '補充與可得狀態', '來源')
        self.tree = ttk.Treeview(frame, columns=columns, show='headings', height=12)
        for column in columns:
            self.tree.heading(column, text=column)
            self.tree.column(column, width=175, minwidth=110, stretch=True)
        vertical = ttk.Scrollbar(frame, command=self.tree.yview)
        horizontal = ttk.Scrollbar(frame, orient='horizontal', command=self.tree.xview)
        self.tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.tree.grid(row=0, column=0, sticky='nsew')
        vertical.grid(row=0, column=1, sticky='ns')
        horizontal.grid(row=1, column=0, sticky='ew')
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.figure = Figure(figsize=(11, 2.7), dpi=100, facecolor='#edf2f7')
        self.ax = self.figure.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.figure, master=self)
        self.canvas.get_tk_widget().pack(fill='both', expand=True, pady=(10, 0))
        self.clear()

    def clear(self):
        self.tree.delete(*self.tree.get_children())
        self.banner.set('尚未載入官方快照；原始價格不能代替總報酬。')
        self.ax.clear()
        self.ax.set_title('Official unadjusted quotes / spot FX (no distributions reinvested)', fontsize=10)
        self.ax.set_ylabel('Price ratio (first valid = 100)')
        self.figure.tight_layout()
        self.canvas.draw_idle()

    def render(self, request, lineage):
        metadata = request.get('adapter_lineage', {})
        if metadata.get('kind') != 'TAIWAN_OFFICIAL_AS_ACQUIRED':
            return
        self.clear()
        etfs = {i['instrument_id'] for i in request['instruments'] if i['asset_type'] == 'etf'}
        grid = request['period_grid']
        known_prices = sum(r['instrument_id'] in etfs and r['value'] is not None and available(r, request['as_of']) for r in request['observations'])
        known_fx = sum(r['period'] in grid and r['rate'] is not None and available(r, request['as_of']) for r in request['fx_rates'])
        local_capture = timestamp(metadata['captured_at']).astimezone(ZoneInfo('Asia/Taipei')).strftime('%Y-%m-%d %H:%M:%S（台北）')
        self.banner.set(f"官方快照取得時間：{local_capture}　｜　ETF 原始收盤價未調整、未含配息再投入。\n"
            f"提供日期：{grid[0]}–{grid[-1]}；可得價格覆蓋 {known_prices}/{len(grid)*len(etfs)}，FX {known_fx}/{len(grid)}。日期聯集非完整交易日曆。\n"
            '原始發布時間未知，以取得時間作為保守可得界線；這是本次取得的歷史資料，不代表當年已可取得的歷史版本。'
            '配息所得分類、完整價格調整及稅費未確認時，總報酬與投資現金流保持未知。')
        identities = {i['instrument_id']: i for i in request['instruments']}
        rows = []
        for row in request['observations']:
            if identities[row['instrument_id']]['asset_type'] == 'fx':
                continue
            state = '未調整' if available(row, request['as_of']) else '截止時不可用'
            rows.append((row['period'], '官方收盤價', row['instrument_id'], row['value'],
                identities[row['instrument_id']]['quote_currency'], state, row['source_url']))
        for row in request['fx_rates']:
            state = '銀行間參考價，非券商成交價' if available(row, request['as_of']) else '截止時不可用'
            rows.append((row['period'], '外匯收盤', 'USD/TWD', row['rate'], '1 USD = TWD', state, row['source_url']))
        for row in metadata.get('distribution_records', request['distributions']):
            note = f"基準日：{row.get('record_date') or '未知'}；支付日：{row['pay_date'] or '未知'}；所得分類未知"
            if not available(row, request['as_of']):
                note += '；截止時不可用'
            rows.append((row['ex_date'], '已公告分配', row['instrument_id'], row['amount_per_unit'], row['currency'], note, row['source_url']))
        for row in metadata.get('splits', []):
            note = '精確分割倍數未知；不由參考價格推算'
            if not available(row, request['as_of']):
                note += '；截止時不可用'
            rows.append((row['period'], '分割參考', row['instrument_id'], row['reference_after'], 'TWD', note, row['source_url']))
        for row in sorted(rows, key=lambda r: (r[0], r[1], r[2])):
            self.tree.insert('', 'end', values=tuple('未知' if value is None else str(value) for value in row))
        grid = request['period_grid']
        for instrument in request['instruments']:
            by_date = {r['period']: r['value'] for r in request['observations']
                if r['instrument_id'] == instrument['instrument_id'] and available(r, request['as_of'])}
            first = next((by_date.get(day) for day in grid if by_date.get(day) is not None), None)
            if first is not None:
                self.ax.plot(grid, [by_date[day]/first*100 if by_date.get(day) is not None else float('nan') for day in grid],
                    label=instrument['symbol'], linewidth=1.6)
        if self.ax.lines:
            self.ax.legend(fontsize=8, loc='upper left')
            ticks = self.ax.get_xticks()
            self.ax.set_xticks(ticks[::max(1, len(ticks)//5)])
        self.ax.tick_params(axis='x', labelsize=8)
        self.ax.grid(alpha=0.16)
        self.figure.tight_layout()
        self.canvas.draw_idle()
