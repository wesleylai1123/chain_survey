from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Sequence
from tkinter import font, ttk


DEFAULT_COMPANY = "聯發科"
DEFAULT_EVENT = "AI 基礎建設資本支出加速"
NO_VALUE = "—"

PRODUCT_COLUMNS = (
    ("product", "產品", "手機 SoC"),
    ("direction", "方向", "證據不足"),
    ("score", "影響分數", "+0.84 / -0.51"),
    ("exposure", "曝險", "直接及間接"),
    ("revenue_mix", "營收占比", "100%"),
)
CHAIN_COLUMNS = (
    ("company", "相關公司", "供應商名稱"),
    ("role", "角色", "上游"),
    ("direction", "方向", "證據不足"),
    ("score", "影響分數", "-0.423"),
    ("cumulative_lag", "累計落後", "12"),
)


def _default_name(names: Sequence[str], preferred: str) -> str:
    if preferred in names:
        return preferred
    return names[0] if names else ""


def _value(value: object) -> str:
    return NO_VALUE if value is None else str(value)


def _score(value: float | None) -> str:
    if value is None:
        return NO_VALUE
    return f"{value:+.3g}" if value else "0"


def _revenue_mix(value: float | None) -> str:
    return NO_VALUE if value is None else f"{value:.6g}%"


def _strength(product: dict) -> float:
    scores = (product["score"], product["positive_score"], product["negative_score"])
    return max((abs(score) for score in scores if score is not None), default=-1.0)


def _score_cell(result: dict) -> str:
    if result["direction"] == "混合":
        return f"{_score(result['positive_score'])} / {_score(result['negative_score'])}"
    return _score(result["score"])


def _score_evidence(result: dict) -> str:
    if result["direction"] == "混合":
        return (
            f"最強正面分數　{_score(result['positive_score'])}　｜　"
            f"最強負面分數　{_score(result['negative_score'])}"
        )
    return f"最強影響分數　{_score(result['score'])}"


def _path_evidence(path: dict) -> tuple[str, ...]:
    return (
        "",
        f"路徑分數　{_score(path['signed_score'])}　｜　"
        f"傳導層級　{_value(path['layer'])}　｜　累計落後　{_value(path['cumulative_lag'])}",
        f"傳導路徑　{_value(path['path'])}",
        f"理由　{_value(path['reason'])}",
    )


def _product_evidence(product: dict) -> str:
    lines = [
        product["product"],
        f"影響方向　{product['direction']}　｜　產品曝險　{product['exposure']}",
        _score_evidence(product),
        f"關係權重　{_value(product['relationship_weight'])}",
        f"營收占比　{_revenue_mix(product['revenue_mix_pct'])}　｜　"
        f"資料期間　{_value(product['revenue_mix_period'])}",
    ]
    for path in product["paths"]:
        lines.extend(_path_evidence(path))
    if not product["paths"]:
        lines.extend(("", "目前沒有可追溯的產品路徑。"))
    return "\n".join(lines)


def _chain_evidence(row: dict) -> str:
    scope = "公司層級" if row["product"] is None else f"產品　{row['product']}"
    lines = [
        f"{row['company']}　｜　{scope}",
        f"角色　{row['role']}　｜　關係　{_value(row['link'])}",
        f"影響方向　{row['direction']}",
        _score_evidence(row),
    ]
    paths = row.get("paths") or []
    reason = row["reason"] or ""
    if paths:
        evidence = []
        for path in paths:
            evidence.extend(_path_evidence(path))
            path_reason = path["reason"]
            if path["path"] == row["path"] and path_reason:
                # The service joins the relationship rationale and best path reason.
                reason = "" if reason == path_reason else reason.removesuffix(f"｜{path_reason}")
        if reason:
            lines.append(f"關係理由　{reason}")
        lines.extend(evidence)
    else:
        lines.extend((
            f"累計落後　{_value(row['cumulative_lag'])}",
            "",
            f"傳導路徑　{row['path'] or NO_VALUE}",
            f"理由　{reason or NO_VALUE}",
        ))
    return "\n".join(lines)


