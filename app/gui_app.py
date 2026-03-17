from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import matplotlib

matplotlib.use("TkAgg")

import networkx as nx
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from core.company_service import (
    get_company_products,
    get_company_profile,
    get_related_companies,
    get_upstream_downstream,
)
from core.dashboard_service import get_company_financials, latest_snapshot
from core.data_loader import load_companies, load_edges, load_events, load_financials, load_products
from core.graph_builder import NODE_TYPE_COLOR, build_subgraph
from core.impact_engine import simulate_event


def format_value(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return str(value)


def clear_tree(tree: ttk.Treeview) -> None:
    tree.delete(*tree.get_children())


def fill_tree(tree: ttk.Treeview, rows: list[tuple[str, ...]]) -> None:
    clear_tree(tree)
    for row in rows:
        tree.insert("", "end", values=row)


class FundamentalChainApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Fundamental Chain Reaction Platform")
        self.geometry("1380x900")
        self.minsize(1160, 760)

        self.companies = load_companies()
        self.products = load_products()
        self.edges = load_edges()
        self.events = load_events()
        self.financials = load_financials()

        self.company_names = sorted(self.companies["name"].tolist())
        self.event_names = [event["name"] for event in self.events]
        self.company_tickers = dict(zip(self.companies["name"], self.companies["ticker"]))

        self._configure_style()
        self._build_layout()
        self._populate_overview()

        if self.company_names:
            default_company = self.company_names[0]
            self.company_var.set(default_company)
            self.graph_company_var.set(default_company)
            self.refresh_company_view()
            self.refresh_graph_view()

        if self.event_names:
            self.event_var.set(self.event_names[0])
            self.refresh_event_view()

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Header.TLabel", font=("Segoe UI", 18, "bold"))
        style.configure("Subhead.TLabel", font=("Segoe UI", 11, "bold"))
        style.configure("Metric.TFrame", padding=14)
        style.configure("MetricLabel.TLabel", font=("Segoe UI", 9))
        style.configure("MetricValue.TLabel", font=("Segoe UI", 20, "bold"))

    def _build_layout(self) -> None:
        root = ttk.Frame(self, padding=16)
        root.pack(fill="both", expand=True)

        header = ttk.Frame(root)
        header.pack(fill="x", pady=(0, 12))
        ttk.Label(header, text="Fundamental Chain Reaction Platform", style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Desktop GUI for exploring company relationships, event impact, and financial snapshots.",
        ).pack(anchor="w", pady=(4, 0))

        notebook = ttk.Notebook(root)
        notebook.pack(fill="both", expand=True)

        self.overview_tab = ttk.Frame(notebook, padding=14)
        self.company_tab = ttk.Frame(notebook, padding=14)
        self.event_tab = ttk.Frame(notebook, padding=14)
        self.graph_tab = ttk.Frame(notebook, padding=14)

        notebook.add(self.overview_tab, text="Overview")
        notebook.add(self.company_tab, text="Company Explorer")
        notebook.add(self.event_tab, text="Event Simulator")
        notebook.add(self.graph_tab, text="Network Graph")

        self._build_overview_tab()
        self._build_company_tab()
        self._build_event_tab()
        self._build_graph_tab()

    def _build_overview_tab(self) -> None:
        metrics = ttk.Frame(self.overview_tab)
        metrics.pack(fill="x", pady=(0, 16))

        self.metric_values: dict[str, ttk.Label] = {}
        for idx, key in enumerate(["companies", "products", "relationships", "financial_rows"]):
            frame = ttk.Frame(metrics, style="Metric.TFrame", relief="ridge")
            frame.grid(row=0, column=idx, sticky="nsew", padx=(0, 12 if idx < 3 else 0))
            metrics.columnconfigure(idx, weight=1)

            label_text = {
                "companies": "Companies",
                "products": "Products",
                "relationships": "Relationships",
                "financial_rows": "Financial Rows",
            }[key]
            ttk.Label(frame, text=label_text, style="MetricLabel.TLabel").pack(anchor="w")
            value_label = ttk.Label(frame, text="0", style="MetricValue.TLabel")
            value_label.pack(anchor="w", pady=(8, 0))
            self.metric_values[key] = value_label

        body = ttk.Frame(self.overview_tab)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        left = ttk.LabelFrame(body, text="Desktop GUI Highlights", padding=14)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))

        bullets = [
            "Browse a compact sample of companies, products, and supply-chain relationships.",
            "Inspect company profiles, products, upstream/downstream links, and financial history.",
            "Run predefined event simulations and review the affected companies with impact scores.",
            "Visualize the relationship network around a selected company at configurable depth.",
        ]
        for text in bullets:
            ttk.Label(left, text=f"- {text}", wraplength=720, justify="left").pack(anchor="w", pady=5)

        right = ttk.LabelFrame(body, text="Available Events", padding=14)
        right.grid(row=0, column=1, sticky="nsew")
        self.event_listbox = tk.Listbox(right, height=10)
        self.event_listbox.pack(fill="both", expand=True)

    def _build_company_tab(self) -> None:
        controls = ttk.Frame(self.company_tab)
        controls.pack(fill="x", pady=(0, 12))
        controls.columnconfigure(1, weight=1)

        ttk.Label(controls, text="Company", style="Subhead.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.company_var = tk.StringVar()
        company_combo = ttk.Combobox(controls, textvariable=self.company_var, values=self.company_names, state="readonly")
        company_combo.grid(row=0, column=1, sticky="ew")
        company_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_company_view())
        ttk.Button(controls, text="Refresh", command=self.refresh_company_view).grid(row=0, column=2, padx=(8, 0))

        snapshot_frame = ttk.Frame(self.company_tab)
        snapshot_frame.pack(fill="x", pady=(0, 12))
        self.snapshot_labels: dict[str, ttk.Label] = {}
        snapshot_keys = [("Period", "period"), ("Revenue", "revenue"), ("Gross Margin", "gross_margin"), ("EPS", "eps")]
        for idx, (label, key) in enumerate(snapshot_keys):
            frame = ttk.LabelFrame(snapshot_frame, text=label, padding=10)
            frame.grid(row=0, column=idx, sticky="nsew", padx=(0, 10 if idx < len(snapshot_keys) - 1 else 0))
            snapshot_frame.columnconfigure(idx, weight=1)
            value = ttk.Label(frame, text="-", font=("Segoe UI", 14, "bold"))
            value.pack(anchor="w")
            self.snapshot_labels[key] = value

        main = ttk.Frame(self.company_tab)
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=2)
        main.columnconfigure(1, weight=3)
        main.rowconfigure(0, weight=1)
        main.rowconfigure(1, weight=1)

        profile_box = ttk.LabelFrame(main, text="Company Profile", padding=12)
        profile_box.grid(row=0, column=0, sticky="nsew", padx=(0, 12), pady=(0, 12))
        self.profile_text = tk.Text(profile_box, height=14, wrap="word")
        self.profile_text.pack(fill="both", expand=True)
        self.profile_text.configure(state="disabled")

        product_box = ttk.LabelFrame(main, text="Products", padding=12)
        product_box.grid(row=1, column=0, sticky="nsew", padx=(0, 12))
        self.products_tree = self._create_tree(product_box, ("name", "category", "segment", "description"))

        financial_box = ttk.LabelFrame(main, text="Financial Trend", padding=12)
        financial_box.grid(row=0, column=1, sticky="nsew", pady=(0, 12))
        self.financial_figure = Figure(figsize=(6, 3.2), dpi=100)
        self.financial_canvas = FigureCanvasTkAgg(self.financial_figure, master=financial_box)
        self.financial_canvas.get_tk_widget().pack(fill="both", expand=True)

        relation_box = ttk.LabelFrame(main, text="Upstream / Downstream Links", padding=12)
        relation_box.grid(row=1, column=1, sticky="nsew")

        relation_split = ttk.Panedwindow(relation_box, orient="horizontal")
        relation_split.pack(fill="both", expand=True)

        upstream_frame = ttk.Frame(relation_split)
        downstream_frame = ttk.Frame(relation_split)
        relation_split.add(upstream_frame, weight=1)
        relation_split.add(downstream_frame, weight=1)

        ttk.Label(upstream_frame, text="Upstream", style="Subhead.TLabel").pack(anchor="w", pady=(0, 6))
        self.upstream_tree = self._create_tree(upstream_frame, ("source", "relation", "target", "weight"))
        ttk.Label(downstream_frame, text="Downstream", style="Subhead.TLabel").pack(anchor="w", pady=(0, 6))
        self.downstream_tree = self._create_tree(downstream_frame, ("source", "relation", "target", "weight"))

    def _build_event_tab(self) -> None:
        controls = ttk.Frame(self.event_tab)
        controls.pack(fill="x", pady=(0, 12))
        controls.columnconfigure(1, weight=1)

        ttk.Label(controls, text="Event", style="Subhead.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.event_var = tk.StringVar()
        event_combo = ttk.Combobox(controls, textvariable=self.event_var, values=self.event_names, state="readonly")
        event_combo.grid(row=0, column=1, sticky="ew")
        event_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_event_view())
        ttk.Button(controls, text="Run Simulation", command=self.refresh_event_view).grid(row=0, column=2, padx=(8, 0))

        description_box = ttk.LabelFrame(self.event_tab, text="Event Details", padding=12)
        description_box.pack(fill="x", pady=(0, 12))
        self.event_text = tk.Text(description_box, height=6, wrap="word")
        self.event_text.pack(fill="both", expand=True)
        self.event_text.configure(state="disabled")

        result_box = ttk.LabelFrame(self.event_tab, text="Simulation Results", padding=12)
        result_box.pack(fill="both", expand=True)
        self.event_tree = self._create_tree(
            result_box,
            ("company", "direction", "impact_score", "sector", "industry", "reason", "path"),
        )

    def _build_graph_tab(self) -> None:
        controls = ttk.Frame(self.graph_tab)
        controls.pack(fill="x", pady=(0, 12))

        self.graph_company_var = tk.StringVar()
        ttk.Label(controls, text="Center Company", style="Subhead.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8))
        graph_combo = ttk.Combobox(
            controls,
            textvariable=self.graph_company_var,
            values=self.company_names,
            state="readonly",
            width=32,
        )
        graph_combo.grid(row=0, column=1, sticky="w")
        graph_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_graph_view())

        ttk.Label(controls, text="Depth", style="Subhead.TLabel").grid(row=0, column=2, sticky="w", padx=(16, 8))
        self.depth_var = tk.IntVar(value=1)
        depth_spin = ttk.Spinbox(controls, from_=1, to=3, textvariable=self.depth_var, width=6, command=self.refresh_graph_view)
        depth_spin.grid(row=0, column=3, sticky="w")

        ttk.Button(controls, text="Render Graph", command=self.refresh_graph_view).grid(row=0, column=4, padx=(12, 0))

        graph_box = ttk.LabelFrame(self.graph_tab, text="Relationship Graph", padding=12)
        graph_box.pack(fill="both", expand=True)
        self.graph_figure = Figure(figsize=(7, 6), dpi=100)
        self.graph_canvas = FigureCanvasTkAgg(self.graph_figure, master=graph_box)
        self.graph_canvas.get_tk_widget().pack(fill="both", expand=True)

    def _create_tree(self, parent: ttk.Widget, columns: tuple[str, ...]) -> ttk.Treeview:
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True)

        tree = ttk.Treeview(frame, columns=columns, show="headings")
        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        hsb = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        for column in columns:
            tree.heading(column, text=column.replace("_", " ").title())
            tree.column(column, width=120, minwidth=90, stretch=True)

        return tree

    def _populate_overview(self) -> None:
        self.metric_values["companies"].configure(text=str(len(self.companies)))
        self.metric_values["products"].configure(text=str(len(self.products)))
        self.metric_values["relationships"].configure(text=str(len(self.edges)))
        self.metric_values["financial_rows"].configure(text=str(len(self.financials)))

        self.event_listbox.delete(0, "end")
        for event in self.events:
            self.event_listbox.insert("end", f"{event['name']} (severity {event.get('severity', 1.0)})")

    def refresh_company_view(self) -> None:
        company_name = self.company_var.get()
        if not company_name:
            return

        try:
            profile = get_company_profile(company_name)
            products = get_company_products(company_name)
            upstream, downstream = get_upstream_downstream(company_name)
            financials = get_company_financials(company_name)
            snapshot = latest_snapshot(company_name)
        except Exception as exc:
            messagebox.showerror("Load Error", str(exc))
            return

        lines = [
            f"Name: {profile.get('name', '-')}",
            f"Ticker: {profile.get('ticker', '-')}",
            f"Country: {profile.get('country', '-')}",
            f"Sector: {profile.get('sector', '-')}",
            f"Industry: {profile.get('industry', '-')}",
            "",
            "Description:",
            format_value(profile.get("description")),
            "",
            "Key Drivers:",
            format_value(profile.get("key_drivers")),
            "",
            f"Related links in dataset: {len(get_related_companies(company_name))}",
        ]
        self.profile_text.configure(state="normal")
        self.profile_text.delete("1.0", "end")
        self.profile_text.insert("1.0", "\n".join(lines))
        self.profile_text.configure(state="disabled")

        product_rows = [
            tuple(format_value(row.get(col)) for col in ["name", "category", "segment", "description"])
            for _, row in products.iterrows()
        ]
        fill_tree(self.products_tree, product_rows)

        upstream_rows = [
            tuple(format_value(row.get(col)) for col in ["source", "relation", "target", "weight"])
            for _, row in upstream.iterrows()
        ]
        downstream_rows = [
            tuple(format_value(row.get(col)) for col in ["source", "relation", "target", "weight"])
            for _, row in downstream.iterrows()
        ]
        fill_tree(self.upstream_tree, upstream_rows)
        fill_tree(self.downstream_tree, downstream_rows)

        for key, label in self.snapshot_labels.items():
            label.configure(text=format_value(snapshot.get(key)))

        self._draw_financial_chart(financials, company_name)

    def _draw_financial_chart(self, financials, company_name: str) -> None:
        self.financial_figure.clear()
        ax = self.financial_figure.add_subplot(111)

        if financials.empty:
            ax.text(0.5, 0.5, "No financial data available", ha="center", va="center")
            ax.set_axis_off()
        else:
            periods = financials["period"].tolist()
            ax.plot(periods, financials["revenue"], marker="o", linewidth=2, color="#2563eb", label="Revenue")
            ax.set_title(f"{self._safe_graph_text(company_name)} Revenue Trend")
            ax.set_xlabel("Period")
            ax.set_ylabel("Revenue")
            ax.grid(True, alpha=0.25)

            ax2 = ax.twinx()
            ax2.plot(periods, financials["eps"], marker="s", linewidth=2, color="#f59e0b", label="EPS")
            ax2.set_ylabel("EPS")

            lines, labels = ax.get_legend_handles_labels()
            lines2, labels2 = ax2.get_legend_handles_labels()
            ax.legend(lines + lines2, labels + labels2, loc="upper left")

        self.financial_figure.tight_layout()
        self.financial_canvas.draw()

    def refresh_event_view(self) -> None:
        event_name = self.event_var.get()
        if not event_name:
            return

        event = next((item for item in self.events if item["name"] == event_name), None)
        if event is None:
            messagebox.showerror("Event Error", f"Event not found: {event_name}")
            return

        details = [
            f"Name: {event['name']}",
            f"Severity: {event.get('severity', 1.0)}",
            "",
            "Rules:",
        ]
        for rule in event.get("rules", []):
            details.append(
                f"- relation={rule.get('relation', '*')}, target_type={rule.get('target_type', '*')}, "
                f"direction={rule.get('direction', '-')}, base_score={rule.get('base_score', '-')}, "
                f"reason={rule.get('reason', '-')}"
            )

        self.event_text.configure(state="normal")
        self.event_text.delete("1.0", "end")
        self.event_text.insert("1.0", "\n".join(details))
        self.event_text.configure(state="disabled")

        result = simulate_event(event_name)
        rows = [
            tuple(format_value(row.get(col)) for col in ["company", "direction", "impact_score", "sector", "industry", "reason", "path"])
            for _, row in result.iterrows()
        ]
        fill_tree(self.event_tree, rows)

    def refresh_graph_view(self) -> None:
        company_name = self.graph_company_var.get()
        if not company_name:
            return

        depth = max(1, int(self.depth_var.get()))
        graph = build_subgraph(company_name, depth=depth)
        label_map = self._build_graph_label_map(graph)

        self.graph_figure.clear()
        ax = self.graph_figure.add_subplot(111)
        ax.set_title(f"Relationship Graph: {self._safe_graph_text(company_name)} (depth {depth})")
        ax.axis("off")

        if len(graph.nodes) == 1:
            pos = {company_name: (0.0, 0.0)}
        else:
            pos = nx.spring_layout(graph, seed=42, k=1.1)

        node_colors = []
        node_sizes = []
        for node, attrs in graph.nodes(data=True):
            node_type = attrs.get("node_type", "company")
            node_colors.append("#7c3aed" if node == company_name else NODE_TYPE_COLOR.get(node_type, "#64748b"))
            node_sizes.append(1400 if node == company_name else 900)

        nx.draw_networkx_edges(graph, pos, ax=ax, edge_color="#94a3b8", width=1.2)
        nx.draw_networkx_nodes(graph, pos, ax=ax, node_color=node_colors, node_size=node_sizes, linewidths=1.2, edgecolors="white")
        nx.draw_networkx_labels(graph, pos, ax=ax, labels=label_map, font_size=8)

        self.graph_figure.tight_layout()
        self.graph_canvas.draw()

    def _safe_graph_text(self, text: str) -> str:
        if text.isascii():
            return text
        return self.company_tickers.get(text, text.encode("ascii", "ignore").decode("ascii") or "item")

    def _build_graph_label_map(self, graph: nx.Graph) -> dict[str, str]:
        label_map: dict[str, str] = {}
        counters: dict[str, int] = {}

        for node, attrs in graph.nodes(data=True):
            if node.isascii():
                label_map[node] = node
                continue

            ticker = self.company_tickers.get(node)
            if ticker:
                label_map[node] = ticker
                continue

            node_type = attrs.get("node_type", "node")
            prefix = {
                "company": "C",
                "product": "P",
                "market": "M",
                "event": "E",
            }.get(node_type, "N")
            counters[prefix] = counters.get(prefix, 0) + 1
            label_map[node] = f"{prefix}{counters[prefix]}"

        return label_map


def launch_app() -> None:
    app = FundamentalChainApp()
    app.mainloop()
