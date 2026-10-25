"""Desktop reader of ABFCompanySurveyV1. Controls never estimate or refit evidence."""
from __future__ import annotations

from datetime import date
import tkinter as tk
from tkinter import ttk
import webbrowser

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import matplotlib.dates as mdates
from matplotlib import font_manager

from core.abf_company_survey_html import (
    company_brief, detail_text, fact_value, latest_gross_margin_fact,
    metric_label, monthly_segments, number, scatter_points, source_link, trend_series,
)

BG, INK, MUTED = '#F3F6FA', '#17283E', '#64758B'
BLUE, TEAL, AMBER = '#2563B4', '#087F8C', '#D98B29'
_AVAILABLE_FONTS = {font.name for font in font_manager.fontManager.ttflist}
FONT = next((name for name in ('Microsoft JhengHei', 'Noto Sans CJK TC', 'Noto Sans CJK JP',
                               'WenQuanYi Zen Hei') if name in _AVAILABLE_FONTS), 'DejaVu Sans')


class CompanySurveyView(ttk.Frame):
    """A responsive nested notebook with read-only charts and linked evidence.

    Public selection variables hold canonical IDs. ``render`` refreshes all
    sections; ``redraw`` only refreshes charts. Neither method touches the audit.
    """

    def __init__(self, parent, report: dict):
        super().__init__(parent)
        self.report = report
        self.company_var = tk.StringVar(self, report['companies'][0]['company'])
        self.scenario_var = tk.StringVar(self, 'UPSIDE')
        self.metric_var = tk.StringVar(self, report['companies'][0]['scenarios']['UPSIDE']['options'][0]['metric_id'])
        self.feature_var = tk.StringVar(self, 'LEVEL')
        self.target_var = tk.StringVar(self, 'LEVEL')
        self._company_label_var = tk.StringVar(self)
        self._metric_label_var = tk.StringVar(self)
        self._build()
        self.render()

    @property
    def selected_company(self) -> dict:
        return next(c for c in self.report['companies'] if c['company'] == self.company_var.get())

    @property
    def selected_detail(self) -> dict | None:
        return next((d for d in self.selected_company['details'].values()
                     if (d['scenario'], d['metric_id'], d['feature_transform'], d['target_transform']) ==
                     (self.scenario_var.get(), self.metric_var.get(), self.feature_var.get(), self.target_var.get())), None)

    def _build(self):
        overview = ttk.Frame(self, padding=(12, 8))
        overview.pack(fill='x')
        for i, company in enumerate(self.report['companies']):
            gm = latest_gross_margin_fact(company)
            text = f"{company['name']} {company['stock_id']}   " + (number(gm['value'])+'%' if gm else 'UNAVAILABLE')
            text += '\n公司整體毛利率 · ' + (gm['observation_date'][:10] if gm else '缺少一手事實')
            ttk.Button(overview, text=text, command=lambda c=company: self._choose_company(c['company'])).grid(
                row=0, column=i, sticky='ew', padx=4)
            overview.columnconfigure(i, weight=1)
        controls = ttk.Frame(self, padding=(16, 2, 16, 8))
        controls.pack(fill='x')
        items = [('研究公司', self._company_label_var, [self._company_title(c) for c in self.report['companies']], 19),
                 ('獨立情境', self.scenario_var, ['UPSIDE', 'DOWNSIDE'], 11),
                 ('產業指標', self._metric_label_var, [], 24),
                 ('指標轉換', self.feature_var, ['LEVEL', 'CHANGE'], 10),
                 ('公司轉換', self.target_var, ['LEVEL', 'CHANGE'], 10)]
        self.controls = {}
        for i, (title, variable, values, width) in enumerate(items):
            cell = ttk.Frame(controls)
            cell.grid(row=0, column=i, sticky='ew', padx=(0, 12))
            ttk.Label(cell, text=title).pack(anchor='w')
            box = ttk.Combobox(cell, textvariable=variable, values=values, state='readonly', width=width)
            box.pack(fill='x')
            self.controls[title] = box
            box.bind('<<ComboboxSelected>>', lambda _e, key=title: self._control_changed(key))
            controls.columnconfigure(i, weight=1 if i in {0, 2} else 0)
        self.status_label = ttk.Label(self, padding=(16, 1, 16, 6), foreground='#9A5C12', wraplength=1320)
        self.status_label.pack(fill='x')
        self.book = ttk.Notebook(self)
        self.book.pack(fill='both', expand=True, padx=12, pady=(0, 10))
        summary, charts, facts, validation, finance, research = [ttk.Frame(self.book) for _ in range(6)]
        for frame, name in zip((summary, charts, facts, validation, finance, research),
                               ('研究總覽', '趨勢與相關', '一手事實與來源', '驗證明細', '財務脈絡', '研究缺口')):
            self.book.add(frame, text=name)
        self.summary_text = self._scroll_text(summary)
        self.chart_status = ttk.Label(charts, padding=8, wraplength=1320)
        self.chart_status.pack(fill='x')
        self.figure = Figure(figsize=(13, 4), dpi=90, facecolor='white', layout='constrained')
        self.trend_ax, self.scatter_ax = self.figure.subplots(1, 2)
        self.chart_canvas = FigureCanvasTkAgg(self.figure, master=charts)
        self.chart_canvas.get_tk_widget().pack(fill='both', expand=True)
        self.facts_text = self._scroll_text(facts)
        self.validation_text = self._scroll_text(validation)
        self.finance_book = ttk.Notebook(finance)
        self.finance_book.pack(fill='both', expand=True)
        finance_chart, finance_data = ttk.Frame(self.finance_book), ttk.Frame(self.finance_book)
        self.finance_book.add(finance_chart, text='公司整體財務圖')
        self.finance_book.add(finance_data, text='逐期數值與來源')
        ttk.Label(finance_chart, text='COMPANY_TOTAL · 公司整體代理值；會計口徑依各列標示，UNKNOWN 尚未確認獨立單季。',
                  padding=8, foreground='#9A5C12').pack(fill='x')
        self.finance_figure = Figure(figsize=(12, 3.8), dpi=90, facecolor='white', layout='constrained')
        self.finance_ax = self.finance_figure.subplots()
        self.finance_canvas = FigureCanvasTkAgg(self.finance_figure, master=finance_chart)
        self.finance_canvas.get_tk_widget().pack(fill='both', expand=True)
        self.finance_text = self._scroll_text(finance_data)
        self.research_text = self._scroll_text(research)

    @staticmethod
    def _company_title(company):
        return company['name'] + ' ' + company['stock_id']

    @staticmethod
    def _scroll_text(parent):
        frame = ttk.Frame(parent)
        frame.pack(fill='both', expand=True)
        text = tk.Text(frame, wrap='word', background='white', foreground=INK,
                       font=(FONT, 11), relief='flat', padx=20, pady=16, spacing3=8,
                       height=8, width=40, cursor='arrow')
        scroll = ttk.Scrollbar(frame, command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        text.pack(side='left', fill='both', expand=True)
        text.tag_configure('heading', font=(FONT, 14, 'bold'), foreground=INK, spacing1=8, spacing3=9)
        text.tag_configure('muted', foreground=MUTED, font=(FONT, 9))
        return text

    @staticmethod
    def _reset(text):
        text.configure(state='normal')
        text.delete('1.0', 'end')

    @staticmethod
    def _link(text, url, title=None):
        safe = source_link(dict(source_url=url))
        if safe is None:
            return
        tag = 'source_' + str(len(text.tag_names()))
        text.tag_configure(tag, foreground=BLUE, underline=True)
        text.tag_bind(tag, '<Button-1>', lambda _event, target=safe: webbrowser.open(target))
        text.insert('end', (title or safe)+'\n', tag)

    def _choose_company(self, company):
        self.company_var.set(company)
        self.render()

    def _control_changed(self, key):
        if key == '研究公司':
            company = next(c for c in self.report['companies'] if self._company_title(c) == self._company_label_var.get())
            self.company_var.set(company['company'])
        elif key == '產業指標':
            metric = next(m for m in self._metrics() if metric_label(m) == self._metric_label_var.get())
            self.metric_var.set(metric)
        self.render()

    def _metrics(self):
        return list(dict.fromkeys(o['metric_id'] for o in self.selected_company['scenarios'][self.scenario_var.get()]['options']))

    def render(self):
        company = self.selected_company
        metrics = self._metrics()
        if self.metric_var.get() not in metrics:
            self.metric_var.set(metrics[0])
        self._company_label_var.set(self._company_title(company))
        self.controls['產業指標'].configure(values=[metric_label(m) for m in metrics])
        self._metric_label_var.set(metric_label(self.metric_var.get()))
        counts = company['scenarios'][self.scenario_var.get()]['eligibility_counts']
        self.status_label.configure(text=f"{self._company_title(company)} × ABF · {self.scenario_var.get()} · "
            f"eligible {counts['eligible']} / support-only {counts['support-only']} / reject {counts['reject']} · "
            'LEVEL = 原始年增率 %；CHANGE = 年增率月差（百分點）；財務傳導 NOT_CALIBRATED')
        self._render_summary(company)
        self._render_facts(company)
        self._render_finance(company)
        self._render_research(company)
        self.redraw()

    def _render_summary(self, company):
        text = self.summary_text
        self._reset(text)
        text.insert('end', self._company_title(company)+' · ABF 公司研究判讀\n', 'heading')
        text.insert('end', '研究知識截止 '+self.report['as_of']+'\n報告生成 '+self.report['generated_at']+'\n', 'muted')
        for scenario, evidence in company['scenarios'].items():
            n = evidence['eligibility_counts']
            text.insert('end', f"{scenario}：可用 {n['eligible']}／僅供佐證 {n['support-only']}／未通過 {n['reject']}\n")
        facts = {f['fact_id']: f for f in company['primary_facts']}
        for line in company_brief(company):
            text.insert('end', '\n'+line['statement']+'\n')
            for fid in line['fact_ids']:
                fact = facts[fid]
                self._link(text, source_link(fact), fid+' · '+str(fact.get('document', ''))+' · p.'+str(fact.get('page', '—')))
        if not facts:
            text.insert('end', '\nUNAVAILABLE · 缺少經核對的一手公司事實。\n')
        text.insert('end', '\n營運傳導假說（尚未驗證）\n', 'heading')
        for mechanism in company.get('operating_mechanism', []):
            text.insert('end', (mechanism.get('statement_zh') or mechanism.get('statement', ''))+'\n')
            text.insert('end', mechanism.get('evidence_status', 'UNKNOWN')+' · '
                        +mechanism.get('status', 'UNVALIDATED_HYPOTHESIS')+'\n', 'muted')
            text.insert('end', '證據 ID：'+' · '.join(mechanism.get('evidence_ids', []))+'\n', 'muted')
        text.insert('end', '\n判讀界線\n', 'heading')
        text.insert('end', '產業與公司整體序列皆為 ABF 代理值。相關性不代表因果，亦不足以識別 ABF 產品營收、毛利或 EPS。\n'
                    '一手文件可供當期閱讀；發布時間未驗證者為 PIT_UNAVAILABLE，無法用來證明歷史時點已公開。\n'
                    'Driver → Revenue → GM → EPS：NOT_CALIBRATED，β = null。\n')
        text.configure(state='disabled')

    def _render_facts(self, company):
        text = self.facts_text
        self._reset(text)
        detail = self.selected_detail
        self._reset(self.validation_text)
        self.validation_text.insert('end', '當前比較 · 驗證資格與固定 OOS\n', 'heading')
        self.validation_text.insert('end', detail_text(detail) if detail else 'UNAVAILABLE · 缺少選定比較')
        self.validation_text.configure(state='disabled')
        text.insert('end', '經核對的一手事實\n', 'heading')
        text.insert('end', '本次取得／快照取得為目前封存紀錄的取得時間；歷史首次取得時間未驗證。\n', 'muted')
        if not company['primary_facts']:
            text.insert('end', 'UNAVAILABLE · 缺少經核對的一手事實\n')
        for fact in company['primary_facts']:
            text.insert('end', metric_label(fact['metric_id'])+' · '+fact_value(fact)+'\n', 'heading')
            text.insert('end', fact.get('statement', '')+'\n')
            text.insert('end', f"{fact['source_scope']} · {fact['evidence_status']} · {fact['data_status']} · "
                        +('前瞻展望，非實績' if fact.get('is_forward_looking') else '歷史／當期觀察')+'\n')
            text.insert('end', fact['fact_id']+'\n', 'muted')
            for label, key in [('觀察', 'observation_date'), ('發布', 'release_date'), ('可取得', 'available_at'),
                               ('訊號生成', 'signal_generated_at'), ('本次取得／快照取得', 'acquired_at')]:
                text.insert('end', label+'：'+str(fact.get(key) or 'null · 未驗證')+'\n', 'muted')
            self._link(text, source_link(fact), str(fact.get('document', '來源'))+' · p.'+str(fact.get('page', '—')))
        text.insert('end', '\n全部引用來源\n', 'heading')
        for source in company['sources']:
            self._link(text, source['source_url'])
            text.insert('end', ' · '.join(source['evidence_ids'])+'\n', 'muted')
        text.configure(state='disabled')

    def _render_finance(self, company):
        text = self.finance_text
        self._reset(text)
        text.insert('end', '公司整體財務脈絡 · COMPANY_TOTAL · ABF 代理值\n', 'heading')
        text.insert('end', '會計口徑 UNKNOWN 者尚未確認為獨立單季；公告來源驗證發布時間，財務數值保留原供應商。\n')
        text.insert('end', '本次取得／快照取得為目前封存紀錄的取得時間；歷史首次取得時間未驗證。\n', 'muted')
        rows = company['financial_context']['rows']
        if not rows:
            text.insert('end', 'UNAVAILABLE · 缺少財務歷史\n')
        for row in rows:
            text.insert('end', row['report_date']+'\n', 'heading')
            pct = lambda value: '—' if value is None else number(value*100)+'%'
            text.insert('end', f"營收 {number(row['revenue'], 0)} 元 · YoY {pct(row['revenue_yoy'])} · "
                        f"毛利率 {pct(row['gross_margin'])} · EPS {number(row['eps'])} 元／股\n")
            text.insert('end', f"{row['accounting_basis']} · {row['data_status']} · 數值來源 {row['fundamental_source']}\n", 'muted')
            text.insert('end', row['evidence_id']+'\n', 'muted')
            for label, key in [('觀察', 'observation_date'), ('發布', 'release_date'), ('可取得', 'available_at'),
                               ('訊號生成', 'signal_generated_at'), ('本次取得／快照取得', 'acquired_at')]:
                text.insert('end', label+'：'+str(row.get(key) or 'null · 未驗證')+'\n', 'muted')
            for url in row['source_urls']:
                self._link(text, url)
        text.configure(state='disabled')

    def _render_research(self, company):
        text = self.research_text
        self._reset(text)
        text.insert('end', 'Driver → Revenue → GM → EPS\n', 'heading')
        for stage in company['financial_bridge']['stages']:
            text.insert('end', stage['stage']+'：NOT_CALIBRATED · β = null\n')
        text.insert('end', '\n優先補足的 ABF 產品輸入\n', 'heading')
        for row in company['missing_inputs']:
            value = '缺少' if row['value'] is None else number(row['value'])+' '+str(row['unit'])
            text.insert('end', f"{metric_label(row['metric_id'])}：{value} · {row['data_status']}\n")
            text.insert('end', ' · '.join(row['evidence_ids'])+'\n', 'muted')
        text.insert('end', '\n下一步研究問題\n', 'heading')
        text.insert('end', '1. 建立產品訂單、庫存、實際稼動率、ASP 及組合的可持續一手紀錄。\n'
                    '2. 上下行情境各自驗證固定時序 OOS、信賴區間、多重比較與跨公司方向。\n'
                    '3. 核對單季財務口徑及發布時間，再研究 ABF 產品財務傳導。\n')
        text.insert('end', '\n失效與撤回條件\n', 'heading')
        text.insert('end', '來源修訂改變相關方向、OOS 穩定性或不確定性門檻時，撤回原判讀。\n'
                    '產品歸因、會計口徑、發布時間或取得來源鏈無法驗證時，撤回財務歸因。\n'
                    '未通過各項門檻的產業及公司整體相關性，不轉為 ABF 預測。\n')
        text.configure(state='disabled')

    @staticmethod
    def _style_axis(ax, title, xlabel, ylabel):
        ax.set_title(title, fontsize=11, fontfamily=FONT, loc='left', color=INK)
        ax.set_xlabel(xlabel, fontsize=9, fontfamily=FONT)
        ax.set_ylabel(ylabel, fontsize=9, fontfamily=FONT)
        ax.tick_params(labelsize=8, colors=MUTED)
        ax.grid(alpha=.18)
        ax.spines[['top', 'right']].set_visible(False)

    @staticmethod
    def _time_axis(ax):
        ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=3, maxticks=7))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))

    @staticmethod
    def _plot_segments(ax, points, *, label, color, cadence=1):
        for i, segment in enumerate(monthly_segments(points, cadence=cadence)):
            ax.plot([date.fromisoformat(p['period'][:7]+'-01') for p in segment],
                    [p['value'] for p in segment], marker='o', markersize=3,
                    linewidth=1.5, color=color, label=label if i == 0 else None)

    def redraw(self):
        company, detail = self.selected_company, self.selected_detail
        self.trend_ax.clear()
        self.scatter_ax.clear()
        for series in trend_series(company, self.metric_var.get()):
            industry = series['company'] == 'INDUSTRY'
            label = metric_label(series['metric_id'])+' · INDUSTRY_AGGREGATE 代理' if industry else company['name']+'營收 YoY · COMPANY_TOTAL 代理'
            self._plot_segments(self.trend_ax, series['points'], label=label, color=BLUE if industry else TEAL)
        self._style_axis(self.trend_ax, '月度營運趨勢 · LEVEL', '觀察月份（缺月斷線，未插值）', '年增率 %')
        self._time_axis(self.trend_ax)
        if self.trend_ax.lines:
            self.trend_ax.legend(prop={'family': FONT, 'size': 8}, loc='best')
        else:
            self.trend_ax.text(.5, .5, 'UNAVAILABLE · 缺少觀察值', transform=self.trend_ax.transAxes,
                               ha='center', fontfamily=FONT, color=MUTED)
        points = scatter_points(detail) if detail else []
        valid = [p for p in points if p.get('x') is not None and p.get('y') is not None]
        if valid:
            self.scatter_ax.scatter([p['x'] for p in valid], [p['y'] for p in valid],
                                    s=22, color='#96AABD', label='完整稽核樣本')
            oos = [p for p in valid if p['is_oos']]
            if oos:
                self.scatter_ax.scatter([p['x'] for p in oos], [p['y'] for p in oos],
                                        s=35, color=AMBER, label='固定時序 OOS')
            self.scatter_ax.legend(prop={'family': FONT, 'size': 8})
        else:
            self.scatter_ax.text(.5, .5, 'UNAVAILABLE · 缺少情境樣本', transform=self.scatter_ax.transAxes,
                                 ha='center', fontfamily=FONT, color=MUTED)
        unit = lambda transform: '%' if transform == 'LEVEL' else '百分點'
        self._style_axis(self.scatter_ax, '封存稽核樣本 · '+self.scenario_var.get(),
                         metric_label(self.metric_var.get())+' ('+unit(self.feature_var.get())+')',
                         '公司整體營收代理 ('+unit(self.target_var.get())+')')
        if detail:
            self.chart_status.configure(text=f"{detail['eligibility']} · N {detail['sample_size']} · ρ {number(detail.get('spearman'), 3)} · "
                f"95% CI [{number(detail.get('bootstrap_ci_low'), 3)}, {number(detail.get('bootstrap_ci_high'), 3)}] · "
                f"p {number(detail.get('permutation_p'), 4)} · FDR q {number(detail.get('fdr_q'), 4)} · "
                f"OOS 符號 {number(detail.get('oos_sign_stability'), 2)} · 跨公司 {number(detail.get('company_sign_agreement'), 2)}\n"
                f"PIT exact {detail.get('pit_exact', False)} · {detail.get('source_scope')} → {detail.get('target_scope')} · "
                f"候選領先 {detail.get('lag_months', 1)} 個月；無擬合或預測線。")
        self.chart_canvas.draw_idle()
        self.finance_ax.clear()
        rows = company['financial_context']['rows']
        for field, label, color in [('gross_margin', '公司毛利率 · COMPANY_TOTAL 代理', TEAL),
                                    ('revenue_yoy', '公司營收 YoY · COMPANY_TOTAL 代理', BLUE)]:
            self._plot_segments(self.finance_ax,
                [dict(period=r['report_date'], value=None if r[field] is None else r[field]*100) for r in rows],
                label=label, color=color, cadence=3)
        self._style_axis(self.finance_ax, '公司整體財務脈絡 · UNKNOWN 口徑未確認為獨立單季', '報告期末', '%')
        self._time_axis(self.finance_ax)
        if self.finance_ax.lines:
            self.finance_ax.legend(prop={'family': FONT, 'size': 9})
        else:
            self.finance_ax.text(.5, .5, 'UNAVAILABLE · 缺少財務歷史', transform=self.finance_ax.transAxes,
                                 ha='center', fontfamily=FONT, color=MUTED)
        self.finance_canvas.draw_idle()