def _table(
    parent: ttk.Frame, name: str, columns: tuple[tuple[str, str, str], ...], height: int,
) -> ttk.Treeview:
    panel = ttk.Frame(parent)
    panel.grid(row=0, column=0, sticky="nsew")
    panel.rowconfigure(0, weight=1)
    panel.columnconfigure(0, weight=1)

    table = ttk.Treeview(
        panel, name=name, columns=[key for key, _, _ in columns],
        show="headings", height=height, selectmode="browse", takefocus=True,
        style="TopicImpact.Treeview",
    )
    vertical = ttk.Scrollbar(panel, name="vertical_scroll", orient="vertical", command=table.yview)
    horizontal = ttk.Scrollbar(panel, name="horizontal_scroll", orient="horizontal", command=table.xview)
    table.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
    table.grid(row=0, column=0, sticky="nsew")
    vertical.grid(row=0, column=1, sticky="ns")
    horizontal.grid(row=1, column=0, sticky="ew")

    face = font.nametofont("TkDefaultFont", root=parent)
    heading_face = font.nametofont("TkHeadingFont", root=parent)
    padding = parent.winfo_pixels("9p")
    for index, (key, title, example) in enumerate(columns):
        minimum = heading_face.measure(title) + padding
        table.heading(key, text=title, anchor="w")
        table.column(
            key, width=max(minimum, face.measure(example) + padding),
            minwidth=minimum, stretch=index == 0,
        )
    return table


def _reader(parent: ttk.Frame, name: str, height: int) -> tk.Text:
    parent.rowconfigure(0, weight=1)
    parent.columnconfigure(0, weight=1)
    text = tk.Text(
        parent, name=name, wrap="word", width=1, height=height,
        padx="6p", pady="4p", font="TkDefaultFont", state="disabled", takefocus=True,
    )
    scroll = ttk.Scrollbar(parent, name="vertical_scroll", orient="vertical", command=text.yview)
    text.configure(yscrollcommand=scroll.set)
    text.grid(row=0, column=0, sticky="nsew")
    scroll.grid(row=0, column=1, sticky="ns")
    return text


def _write_text(widget: tk.Text, content: str) -> None:
    widget.configure(state="normal")
    widget.delete("1.0", "end")
    widget.insert("1.0", content)
    widget.configure(state="disabled")
    widget.yview_moveto(0)


def _select_first(table: ttk.Treeview) -> None:
    items = table.get_children()
    if items:
        table.focus(items[0])
        table.selection_set(items[0])
        table.see(items[0])


class _ChainView(ttk.Frame):
    def __init__(self, parent: ttk.Notebook, name: str) -> None:
        super().__init__(parent, name=name, padding=8)
        self.rowconfigure(0, weight=2)
        self.rowconfigure(1, weight=3)
        self.columnconfigure(0, weight=1)
        self.tree = _table(self, "chain", CHAIN_COLUMNS, height=4)
        evidence = ttk.LabelFrame(self, text="供應鏈證據", padding=6)
        evidence.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        self.evidence = _reader(evidence, "chain_evidence", height=4)
        self._rows: dict[str, dict] = {}
        self._empty_message = ""
        self.tree.bind("<<TreeviewSelect>>", self._show_evidence)

    def render(self, rows: list[dict], empty_message: str) -> None:
        self.tree.delete(*self.tree.get_children())
        self._rows.clear()
        self._empty_message = empty_message
        for row in rows:
            item = self.tree.insert("", "end", values=(
                row["company"], row["role"], row["direction"], _score_cell(row),
                _value(row["cumulative_lag"]),
            ))
            self._rows[item] = row
        _select_first(self.tree)
        self._show_evidence()

    def _show_evidence(self, _event: object = None) -> None:
        selection = self.tree.selection()
        row = self._rows.get(selection[0]) if selection else None
        if row is None:
            message = "請選擇供應鏈資料列。" if self._rows else self._empty_message
            _write_text(self.evidence, message)
            return

        _write_text(self.evidence, _chain_evidence(row))


