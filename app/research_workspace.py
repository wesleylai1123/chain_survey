from __future__ import annotations

import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, font, messagebox, ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm, to_hex
from matplotlib.dates import DateFormatter
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator

from core.research_workspace import LAGS, ROLLING_WINDOW, ResearchDataset, load_default_dataset, metric_label

ROOT = Path(__file__).resolve().parents[1]
BG, WHITE, NAV = "#f3f5f7", "#ffffff", "#172429"
INK, MUTED, LINE = "#15252b", "#53646d", "#dce3e7"
TEAL, NEGATIVE = "#00766c", "#ad432f"
HEAT = LinearSegmentedColormap.from_list("study", ["#a94130", "#ffdcd0", "#f1f4f4", "#c5e8df", "#00685d"])
NORM = TwoSlopeNorm(vmin=-1, vcenter=0, vmax=1)
METHODS = {"Spearman": "spearman", "Pearson": "pearson"}
TIMES = {
    "page_publication_date": "頁面發布日",
    "regulatory_deadline_proxy": "申報期限代理",
    "page_last_update": "頁面更新日",
}


def _score(value):
    return "—" if value is None else f"{value:+.3f}"


class ResearchWorkspace(tk.Tk):
    def __init__(self, dataset: ResearchDataset | None = None):
        super().__init__()
        self.title("Chain Survey · 相關性研究")
        self.geometry("1360x850")
        self.minsize(1100, 720)
        self.configure(background=BG)
        self.report = None
        self.dataset = None
        self.samples_by_id = {}
        self.cells = {}
        self._configure_styles()
        self._build()
        try:
            self._set_dataset(dataset or load_default_dataset(ROOT))
        except (OSError, ValueError) as error:
            self.status.configure(text=str(error))
            self._empty_charts("No monthly dataset")

    def _configure_styles(self):
        family = font.nametofont("TkDefaultFont", root=self).actual("family")
        self.face = family
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", font=(family, 11))
        style.configure("Research.TFrame", background=BG)
        style.configure("Research.TNotebook", background=BG, borderwidth=0, tabmargins=0)
        style.configure("Research.TNotebook.Tab", padding=(17, 8), background="#e4eaed", foreground=MUTED)
        style.map("Research.TNotebook.Tab", background=[("selected", WHITE)], foreground=[("selected", TEAL)])
        style.configure("Research.Treeview", background=WHITE, fieldbackground=WHITE, foreground=INK,
                        rowheight=30, borderwidth=0, font=(family, 10))
        style.configure("Research.Treeview.Heading", background="#eaf0f2", foreground=INK,
                        font=(family, 10, "bold"), relief="flat")
        style.map("Research.Treeview", background=[("selected", "#d6eee8")], foreground=[("selected", INK)])
        style.configure("Research.TCombobox", padding=7, foreground=INK, fieldbackground=WHITE)
        style.map("Research.TCombobox", fieldbackground=[("readonly", WHITE)],
                  foreground=[("readonly", INK)], selectbackground=[("readonly", WHITE)],
                  selectforeground=[("readonly", INK)])
        style.configure("Primary.TButton", padding=(12, 9), background=TEAL, foreground=WHITE, borderwidth=0)
        style.map("Primary.TButton", background=[("active", "#005d54"), ("disabled", "#547470")])
        style.configure("Quiet.TButton", padding=(10, 7), background="#e8edef", foreground=INK, borderwidth=0)
        style.map("Quiet.TButton", background=[("active", "#d9e4e7")])

    def _label(self, parent, text="", *, size=11, fg=INK, bg=WHITE, bold=False,
               anchor="w", justify="left", **kwargs):
        return tk.Label(parent, text=text, fg=fg, bg=bg, justify=justify, anchor=anchor,
                        font=(self.face, size, "bold" if bold else "normal"), **kwargs)

    def _build(self):
        top = tk.Frame(self, bg=NAV, height=54)
        top.pack(fill="x")
        top.pack_propagate(False)
        self._label(top, "CHAIN SURVEY", size=14, bold=True, fg=WHITE, bg=NAV).pack(side="left", padx=23, fill="y")
        self._label(top, "研究工作台", fg="#d2e0e2", bg=NAV).pack(side="left", padx=10, fill="y")
        tools = tk.Menubutton(top, text="研究工具  ▾", bg=NAV, fg=WHITE, activebackground="#263940",
                              activeforeground=WHITE, relief="flat", padx=10)
        tools.pack(side="right", padx=18, fill="y")
        menu = tk.Menu(tools, tearoff=False)
        for title, option in (
            ("進階 CSV 相關分析", "--correlation"), ("跨公司相關驗證", "--panel-correlation"),
            ("ABF 研究室", "--abf-research"), ("跨資產／ETF 研究", "--multi-asset"),
            ("公司與題材分析", "--company-explorer"),
        ):
            menu.add_command(label=title, command=lambda flag=option: self._open_tool(flag))
        tools.configure(menu=menu)

        center = ttk.Frame(self, style="Research.TFrame")
        center.pack(fill="both", expand=True)
        center.columnconfigure(1, weight=1)
        center.rowconfigure(0, weight=1)
        sidebar = tk.Frame(center, bg=WHITE, width=253, highlightthickness=1, highlightbackground=LINE)
        sidebar.grid(row=0, column=0, sticky="ns")
        sidebar.grid_propagate(False)
        sidebar.columnconfigure(0, weight=1)
        self._build_controls(sidebar)

        workspace = tk.Frame(center, bg=BG, padx=20, pady=16)
        workspace.grid(row=0, column=1, sticky="nsew")
        header = tk.Frame(workspace, bg=BG)
        header.pack(fill="x", pady=(0, 8))
        self._label(header, "相關性研究", size=24, bold=True, bg=BG).pack(side="left")
        self.dataset_badge = self._label(header, size=10, fg=MUTED, bg=BG)
        self.dataset_badge.pack(side="right")
        self.pair_label = self._label(workspace, size=12, bg=BG, fg=MUTED)
        self.pair_label.pack(fill="x", pady=(0, 12))

        metrics = tk.Frame(workspace, bg=LINE, highlightbackground=LINE, highlightthickness=1)
        metrics.pack(fill="x", pady=(0, 12))
        self.tiles = {}
        for i, (key, title) in enumerate((
            ("score", "相關係數"), ("n", "配對樣本"), ("early", "前半段"), ("late", "後半段"),
        )):
            metrics.columnconfigure(i, weight=1, uniform="metric")
            tile = tk.Frame(metrics, bg=WHITE, padx=13, pady=7)
            tile.grid(row=0, column=i, sticky="nsew", padx=(0, 1 if i < 3 else 0))
            self._label(tile, title, size=10, fg=MUTED).pack(anchor="w")
            self.tiles[key] = self._label(tile, "—", size=19, bold=True)
            self.tiles[key].pack(anchor="w")

        self.book = ttk.Notebook(workspace, style="Research.TNotebook")
        self.book.pack(fill="both", expand=True)
        pair = tk.Frame(self.book, bg=WHITE, padx=11, pady=8)
        scan = tk.Frame(self.book, bg=WHITE, padx=15, pady=10)
        evidence = tk.Frame(self.book, bg=WHITE, padx=15, pady=10)
        self.book.add(pair, text="配對分析")
        self.book.add(scan, text="領先／落後掃描")
        self.book.add(evidence, text="樣本與來源")
        self.pair_panel = pair
        self.book.bind("<<NotebookTabChanged>>", self._on_tab)
        self._build_charts(pair)
        self._build_scan(scan)
        self._build_evidence(evidence)

    def _build_controls(self, panel):
        self._label(panel, "研究設定", size=14, bold=True).grid(row=0, column=0, sticky="ew", padx=16, pady=(20, 8))
        self.x = tk.StringVar(self)
        self.y = tk.StringVar(self)
        self.method = tk.StringVar(self, value="Spearman")
        self.lag = tk.StringVar(self, value="+1")
        for i, (name, variable, options) in enumerate((
            ("X · 產業指標", self.x, ()), ("Y · 目標指標", self.y, ()),
            ("相關方法", self.method, tuple(METHODS)), ("X 領先 Y · 月", self.lag, tuple(f"{lag:+d}" for lag in LAGS)),
        )):
            self._label(panel, name, size=10, fg=MUTED, bold=True).grid(row=2*i+1, column=0, sticky="ew",
                                                                       padx=16, pady=(8, 3))
            combo = ttk.Combobox(panel, textvariable=variable, values=options, state="readonly", width=15,
                                 style="Research.TCombobox")
            combo.grid(row=2*i+2, column=0, sticky="ew", padx=16)
            if variable is self.x:
                self.x_menu = combo
            elif variable is self.y:
                self.y_menu = combo
            combo.bind("<<ComboboxSelected>>", self._input_changed)
        ttk.Button(panel, text="執行分析", style="Primary.TButton", command=self.refresh).grid(
            row=9, column=0, sticky="ew", padx=16, pady=(16, 12))
        tk.Frame(panel, bg=LINE, height=1).grid(row=10, column=0, sticky="ew", padx=16, pady=4)
        self._label(panel, "資料集", bold=True).grid(row=11, column=0, sticky="ew", padx=16, pady=(9, 3))
        self.status = self._label(panel, "載入中", size=10, fg=MUTED, wraplength=214)
        self.status.grid(row=12, column=0, sticky="ew", padx=16, pady=(0, 10))
        ttk.Button(panel, text="匯入月度資料 CSV", style="Quiet.TButton", command=self._import).grid(
            row=13, column=0, sticky="ew", padx=16)

    def _build_charts(self, parent):
        self.chart_note = self._label(parent, fg=MUTED, size=10, padx=8)
        self.chart_note.pack(side="bottom", fill="x", pady=(4, 0))
        titles = tk.Frame(parent, bg=WHITE)
        titles.pack(fill="x")
        titles.columnconfigure((0, 1), uniform="chart", weight=1)
        for i, title in enumerate(("配對散佈圖", f"滾動相關 · {ROLLING_WINDOW} 筆樣本")):
            self._label(titles, title, size=12, bold=True, padx=8).grid(row=0, column=i, sticky="ew")
        self.figure = Figure(dpi=100, figsize=(8, 4.2), facecolor=WHITE, layout="constrained")
        self.scatter, self.rolling = self.figure.subplots(1, 2)
        self.canvas = FigureCanvasTkAgg(self.figure, master=parent)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, pady=(5, 0))

    def _build_scan(self, parent):
        header = tk.Frame(parent, bg=WHITE)
        header.pack(fill="x", pady=(0, 8))
        self._label(header, "指標 × 月份落後", size=13, bold=True).pack(side="left")
        self._label(header, "負相關  −1     0     +1  正相關", size=10, fg=MUTED).pack(side="right")
        scroll_area = tk.Frame(parent, bg=WHITE)
        scroll_area.pack(fill="both", expand=True)
        self.scan_canvas = tk.Canvas(scroll_area, bg=WHITE, highlightthickness=0, width=1, height=1)
        scroll = ttk.Scrollbar(scroll_area, orient="vertical", command=self.scan_canvas.yview)
        scroll.pack(side="right", fill="y")
        self.scan_canvas.pack(side="left", fill="both", expand=True)
        self.scan_canvas.configure(yscrollcommand=scroll.set)
        self.scan_table = tk.Frame(self.scan_canvas, bg=LINE)
        window = self.scan_canvas.create_window((0, 0), window=self.scan_table, anchor="nw")
        self.scan_canvas.bind("<Configure>", lambda event: self.scan_canvas.itemconfigure(window, width=event.width))
        self.scan_table.bind("<Configure>", lambda _event: self.scan_canvas.configure(
            scrollregion=self.scan_canvas.bbox("all")))
        self.scan_note = self._label(parent, fg=MUTED, size=10, wraplength=680)
        self.scan_note.pack(fill="x", pady=(12, 0))
        self.scan_key = None

    def _build_evidence(self, parent):
        top = tk.Frame(parent, bg=WHITE)
        top.pack(fill="x", pady=(0, 8))
        self._label(top, "已對齊的月度樣本", size=13, bold=True).pack(side="left")
        ttk.Button(top, text="匯出樣本 CSV", style="Quiet.TButton", command=self._export).pack(side="right")
        self.evidence_text = tk.Text(parent, height=4, wrap="word", relief="flat", borderwidth=0,
                                     bg="#edf3f4", fg=INK, font=(self.face, 10), padx=8, pady=6)
        self.evidence_text.pack(side="bottom", fill="x", pady=(8, 0))
        self.evidence_text.configure(state="disabled")
        table = tk.Frame(parent, bg=WHITE)
        table.pack(fill="both", expand=True)
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        titles = ("X 月份", "X (%)", "X 可用日 UTC", "Y 月份", "Y (%)", "Y 可用日 UTC")
        self.tree = ttk.Treeview(table, columns=titles, show="headings", style="Research.Treeview", selectmode="browse")
        for title in titles:
            self.tree.heading(title, text=title)
            self.tree.column(title, width=95, minwidth=72, anchor="center")
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.bind("<<TreeviewSelect>>", self._show_source)

    def _set_dataset(self, dataset):
        self.dataset = dataset
        display = [metric_label(key) for key in dataset.metrics]
        self.labels = {label if display.count(label) == 1 else f"{label} [{key}]": key
                       for label, key in zip(display, dataset.metrics)}
        self.by_id = {key: label for label, key in self.labels.items()}
        self.x_menu.configure(values=tuple(self.labels))
        self.y_menu.configure(values=tuple(self.labels))
        x = "pcb_revenue_yoy" if "pcb_revenue_yoy" in dataset.metrics else dataset.metrics[0]
        y = "abf_company_revenue_yoy::3037.TW"
        if y == x or y not in dataset.metrics:
            y = next(key for key in dataset.metrics if key != x)
        self.x.set(self.by_id[x])
        self.y.set(self.by_id[y])
        self.scan_key = None
        self.dataset_badge.configure(text=f"月度變動   ·   {dataset.first_month} — {dataset.last_month}")
        self.status.configure(text=f"{dataset.label}\n{len(dataset.metrics)} 個指標\n{dataset.first_month} 至 {dataset.last_month}")
        self.refresh()

    def _import(self):
        path = filedialog.askopenfilename(parent=self, filetypes=[("CSV", "*.csv")])
        if not path:
            return
        try:
            self._set_dataset(ResearchDataset.from_csv(path, Path(path).name))
        except (OSError, ValueError) as error:
            messagebox.showerror("無法匯入資料", str(error), parent=self)

    def _input_changed(self, _event):
        self.refresh()

    def refresh(self):
        if self.dataset is None:
            return
        x, y = self.labels[self.x.get()], self.labels[self.y.get()]
        method, lag = METHODS[self.method.get()], int(self.lag.get())
        if x == y:
            self.report = None
            self.pair_label.configure(text="請選擇兩個不同的指標")
            for tile in self.tiles.values():
                tile.configure(text="—", fg=INK)
            self._empty_charts("Select two different series")
            self._render_evidence()
            self._on_tab()
            return
        self.report = self.dataset.analyze(x, y, lag, method)
        count = len(self.report.samples)
        self.pair_label.configure(text=f"{self.x.get()}   ×   {self.y.get()}   ·   {self.method.get()}   ·   {lag:+d} 月")
        for key, value in (("score", self.report.coefficient), ("early", self.report.earlier), ("late", self.report.later)):
            self.tiles[key].configure(text=_score(value), fg=TEAL if value and value > 0 else NEGATIVE if value else INK)
        self.tiles["n"].configure(text=str(count), fg=INK)
        self._render_charts()
        self._render_evidence()
        self._on_tab()

    def _style_axis(self, ax):
        ax.clear()
        ax.set_axisbelow(True)
        ax.grid(color="#e4ecee", linewidth=0.8)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(LINE)
        ax.tick_params(colors=MUTED, labelsize=9, length=0)

    def _empty_charts(self, label):
        for ax in (self.scatter, self.rolling):
            ax.clear()
            ax.set_axis_off()
            ax.text(0.5, 0.5, label, ha="center", va="center", color=MUTED, transform=ax.transAxes)
        self.chart_note.configure(text="")
        self.canvas.draw_idle()

    def _render_charts(self):
        a, b = self.scatter, self.rolling
        for ax in (a, b):
            self._style_axis(ax)
            ax.set_axis_on()
        pair = self.report.samples
        a.set_xlabel("X change (%)", color=MUTED)
        a.set_ylabel("Y change (%)", color=MUTED)
        a.xaxis.set_major_locator(MaxNLocator(5))
        a.yaxis.set_major_locator(MaxNLocator(5))
        a.axhline(0, color=LINE, linewidth=1)
        a.axvline(0, color=LINE, linewidth=1)
        if pair.empty:
            a.text(0.5, 0.5, "No aligned observations", ha="center", va="center", color=MUTED, transform=a.transAxes)
        else:
            split = len(pair) // 2
            for data, color, mark, label in ((pair.iloc[:split], TEAL, "o", "Earlier"),
                                              (pair.iloc[split:], "#b56e30", "D", "Later")):
                a.scatter(data["x"], data["y"], color=color, marker=mark, s=38,
                          alpha=0.83, edgecolors="white", linewidths=0.65, label=label, zorder=3)
            a.legend(loc="best", frameon=False, fontsize=8, labelcolor=MUTED)
        b.set_ylim(-1.04, 1.04)
        b.set_yticks([-1, -0.5, 0, 0.5, 1])
        b.axhline(0, color="#98a9b1", linewidth=1)
        b.set_xlabel("Y month", color=MUTED)
        rolling = self.report.rolling
        if rolling.notna().any():
            x = rolling.index.to_timestamp()
            b.plot(x, rolling, color=TEAL, linewidth=2.2, marker=".", markersize=4)
            b.fill_between(x, rolling, 0, where=rolling > 0, color="#b4dfd5", alpha=0.55)
            b.fill_between(x, rolling, 0, where=rolling < 0, color="#f4b9aa", alpha=0.55)
            b.xaxis.set_major_locator(MaxNLocator(4))
            b.xaxis.set_major_formatter(DateFormatter("%Y-%m"))
        else:
            b.set_xticks([])
            b.text(0.5, 0.69, "Rolling estimate unavailable", ha="center", color=MUTED, transform=b.transAxes)
        status = ("按可用日代理對齊 · 實際發布順序未確認" if self.report.uses_proxy
                  else "按來源發布時間對齊")
        if self.report.coefficient is None:
            status += " ／ 有效樣本不足或序列無變異"
        self.chart_note.configure(text=status)
        self.canvas.draw_idle()

    def _on_tab(self, _event=None):
        if self.dataset is None or self.book.index("current") != 1:
            return
        key = (self.labels[self.y.get()], self.method.get())
        if key != self.scan_key:
            self.scan_key = key
            self._render_scan(*key)
        for (feature, lag), button in self.cells.items():
            selected = feature == self.labels[self.x.get()] and lag == int(self.lag.get())
            button.configure(highlightbackground=INK if selected else WHITE)

    def _render_scan(self, target, method):
        for widget in self.scan_table.winfo_children():
            widget.destroy()
        self.cells.clear()
        features = tuple(key for key in self.dataset.metrics if key != target)
        rows = self.dataset.scan(target, METHODS[method], features)
        results = {(feature, lag): (value, count, proxy) for feature, lag, value, count, proxy in rows}
        self.scan_table.columnconfigure(0, weight=3)
        self._label(self.scan_table, "指標", bold=True, padx=9, bg="#eaf0f2").grid(row=0, column=0, sticky="nsew")
        for j, lag in enumerate(LAGS, 1):
            self.scan_table.columnconfigure(j, weight=1, uniform="lag")
            self._label(self.scan_table, f"{lag:+d}", bg="#eaf0f2", size=10, anchor="center").grid(
                row=0, column=j, sticky="nsew", pady=1)
        for i, feature in enumerate(features, 1):
            self._label(self.scan_table, self.by_id[feature], size=10, padx=8, pady=4, wraplength=157).grid(
                row=i, column=0, sticky="nsew", padx=(0, 1), pady=(0, 1))
            for j, lag in enumerate(LAGS, 1):
                value, count, proxy = results[feature, lag]
                cell = tk.Frame(self.scan_table, bg=WHITE, highlightthickness=1, highlightbackground=WHITE)
                cell.grid(row=i, column=j, sticky="nsew", padx=(0, 1), pady=(0, 1))
                shade = "#eef1f2" if value is None else to_hex(HEAT(NORM(value)))
                marker = "*" if proxy else ""
                label = self._label(cell, ("—" if value is None else f"{value:+.2f}") + f"\n{count}{marker}",
                                    size=9, bg=shade, fg=WHITE if value and abs(value) >= .83 else INK,
                                    anchor="center", justify="center", pady=4, takefocus=1, cursor="hand2")
                label.pack(fill="both", expand=True)
                for trigger in ("<Button-1>", "<Return>", "<space>"):
                    label.bind(trigger, lambda _e, f=feature, l=lag: self._select_cell(f, l))
                self.cells[feature, lag] = cell
        self.scan_canvas.yview_moveto(0)
        self.scan_note.configure(text=f"{self.by_id[target]} · {method}   ／   上：係數　下：樣本數　* 含可用日代理")

    def _select_cell(self, feature, lag):
        self.x.set(self.by_id[feature])
        self.lag.set(f"{lag:+d}")
        self.refresh()
        self.book.select(self.pair_panel)

    def _render_evidence(self):
        self.tree.delete(*self.tree.get_children())
        self.samples_by_id.clear()
        if self.report is not None:
            for row in self.report.samples.itertuples(index=False):
                item = self.tree.insert("", "end", values=(
                    str(row.period_m), f"{row.x:.2f}", row.feature_published_at.date(),
                    str(row.target_period), f"{row.y:.2f}", row.target_published_at.date(),
                ))
                self.samples_by_id[item] = row
        items = self.tree.get_children()
        if items:
            self.tree.selection_set(items[-1])
            self.tree.see(items[-1])
        self._show_source()

    def _show_source(self, _event=None):
        selected = self.tree.selection()
        row = self.samples_by_id.get(selected[0]) if selected else None
        message = "無配對樣本"
        if row:
            parts = []
            for side, label in (("feature", "X"), ("target", "Y")):
                source = getattr(row, f"{side}_source")
                url = getattr(row, f"{side}_source_url")
                method = getattr(row, f"{side}_knowledge_time_method")
                parts.append(f"{label} · {source} ／ {TIMES.get(method, method)}\n{url}")
            message = "\n".join(parts)
        self.evidence_text.configure(state="normal")
        self.evidence_text.delete("1.0", "end")
        self.evidence_text.insert("1.0", message)
        self.evidence_text.configure(state="disabled")

    def _export(self):
        if self.report is None or self.report.samples.empty:
            return
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if path:
            try:
                self.report.samples.assign(feature=self.labels[self.x.get()], target=self.labels[self.y.get()],
                                           lag_months=int(self.lag.get()), method=self.method.get()).to_csv(
                                               path, index=False, encoding="utf-8-sig")
            except OSError as error:
                messagebox.showerror("無法匯出樣本", str(error), parent=self)

    def _open_tool(self, flag):
        try:
            subprocess.Popen([sys.executable, str(ROOT / "app/main.py"), flag], cwd=ROOT)
        except OSError as error:
            messagebox.showerror("無法開啟工具", str(error), parent=self)


def launch_research_workspace():
    ResearchWorkspace().mainloop()
