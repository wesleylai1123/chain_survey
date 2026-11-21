"""Comparative research UI. Launches empty; data must have explicit provenance."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, ttk
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from core.multi_asset.adapters import load_csv_bundle, load_request, validate_request
from core.multi_asset.context import build_research_context
from core.multi_asset.service import run_research
from core.multi_asset.official_capture import capture_official_data, load_capture
from app.etf_context_view import ETFContextView
from app.official_data_view import OfficialDataView

ROOT = Path(__file__).resolve().parents[1]
LABELS = {
    'total_return': '總報酬', 'annualized_return': '年化報酬', 'cagr': '年化報酬',
    'max_drawdown': '最大回撤', 'volatility': '年化波動', 'annualized_volatility': '年化波動',
    'sharpe': 'Sharpe', 'sortino': 'Sortino', 'sharpe_ratio': 'Sharpe', 'sortino_ratio': 'Sortino', 'tracking_difference': '追蹤差異',
    'tracking_error': '追蹤誤差', 'expense_ratio': '費用率', 'active_return': '主動報酬',
    'alpha': 'CAPM Alpha', 'capm_alpha': 'CAPM Alpha', 'information_ratio': '資訊比率',
    'distribution_yield': '過去 12 個月配息率', 'distribution_cv': '配息變異係數',
    'terminal_wealth': '期末資產與現金', 'net_cash_flow': '稅費後現金流',
    'net_paid_cash': '稅費後已付現金', 'gross_paid_cash': '已付現金總額',
    'paid_distribution_yield': '過去 12 個月配息率', 'paid_income_yield': '過去 12 個月收益率',
    'payout_cv': '分配金額變異係數', 'payout_cut_frequency': '減配頻率',
    'return_of_capital_cash': '還本現金', 'earned_income_cash': '收益現金',
}


def display(value):
    if value is None:
        return '未知 / 不足'
    if isinstance(value, float):
        return f'{value:.5g}'
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


class MultiAssetLab(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('chain_survey · 跨資產與 ETF 研究')
        self.geometry('1480x960')
        self.minsize(1080, 760)
        self.configure(bg='#edf2f7')
        self.request = self.result = self.context = self.lineage = None
        self.generation = 0
        self.pending = queue.Queue()
        self.source_pending = queue.Queue()
        self.source_busy = False
        self.busy = False
        self.tables, self.details = {}, {}
        self.status = tk.StringVar(value='載入有來源與發布時間的研究資料，開始比較股票、ETF 與 FX。')
        self.objective = tk.StringVar(value='accumulation')
        self.currency = tk.StringVar(value='USD')
        self.cutoff = tk.StringVar()
        self.engine = tk.StringVar(value=os.environ.get('INVEST_BACKTEST_REPO', str(ROOT.parent/'invest_backtest')))
        self._build()
        self.updating_settings = False
        for variable in (self.objective, self.currency, self.cutoff):
            variable.trace_add('write', lambda *_: self.settings_changed())

    def _build(self):
        style = ttk.Style(self)
        if 'clam' in style.theme_names():
            style.theme_use('clam')
        style.configure('TFrame', background='#edf2f7')
        style.configure('TLabel', background='#edf2f7', foreground='#24364b', font=('Segoe UI', 10))
        style.configure('Title.TLabel', font=('Segoe UI', 23, 'bold'), foreground='#112d46')
        style.configure('Sub.TLabel', foreground='#50677d')
        style.configure('TNotebook.Tab', padding=(15, 9))
        style.configure('Treeview', rowheight=28, font=('Segoe UI', 10))
        body = ttk.Frame(self, padding=22)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text='跨資產研究  /  ETF Research', style='Title.TLabel').pack(anchor='w')
        ttk.Label(body, text='股票 × 指數型 ETF × 主動型 ETF × 外匯  ·  同一基準幣別，分開看資產成長與可支用現金', style='Sub.TLabel').pack(anchor='w', pady=(4, 16))
        toolbar = ttk.Frame(body)
        toolbar.pack(fill='x')
        ttk.Button(toolbar, text='載入研究資料…', command=self.load_file).pack(side='left', padx=(0, 14))
        self.source_button = ttk.Button(toolbar, text='擷取官方資料…', command=self.open_source_dialog)
        self.source_button.pack(side='left', padx=(0, 14))
        ttk.Label(toolbar, text='投資目標').pack(side='left')
        self.objective_control = ttk.Combobox(toolbar, textvariable=self.objective, state='readonly', width=15,
            values=('accumulation', 'income'))
        self.objective_control.pack(side='left', padx=(6, 14))
        self.objective_control.bind('<<ComboboxSelected>>', self.settings_changed)
        ttk.Label(toolbar, text='基準幣別').pack(side='left')
        control = ttk.Combobox(toolbar, textvariable=self.currency, width=7, values=('USD', 'TWD', 'EUR', 'JPY', 'GBP'))
        control.pack(side='left', padx=(6, 14))
        control.bind('<<ComboboxSelected>>', self.settings_changed)
        control.bind('<FocusOut>', self.settings_changed)
        ttk.Label(toolbar, text='資料截止').pack(side='left')
        control = ttk.Entry(toolbar, textvariable=self.cutoff, width=27)
        control.pack(side='left', padx=6)
        control.bind('<FocusOut>', self.settings_changed)
        self.run_button = ttk.Button(toolbar, text='執行比較', command=self.calculate)
        self.run_button.pack(side='right')
        engine_row = ttk.Frame(body)
        engine_row.pack(fill='x', pady=(8, 0))
        ttk.Label(engine_row, text='計算服務位置', style='Sub.TLabel').pack(side='left')
        ttk.Entry(engine_row, textvariable=self.engine).pack(side='left', fill='x', expand=True, padx=8)
        ttk.Button(engine_row, text='選擇資料夾…', command=self.choose_engine).pack(side='right')
        ttk.Label(body, textvariable=self.status, wraplength=1350, foreground='#176b78').pack(anchor='w', pady=(12, 10))
        self.book = ttk.Notebook(body)
        self.book.pack(fill='both', expand=True)
        pages = {}
        for key, title in [('comparison', '資產比較'), ('cash', '配息與現金流'), ('rolling', '滾動報酬'),
            ('correlation', '相關性 / OOS / 市場狀態'), ('exposure', '持股與外匯曝險'),
            ('evidence', '指標與研究證據'), ('quality', '資料品質與假設')]:
            page = ttk.Frame(self.book, padding=12)
            self.book.add(page, text=title)
            pages[key] = page
        ttk.Label(pages['comparison'], text='Accumulation：配息再投入   ·   Income：保留現金   ·   總報酬不等於配息率；比率以小數表示（0.05 = 5%）', style='Sub.TLabel').pack(anchor='w', pady=(0, 10))
        self._table(pages['comparison'], 'comparison', ['資產', '類別 / 管理', '計價幣別', '總報酬', '最大回撤', '年化波動', 'Sharpe', 'Sortino'], height=6)
        self.figure = Figure(figsize=(11, 2.6), dpi=100, facecolor='#edf2f7')
        self.ax = self.figure.add_subplot(111)
        self.ax.set_title('Load sourced data to compare return paths', fontsize=11)
        self.ax.set_ylabel('Reinvested wealth (100)')
        self.figure.tight_layout()
        self.canvas = FigureCanvasTkAgg(self.figure, master=pages['comparison'])
        self.canvas.get_tk_widget().pack(fill='both', expand=True, pady=(8, 8))
        self._table(pages['comparison'], 'metrics', ['指標', '資產', '數值', '不可用原因'], height=5)
        ttk.Label(pages['cash'], text='支付日現金使用當日匯率；未知稅率或費用顯示未知。所有現金金額以基準幣別表示。', style='Sub.TLabel').pack(anchor='w', pady=(0, 10))
        self._table(pages['cash'], 'cash_summary', ['資產', '稅前已付現金', '稅費後已付現金', '配息率（12月）', '收益率（12月）', '期末資產與現金'], height=5)
        self._table(pages['cash'], 'cash', ['資產', '除息日', '支付日', '分配類別', '每單位（原幣）', '稅前現金', '稅費後現金', '狀態 / 原因'], height=11)
        self._text(pages['cash'], 'cash', height=5)
        self._table(pages['rolling'], 'rolling', ['資產', '起始', '結束', '視窗', '總報酬'], height=17)
        self._table(pages['correlation'], 'correlation', ['資產 A', '資產 B', '樣本數', '全樣本相關', '訓練期', 'OOS', '狀態 / 原因'], height=11)
        self._text(pages['correlation'], 'correlation', height=12)
        self._table(pages['exposure'], 'exposure', ['資產', '類別', '曝險 / Coverage', '權重 / Loading'], height=17)
        self._text(pages['exposure'], 'exposure', height=5)
        self._table(pages['evidence'], 'evidence', ['指標 / 情境', '時間分類', '相對目標', '狀態 / 來源'], height=15)
        self._text(pages['evidence'], 'evidence', height=8)
        self._text(pages['quality'], 'quality', height=30)
        self.official = OfficialDataView(self.book)
        self.book.add(self.official, text='官方原始資料')
        self.tables['official'] = self.official.tree
        self.source_banner = self.official.banner
        self.etf_context = ETFContextView(self.book)
        self.book.add(self.etf_context, text='淨值與基準')
        self.tables['etf_nav'] = self.etf_context.nav
        self.tables['etf_reference'] = self.etf_context.reference

    def _table(self, parent, key, columns, height):
        frame = ttk.Frame(parent)
        frame.pack(fill='both', expand=True)
        tree = ttk.Treeview(frame, columns=columns, show='headings', height=height)
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=150 if len(columns) > 3 else 350, minwidth=110, stretch=True)
        scroll = ttk.Scrollbar(frame, command=tree.yview)
        horizontal = ttk.Scrollbar(frame, orient='horizontal', command=tree.xview)
        tree.configure(yscrollcommand=scroll.set, xscrollcommand=horizontal.set)
        tree.grid(row=0, column=0, sticky='nsew')
        scroll.grid(row=0, column=1, sticky='ns')
        horizontal.grid(row=1, column=0, sticky='ew')
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.tables[key] = tree

    def _text(self, parent, key, height):
        frame = ttk.Frame(parent)
        frame.pack(fill='both', expand=True, pady=(8, 0))
        text = tk.Text(frame, height=height, wrap='word', font=('Segoe UI', 10), bg='#fff', fg='#24364b', relief='flat', padx=12, pady=10)
        scroll = ttk.Scrollbar(frame, command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        self.details[key] = text

    def choose_engine(self):
        directory = filedialog.askdirectory(title='選擇 invest_backtest 資料夾')
        if directory:
            self.engine.set(directory)

    def _clear(self):
        for tree in self.tables.values():
            tree.delete(*tree.get_children())
        for detail in self.details.values():
            detail.delete('1.0', 'end')
        self.ax.clear()
        self.ax.set_ylabel('Reinvested wealth (100)')
        self.canvas.draw_idle()
        self.official.clear()
        self.etf_context.clear()

    def _render_official_facts(self):
        self.official.render(self.request, self.lineage)
        self.etf_context.render(self.request)

    def set_request(self, request, lineage):
        validate_request(request)
        self.request, self.lineage = copy.deepcopy(request), lineage
        self.context = build_research_context(request)
        self.result = None
        self.generation += 1
        self.updating_settings = True
        try:
            self.objective.set(request['objective'])
            self.currency.set(request['base_currency'])
            self.cutoff.set(request['as_of'])
        finally:
            self.updating_settings = False
        self._clear()
        self.status.set(f"已載入 {len(request['instruments'])} 個資產；請執行比較。缺漏資料會保留並標示。")
        self._render_official_facts()
        if request.get('adapter_lineage', {}).get('kind') == 'TAIWAN_OFFICIAL_AS_ACQUIRED':
            self.status.set('已載入官方歷史快照：ETF 原始價格未調整，配息分類與總報酬不推估。詳見「官方原始資料」。')

    def load_file(self):
        path = filedialog.askopenfilename(title='載入研究 JSON 或 CSV bundle manifest', filetypes=[('Research JSON', '*.json')])
        if not path:
            return
        try:
            metadata = json.loads(Path(path).read_text(encoding='utf-8-sig'))
            loader = load_capture if metadata.get('contract') == 'TaiwanOfficialCaptureV1' else (
                load_csv_bundle if 'request' in metadata and 'files' in metadata else load_request)
            self.set_request(*loader(path))
        except Exception as exc:
            self.request = self.result = self.context = None
            self.generation += 1
            self._clear()
            self.status.set(f'無法載入：{exc}')

    def settings_changed(self, event=None):
        if self.updating_settings:
            return
        if self.request is None:
            if self.source_busy:
                self.generation += 1
            return
        changes = dict(objective=self.objective.get(), base_currency=self.currency.get().strip(), as_of=self.cutoff.get().strip())
        if any(self.request.get(k) != v for k, v in changes.items()):
            self.request.update(changes)
            self.result = None
            self.generation += 1
            self._clear()
            self.status.set('設定已變更；請重新執行比較。')
            self._render_official_facts()

    def calculate(self):
        if self.request is None:
            self.status.set('請先載入研究資料。')
            return
        if self.busy or self.source_busy:
            return
        self.settings_changed()
        try:
            validate_request(self.request)
            self.context = build_research_context(self.request)
        except ValueError as exc:
            self.status.set(f'資料檢查失敗：{exc}')
            return
        request, generation, engine = copy.deepcopy(self.request), self.generation, self.engine.get()
        self.busy = True
        self.run_button.configure(state='disabled')
        self.status.set('正在對齊資料並計算；缺值不補造，市場狀態僅用當時可得紀錄。')
        def worker():
            try:
                self.pending.put((generation, run_research(request, engine), None))
            except Exception as exc:
                self.pending.put((generation, None, str(exc)))
        threading.Thread(target=worker, daemon=True).start()
        self.after(80, self._poll)

    def _poll(self):
        try:
            generation, result, error = self.pending.get_nowait()
        except queue.Empty:
            self.after(80, self._poll)
            return
        self.busy = False
        self.run_button.configure(state='normal')
        if generation != self.generation:
            self.status.set('資料或設定已變更，已略過舊計算結果；請重新執行。')
        elif error:
            self.result = None
            self._clear()
            self.status.set(f'計算未完成：{error}')
            self._render_official_facts()
        else:
            self.render_result(result)

    def _put(self, key, rows):
        tree = self.tables[key]
        for row in rows:
            tree.insert('', 'end', values=tuple(display(v) for v in row))

    def _detail(self, key, value):
        self.details[key].insert('end', value if isinstance(value, str) else json.dumps(value, indent=2, ensure_ascii=False, default=str))

    def render_result(self, result):
        self._clear()
        self.result = result
        identities = {i['instrument_id']: i for i in self.request['instruments']}
        for row in result['instruments']:
            iid, metrics = row['instrument_id'], row['metrics']
            ins = identities[iid]
            self._put('comparison', [(iid, f"{ins['asset_type']} / {ins['management_style']}", ins['quote_currency'],
                metrics.get('total_return'), metrics.get('max_drawdown'), metrics.get('volatility', metrics.get('annualized_volatility')),
                metrics.get('sharpe_ratio', metrics.get('sharpe')), metrics.get('sortino_ratio', metrics.get('sortino')))])
            self._put('metrics', [(LABELS.get(key, key), iid, value, row['unavailable'].get(key, '')) for key, value in metrics.items()])
            self._put('cash_summary', [(iid, metrics.get('gross_paid_cash'), metrics.get('net_paid_cash'),
                metrics.get('paid_distribution_yield'), metrics.get('paid_income_yield'), metrics.get('terminal_wealth'))])
            self._put('cash', [(iid, cash.get('ex_date'), cash.get('pay_date'), cash.get('distribution_type'),
                cash.get('amount_per_unit'), cash.get('gross_cash'), cash.get('net_cash'), cash.get('reason') or cash.get('status')) for cash in row['cash_flows']])
            self._put('rolling', [(iid, r.get('start'), r.get('end'), r.get('window'), r.get('value')) for r in row['rolling_returns']])
            dates, values, wealth, valid = [], [], 100.0, True
            for r in row['returns']:
                if not dates:
                    dates.append(r['start']); values.append(wealth)
                if r.get('value') is None:
                    valid = False
                if valid:
                    wealth *= 1 + r['value']
                dates.append(r['end']); values.append(wealth if valid else float('nan'))
            if dates:
                self.ax.plot(dates, values, label=iid, linewidth=1.7)
        self.ax.set_ylabel('Reinvested wealth (100)')
        self.ax.set_title(f"{self.request['base_currency']} · total-return comparison (gaps stop compounding)", fontsize=10)
        self.ax.grid(alpha=0.16)
        if self.ax.lines:
            self.ax.legend(fontsize=8, loc='upper left')
            ticks = self.ax.get_xticks()
            if len(ticks) > 6:
                self.ax.set_xticks(ticks[::max(1, len(ticks)//5)])
        self.ax.tick_params(axis='x', labelsize=8)
        self.figure.tight_layout()
        self.canvas.draw_idle()
        self._put('correlation', [(r.get('left'), r.get('right'), r.get('sample_size'),
            r.get('full', {}).get('value'), r.get('train', {}).get('value'), r.get('oos', {}).get('value'),
            r.get('oos', {}).get('reason') or '描述性檢查；非因果證明') for r in result.get('correlations', [])])
        self._detail('correlation', '相關不代表因果；OOS 為按時間切割的描述性檢查，未自動升級為有效 driver。\n\n')
        for row in result.get('correlations', []):
            self._detail('correlation', f"\n{row.get('left')} × {row.get('right')}\n")
            for regime, detail in row.get('regimes', {}).items():
                self._detail('correlation', f"  {regime}: n={detail.get('sample_size')}, correlation={display(detail.get('value'))}; {detail.get('reason') or ''}\n")
        context = self.context or build_research_context(self.request)
        for row in context['exposures']:
            iid = row['instrument_id']
            self._put('exposure', [(iid, '揭露覆蓋', row['status'], row['coverage'])])
            for kind in ('securities', 'sectors', 'currencies', 'factors'):
                self._put('exposure', [(iid, kind, key, value) for key, value in row[kind].items()])
        self._detail('exposure', '未揭露部位保留 UNKNOWN。ETF 計價幣別不代表底層幣別；未揭露避險與衍生品不推估。\n\n')
        for ins in self.request['instruments']:
            if ins['asset_type'] == 'fx':
                self._detail('exposure', f"{ins['instrument_id']}: 1 {ins.get('fx_base_currency')} = spot × {ins.get('fx_quote_currency')}；未含利差、槓桿與展期。\n")
        self._put('evidence', [(r['indicator_id'], r['timing_class'], r['relative_to'], r['validation_status']) for r in context['indicators']])
        for scenario, rows in context['scenarios'].items():
            self._put('evidence', [(scenario + ' / ' + r['indicator_id'], '獨立情境', r['relative_to'], r.get('status', '') + ' ' + r['source_url']) for r in rows])
            if not rows:
                self._put('evidence', [(scenario, '未提供可用證據', '', 'INSUFFICIENT')])
        self._detail('evidence', context['limitations'])
        self._detail('evidence', '\n\nDriver / Model 參考：' + display(context['model_references']) + '\nSensitivity：未校準；持股權重不轉成 EPS beta。')
        self._detail('evidence', '\n\n既有公司敏感度研究參考：' + display(context['sensitivity_references']))
        assumptions = self.request['cash_flow_assumptions']
        self._detail('cash', f"目標：{self.request['objective']}　初始資金：{display(assumptions['initial_capital'])} {self.request['base_currency']}\n"
            f"情境假設｜預扣稅率：{display(assumptions['withholding_tax_rate'])}　分配費率：{display(assumptions['distribution_fee_rate'])}　換匯費率：{display(assumptions['fx_fee_rate'])}\n"
            f"買入費率：{display(assumptions['buy_fee_rate'])}　再投入費率：{display(assumptions['reinvest_fee_rate'])}\n"
            '未知稅費不視為零；統一稅率僅為使用者情境。還本分配不稱為收益，費用率不重複扣除；未估算賣出清算所得稅。')
        self._detail('quality', {'cutoff': self.request['as_of'], 'base_currency': self.request['base_currency'],
            'input_sha256': result.get('input_sha256'), 'adapter_lineage': self.lineage,
            'quality': result.get('quality'), 'methodology': result.get('methodology'),
            'instruments': [{k: r[k] for k in ('instrument_id', 'quality', 'unavailable')} for r in result['instruments']]})
        self.status.set(f"比較完成  ·  {len(result['instruments'])} 個資產  ·  {self.request['objective']}  ·  {self.request['base_currency']}  ·  缺值與假設請見「資料品質」。")
        self._render_official_facts()

    def open_source_dialog(self):
        if self.busy or self.source_busy:
            self.status.set('目前工作尚未完成；請稍候再擷取官方資料。')
            return
        dialog = tk.Toplevel(self)
        dialog.title('台股 ETF / USD-TWD 官方資料')
        dialog.geometry('590x330')
        frame = ttk.Frame(dialog, padding=18)
        frame.pack(fill='both', expand=True)
        today = datetime.now(ZoneInfo('Asia/Taipei')).date()
        symbols = tk.StringVar(value='0050,00981A')
        start = tk.StringVar(value=(today-timedelta(days=90)).isoformat())
        end = tk.StringVar(value=(today-timedelta(days=1)).isoformat())
        currency = tk.StringVar(value=self.currency.get() if self.currency.get() in {'TWD', 'USD'} else 'TWD')
        include_context = tk.BooleanVar(master=dialog, value=True)
        for row, (label, variable, choices) in enumerate([
            ('比較範例代號', symbols, ('0050,00981A', '0050', '00981A')),
            ('起日 YYYY-MM-DD', start, None), ('迄日 YYYY-MM-DD', end, None),
            ('報告幣別', currency, ('TWD', 'USD'))]):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky='w', pady=5)
            widget = ttk.Combobox(frame, textvariable=variable, values=choices, state='readonly') if choices else ttk.Entry(frame, textvariable=variable)
            widget.grid(row=row, column=1, sticky='ew', padx=(12, 0))
        frame.columnconfigure(1, weight=1)
        ttk.Checkbutton(frame, text='一併擷取 ETF 淨值與報酬指數', variable=include_context).grid(
            row=4, column=0, columnspan=2, sticky='w', pady=(10, 0))
        ttk.Label(frame, text='證交所與中央銀行提供原始價格及市場資料，ETF 淨值來自投信投顧公會。'
                  '擷取會保存原始回應及取得時間，原始價格區間最多 24 個月。'
                  '價格調整與配息所得分類需另外確認。', wraplength=540, justify='left').grid(
            row=5, column=0, columnspan=2, sticky='w', pady=14)
        def begin():
            args = (symbols.get().split(','), start.get(), end.get(), currency.get())
            include_etf_context = include_context.get()
            dialog.destroy()
            self.start_source_capture(*args, include_etf_context=include_etf_context)
        ttk.Button(frame, text='擷取並保存官方快照', command=begin).grid(row=6, column=0, columnspan=2, sticky='e')

    def start_source_capture(self, symbols, start, end, currency, *, include_etf_context=False):
        if self.busy or self.source_busy:
            return
        generation = self.generation
        self.source_busy = True
        self.source_button.configure(state='disabled')
        self.run_button.configure(state='disabled')
        self.status.set('擷取官方資料中；如已有資料，仍顯示上一份快照。原始回應會逐筆保存。')
        def worker():
            try:
                manifest = capture_official_data(symbols, start, end, ROOT/'artifacts/official-data',
                                                 base_currency=currency, include_etf_context=include_etf_context)
                request, lineage = load_capture(manifest)
                self.source_pending.put((generation, request, lineage, None))
            except Exception as exc:
                self.source_pending.put((generation, None, None, str(exc)))
        threading.Thread(target=worker, daemon=True).start()
        self.after(80, self._poll_source)

    def _poll_source(self):
        try:
            generation, request, lineage, error = self.source_pending.get_nowait()
        except queue.Empty:
            self.after(80, self._poll_source)
            return
        self.source_busy = False
        self.source_button.configure(state='normal')
        self.run_button.configure(state='normal')
        if generation != self.generation:
            self.status.set('資料或設定已變更，已略過舊的官方擷取結果；快照仍已保存在資料夾。')
        elif error:
            self.status.set(f'官方資料擷取失敗，保留原有資料與最後成功快照：{error}')
        else:
            self.set_request(request, lineage)
            self.book.select(self.official)


def launch_multi_asset_lab():
    MultiAssetLab().mainloop()