class TopicImpactTab(ttk.Frame):
    def __init__(
        self,
        parent: ttk.Notebook,
        company_names: Sequence[str],
        event_names: Sequence[str],
        analyze: Callable[[str, str], dict],
    ) -> None:
        super().__init__(parent, name="topic_impact", padding=14)
        self._analyze = analyze
        self._products: dict[str, dict] = {}
        self._chain: list[dict] = []
        self._needs_refresh = True

        face = font.nametofont("TkDefaultFont", root=self)
        ttk.Style(self).configure(
            "TopicImpact.Treeview", font=face,
            rowheight=face.metrics("linespace") + self.winfo_pixels("4p"),
        )
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self._build_controls(company_names, event_names)
        self._build_results()
        self.bind("<Map>", self._on_map)

    def _build_controls(self, company_names: Sequence[str], event_names: Sequence[str]) -> None:
        controls = ttk.Frame(self)
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        controls.columnconfigure(1, weight=2)
        controls.columnconfigure(3, weight=3)

        self.company_var = tk.StringVar(self, value=_default_name(company_names, DEFAULT_COMPANY))
        self.event_var = tk.StringVar(self, value=_default_name(event_names, DEFAULT_EVENT))
        ttk.Label(controls, text="公司").grid(row=0, column=0, sticky="w", padx=(0, 6))
        company = ttk.Combobox(
            controls, name="company", textvariable=self.company_var, values=tuple(company_names),
            state="readonly", width=14, takefocus=True,
        )
        company.grid(row=0, column=1, sticky="ew", padx=(0, 12))
        company.bind("<<ComboboxSelected>>", self.refresh)

        ttk.Label(controls, text="事件").grid(row=0, column=2, sticky="w", padx=(0, 6))
        event = ttk.Combobox(
            controls, name="event", textvariable=self.event_var, values=tuple(event_names),
            state="readonly", width=20, takefocus=True,
        )
        event.grid(row=0, column=3, sticky="ew", padx=(0, 8))
        event.bind("<<ComboboxSelected>>", self.refresh)
        ttk.Button(controls, text="分析題材", command=self.refresh).grid(row=0, column=4)

    def _build_results(self) -> None:
        summary = ttk.LabelFrame(self, text="公司影響摘要", padding=8)
        summary.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        summary.columnconfigure(0, weight=1)
        self.result_label = ttk.Label(summary)
        self.result_label.grid(row=0, column=0, sticky="w", pady=(0, 4))
        summary_reader = ttk.Frame(summary)
        summary_reader.grid(row=1, column=0, sticky="ew")
        self.summary_text = _reader(summary_reader, "summary", height=3)

        body = ttk.Frame(self)
        body.grid(row=2, column=0, sticky="nsew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure((0, 1), weight=1, uniform="topic_impact")
        products = ttk.LabelFrame(body, text="產品影響", padding=8)
        products.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        products.rowconfigure(0, weight=1)
        products.columnconfigure(0, weight=1)
        self.products_tree = _table(products, "products", PRODUCT_COLUMNS, height=8)
        self.products_tree.bind("<<TreeviewSelect>>", self._show_product)

        details = ttk.Notebook(body, name="details", takefocus=True)
        details.grid(row=0, column=1, sticky="nsew")
        evidence = ttk.Frame(details, name="product_evidence", padding=8)
        details.add(evidence, text="產品證據")
        self.product_text = _reader(evidence, "evidence", height=6)
        self.product_chain = _ChainView(details, name="product_chain")
        details.add(self.product_chain, text="產品供應鏈")
        self.company_chain = _ChainView(details, name="company_chain")
        details.add(self.company_chain, text="公司層級供應鏈")
        details.enable_traversal()

    def invalidate(self) -> None:
        self._needs_refresh = True

    def _on_map(self, _event: object) -> None:
        if self._needs_refresh:
            self.refresh()

    def refresh(self, _event: object = None) -> None:
        self._needs_refresh = False
        company, event = self.company_var.get(), self.event_var.get()
        if not company or not event:
            self._clear_result("請選擇公司與事件。")
            return
        try:
            result = self._analyze(company, event)
        except (LookupError, RuntimeError, ValueError) as error:
            self._clear_result(f"無法完成分析。\n{error}")
            return

        self.result_label.configure(
            text=f"關聯程度　{result['relevance']}　｜　影響方向　{result['direction']}",
        )
        _write_text(self.summary_text, f"事件說明　{result['description']}\n影響摘要　{result['summary']}")
        self._render_products(sorted(result["products"], key=_strength, reverse=True))
        self._chain = result["chain"]
        self.company_chain.render(
            [row for row in self._chain if row["product"] is None],
            "目前沒有公司層級供應鏈資料。",
        )
        self._show_product()

    def _clear_result(self, message: str) -> None:
        self.result_label.configure(text="分析結果尚未取得")
        _write_text(self.summary_text, message)
        self._render_products([])
        self._chain = []
        self.company_chain.render([], "請先完成題材分析。")
        self._show_product()

    def _render_products(self, products: list[dict]) -> None:
        self.products_tree.delete(*self.products_tree.get_children())
        self._products.clear()
        for product in products:
            item = self.products_tree.insert("", "end", values=(
                product["product"], product["direction"], _score_cell(product), product["exposure"],
                _revenue_mix(product["revenue_mix_pct"]),
            ))
            self._products[item] = product
        _select_first(self.products_tree)

    def _show_product(self, _event: object = None) -> None:
        selection = self.products_tree.selection()
        product = self._products.get(selection[0]) if selection else None
        if product is None:
            message = "請選擇產品。" if self._products else "目前沒有產品資料。"
            _write_text(self.product_text, message)
            self.product_chain.render([], message)
            return

        _write_text(self.product_text, _product_evidence(product))
        self.product_chain.render(
            [row for row in self._chain if row["product"] == product["product"]],
            f"{product['product']}目前沒有供應鏈資料。",
        )
