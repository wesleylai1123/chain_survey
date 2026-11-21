"""Official ETF valuation facts and independent total-return reference coverage."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from core.multi_asset.adapters import timestamp
from core.multi_asset.official_context import reference_rows, valuation_rows


REFERENCE_NAMES = {
    'TWSE.TAI50.TR': '臺灣50報酬指數（TWSE.TAI50.TR）',
    'TWSE.TAIEX.TR': '發行量加權股價報酬指數（TWSE.TAIEX.TR）',
}
AVAILABILITY = {
    'AVAILABLE': '可用',
    'PARTIAL_COVERAGE': '僅涵蓋部分研究日期',
    'NO_SUPPLIED_OBSERVATIONS': '來源未提供資料',
    'NO_USABLE_OBSERVATIONS': '研究日期內無可用資料',
    'UNAVAILABLE_AS_OF': '截止時不可用',
    'OUTSIDE_PERIOD_GRID': '淨值日期在研究期間外',
    'NAV_MISSING': '缺少淨值',
    'NAV_INVALID': '淨值無效',
    'NAV_UNAVAILABLE_AS_OF': '淨值在截止時不可用',
    'NAV_CONFLICT': '淨值紀錄互相衝突',
    'PRICE_MISSING': '缺少同日收盤價',
    'PRICE_INVALID': '同日收盤價無效',
    'PRICE_UNAVAILABLE_AS_OF': '同日收盤價在截止時不可用',
    'PRICE_CONFLICT': '同日收盤價紀錄互相衝突',
    'CURRENCY_UNKNOWN': '原幣資料不全',
    'CURRENCY_MISMATCH': '淨值與收盤價原幣不同',
    'CALCULATION_NONFINITE': '折溢價超出可計算範圍',
}
EMPTY = '尚未載入研究資料。可擷取包含 ETF 淨值與報酬指數的官方快照，或載入已保存的快照。'
NO_CONTEXT = '這份資料檔未包含可顯示的 ETF 淨值與報酬指數。可在擷取官方資料時勾選這兩項資料。'
CONTEXT_NOTE = (
    '淨值只列來源提供的最新日期。折溢價是收盤估值比率（同日同幣別收盤價 ÷ 淨值 − 1），用途限於估值。\n'
    '下方報酬指數供獨立研究參考。ETF 自身報酬須依基金資料計算，基金契約基準須另行查證。'
    '指數限於供應日期，涵蓋筆數的分母採用 ETF 日期聯集，交易日曆完整性未驗證。\n'
    '本頁呈現本次擷取快照。原始發布時間未知，按取得時間判定資料可得性。'
    'ETF 總報酬需完整的價格調整與配息資料，'
    '稅費後現金流另需分配分類與稅費資料。'
)


class ETFContextView(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=12)
        self.banner = tk.StringVar(master=self, value=EMPTY)
        ttk.Label(self, textvariable=self.banner, wraplength=980, foreground='#176b78',
                  justify='left').pack(anchor='w', pady=(0, 14))
        self.nav = self._table('ETF 淨值與收盤折溢價', (
            ('資產', 88), ('淨值日期', 106), ('淨值', 76), ('淨值原幣', 76), ('同日收盤價', 98),
            ('折溢價', 76), ('可得狀態', 196), ('淨值來源網址', 362), ('收盤價來源網址', 610),
        ))
        self.reference = self._table('獨立研究參考指數', (
            ('報酬指數', 300), ('供應起日', 102), ('供應迄日', 102), ('可用 / 聯集日期', 116),
            ('幣別', 65), ('報酬基礎', 138), ('可得狀態', 180), ('指數來源網址', 368),
        ))

    def _table(self, title, columns):
        ttk.Label(self, text=title, font=('Segoe UI', 11, 'bold')).pack(anchor='w', pady=(0, 5))
        frame = ttk.Frame(self)
        frame.pack(fill='both', expand=True, pady=(0, 14))
        tree = ttk.Treeview(frame, columns=[name for name, _ in columns], show='headings', height=4)
        for name, width in columns:
            tree.heading(name, text=name, anchor='w')
            tree.column(name, width=width, stretch=False)
        vertical = ttk.Scrollbar(frame, orient='vertical', command=tree.yview)
        horizontal = ttk.Scrollbar(frame, orient='horizontal', command=tree.xview)
        tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        tree.grid(row=0, column=0, sticky='nsew')
        vertical.grid(row=0, column=1, sticky='ns')
        horizontal.grid(row=1, column=0, sticky='ew')
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        return tree

    def clear(self):
        for tree in (self.nav, self.reference):
            tree.delete(*tree.get_children())
        self.banner.set(EMPTY)

    @staticmethod
    def _insert(tree, values):
        tree.insert('', 'end', values=tuple('—' if value is None else str(value) for value in values))

    def render(self, request):
        self.clear()
        valuations, references = valuation_rows(request), reference_rows(request)
        if not valuations and not references:
            self.banner.set(NO_CONTEXT)
            return
        banner = CONTEXT_NOTE
        try:
            timestamp(request.get('as_of'))
        except ValueError:
            banner = '截止時間格式不完整或無效，目前無法使用資料計算折溢價或指數覆蓋。\n' + banner
        self.banner.set(banner)

        for row in valuations:
            ratio = row['premium_discount']
            self._insert(self.nav, (
                row['instrument_id'], row['period'], row['nav'], row['currency'], row['close'],
                f'{ratio:.2%}' if ratio is not None else None,
                AVAILABILITY[row['reason']], row['nav_source_url'], row['price_source_url'],
            ))

        instruments = {item['instrument_id']: item for item in request['instruments']}
        for row in references:
            identity = row['instrument_id']
            instrument = instruments[identity]
            self._insert(self.reference, (
                REFERENCE_NAMES[identity], row['supplied_start'], row['supplied_end'],
                f"{row['available_count']}/{row['grid_count']}", instrument['quote_currency'],
                '含息報酬指數', AVAILABILITY[row['reason']], row['source_url'],
            ))
