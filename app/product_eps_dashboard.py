from __future__ import annotations

import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import matplotlib

matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from core.company_earnings_bridge import CompanyBridgeAssumptions, bridge_product_impacts_to_company
from core.data_loader import load_company_product_relationships, load_quarterly_financials


class ProductEpsDashboard(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Product EPS Contribution Dashboard")
        self.geometry("1320x840")
        self.minsize(1100, 720)

        self.financials = load_quarterly_financials()
        self.company_products = load_company_product_relationships()
        self.scenario_rows: dict[str, tuple[tk.StringVar, tk.StringVar]] = {}

        self._configure_style()
        self._build_layout()
        self._load_companies()

        if os.getenv("UI_SMOKE_DEMO") == "1":
            self.after(250, self._load_demo_scenario)

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"))
        style.configure("Subhead.TLabel", font=("Segoe UI", 11, "bold"))
        style.configure("Metric.TLabel", font=("Segoe UI", 19, "bold"))
        style.configure("Hint.TLabel", foreground="#555555")

    def _build_layout(self) -> None:
        root = ttk.Frame(self, padding=18)
        root.pack(fill="both", expand=True)

        ttk.Label(root, text="Product → Company EPS Contribution", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            root,
            text="Turn product-level revenue / gross-profit changes into company EPS and attribution. Scenario inputs are analyst assumptions, not forecasts.",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(4, 14))

        controls = ttk.LabelFrame(root, text="Company baseline & bridge assumptions", padding=12)
        controls.pack(fill="x", pady=(0, 12))
        for idx in range(8):
            controls.columnconfigure(idx, weight=1 if idx in (1, 3, 5, 7) else 0)

        self.company_var = tk.StringVar()
        self.period_var = tk.StringVar()
        self.opex_var = tk.StringVar(value="10")
        self.nonop_var = tk.StringVar(value="0")

        ttk.Label(controls, text="Company").grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.company_combo = ttk.Combobox(controls, textvariable=self.company_var, state="readonly")
        self.company_combo.grid(row=0, column=1, sticky="ew", padx=(0, 14))
        self.company_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_company_change())

        ttk.Label(controls, text="Period").grid(row=0, column=2, sticky="w", padx=(0, 6))
        self.period_combo = ttk.Combobox(controls, textvariable=self.period_var, state="readonly")
        self.period_combo.grid(row=0, column=3, sticky="ew", padx=(0, 14))
        self.period_combo.bind("<<ComboboxSelected>>", lambda _event: self._refresh_baseline())

        ttk.Label(controls, text="Variable OPEX % of revenue Δ").grid(row=0, column=4, sticky="w", padx=(0, 6))
        ttk.Entry(controls, textvariable=self.opex_var, width=10).grid(row=0, column=5, sticky="ew", padx=(0, 14))

        ttk.Label(controls, text="Non-operating income Δ").grid(row=0, column=6, sticky="w", padx=(0, 6))
        ttk.Entry(controls, textvariable=self.nonop_var, width=12).grid(row=0, column=7, sticky="ew")

        metric_frame = ttk.Frame(root)
        metric_frame.pack(fill="x", pady=(0, 12))
        self.metric_labels: dict[str, ttk.Label] = {}
        for idx, (key, title) in enumerate(
            [
                ("base_eps", "Base EPS"),
                ("scenario_eps", "Scenario EPS"),
                ("eps_change", "EPS Δ"),
                ("eps_change_pct", "EPS Δ %"),
            ]
        ):
            box = ttk.LabelFrame(metric_frame, text=title, padding=10)
            box.grid(row=0, column=idx, sticky="nsew", padx=(0, 10 if idx < 3 else 0))
            metric_frame.columnconfigure(idx, weight=1)
            label = ttk.Label(box, text="-", style="Metric.TLabel")
            label.pack(anchor="w")
            self.metric_labels[key] = label

        main = ttk.Panedwindow(root, orient="horizontal")
        main.pack(fill="both", expand=True)

        input_panel = ttk.LabelFrame(main, text="Product scenario inputs", padding=12)
        result_panel = ttk.LabelFrame(main, text="EPS attribution result", padding=12)
        main.add(input_panel, weight=2)
        main.add(result_panel, weight=3)

        header = ttk.Frame(input_panel)
        header.pack(fill="x", pady=(0, 8))
        ttk.Label(header, text="Product", style="Subhead.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, text="Revenue Δ", style="Subhead.TLabel").grid(row=0, column=1, sticky="w", padx=(14, 0))
        ttk.Label(header, text="Gross Profit Δ", style="Subhead.TLabel").grid(row=0, column=2, sticky="w", padx=(14, 0))

        self.input_canvas = tk.Canvas(input_panel, highlightthickness=0, height=370)
        input_scroll = ttk.Scrollbar(input_panel, orient="vertical", command=self.input_canvas.yview)
        self.input_rows_frame = ttk.Frame(self.input_canvas)
        self.input_rows_frame.bind(
            "<Configure>", lambda _event: self.input_canvas.configure(scrollregion=self.input_canvas.bbox("all"))
        )
        self.input_canvas.create_window((0, 0), window=self.input_rows_frame, anchor="nw")
        self.input_canvas.configure(yscrollcommand=input_scroll.set)
        self.input_canvas.pack(side="left", fill="both", expand=True)
        input_scroll.pack(side="right", fill="y")

        button_bar = ttk.Frame(root)
        button_bar.pack(fill="x", pady=(12, 0))
        ttk.Button(button_bar, text="Load demo scenario", command=self._load_demo_scenario).pack(side="left")
        ttk.Button(button_bar, text="Reset", command=self._reset_scenario).pack(side="left", padx=(8, 0))
        ttk.Button(button_bar, text="Calculate EPS", command=self.calculate).pack(side="left", padx=(8, 0))
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(button_bar, textvariable=self.status_var, style="Hint.TLabel").pack(side="right")

        result_panel.rowconfigure(0, weight=2)
        result_panel.rowconfigure(1, weight=3)
        result_panel.columnconfigure(0, weight=1)

        columns = ("product", "revenue_change", "gross_profit_change", "operating_income_change", "eps_change", "contribution")
        self.result_tree = ttk.Treeview(result_panel, columns=columns, show="headings", height=9)
        headings = {
            "product": "Product",
            "revenue_change": "Revenue Δ",
            "gross_profit_change": "GP Δ",
            "operating_income_change": "Op Income Δ",
            "eps_change": "EPS Δ",
            "contribution": "EPS Contribution",
        }
        for col in columns:
            self.result_tree.heading(col, text=headings[col])
            self.result_tree.column(col, width=125, anchor="e" if col != "product" else "w")
        self.result_tree.grid(row=0, column=0, sticky="nsew", pady=(0, 10))

        self.figure = Figure(figsize=(6.4, 3.2), dpi=100)
        self.canvas = FigureCanvasTkAgg(self.figure, master=result_panel)
        self.canvas.get_tk_widget().grid(row=1, column=0, sticky="nsew")

    def _load_companies(self) -> None:
        companies = sorted(self.financials["company"].dropna().unique().tolist())
        self.company_combo.configure(values=companies)
        if companies:
            self.company_var.set(companies[0])
            self._on_company_change()

    def _on_company_change(self) -> None:
        company = self.company_var.get()
        periods = self.financials[self.financials["company"] == company]["period"].astype(str).tolist()
        self.period_combo.configure(values=periods)
        if periods:
            self.period_var.set(periods[-1])
        self._build_product_inputs()
        self._refresh_baseline()

    def _build_product_inputs(self) -> None:
        for child in self.input_rows_frame.winfo_children():
            child.destroy()
        self.scenario_rows.clear()

        company = self.company_var.get()
        products = self.company_products[self.company_products["company"] == company]["product"].dropna().astype(str).tolist()
        if not products:
            products = ["Unallocated product"]

        for row_index, product in enumerate(products):
            revenue_var = tk.StringVar(value="0")
            gp_var = tk.StringVar(value="0")
            ttk.Label(self.input_rows_frame, text=product, width=28).grid(row=row_index, column=0, sticky="w", pady=4)
            ttk.Entry(self.input_rows_frame, textvariable=revenue_var, width=16).grid(row=row_index, column=1, padx=(14, 0), pady=4)
            ttk.Entry(self.input_rows_frame, textvariable=gp_var, width=16).grid(row=row_index, column=2, padx=(14, 0), pady=4)
            self.scenario_rows[product] = (revenue_var, gp_var)

    def _refresh_baseline(self) -> None:
        rows = self._baseline_rows()
        if rows.empty:
            return
        base_eps = float(rows.iloc[0]["eps"])
        self.metric_labels["base_eps"].configure(text=f"{base_eps:.3f}")
        self.metric_labels["scenario_eps"].configure(text="-")
        self.metric_labels["eps_change"].configure(text="-")
        self.metric_labels["eps_change_pct"].configure(text="-")

    def _baseline_rows(self):
        return self.financials[
            (self.financials["company"] == self.company_var.get())
            & (self.financials["period"].astype(str) == self.period_var.get())
        ]

    def _reset_scenario(self) -> None:
        for revenue_var, gp_var in self.scenario_rows.values():
            revenue_var.set("0")
            gp_var.set("0")
        self.calculate(quiet=True)

    def _load_demo_scenario(self) -> None:
        rows = self._baseline_rows()
        if rows.empty or not self.scenario_rows:
            return
        baseline = rows.iloc[0]
        base_revenue = float(baseline["revenue"])
        base_gp = float(baseline["gross_profit"])
        products = list(self.scenario_rows)

        for revenue_var, gp_var in self.scenario_rows.values():
            revenue_var.set("0")
            gp_var.set("0")

        first = products[0]
        self.scenario_rows[first][0].set(f"{base_revenue * 0.010:.2f}")
        self.scenario_rows[first][1].set(f"{base_gp * 0.012:.2f}")
        if len(products) > 1:
            second = products[1]
            self.scenario_rows[second][0].set(f"{-base_revenue * 0.003:.2f}")
            self.scenario_rows[second][1].set(f"{-base_gp * 0.002:.2f}")
        self.status_var.set("Demo scenario loaded — values are illustrative only")
        self.calculate(quiet=True)

    def calculate(self, quiet: bool = False) -> None:
        try:
            company = self.company_var.get()
            period = self.period_var.get()
            impacts = []
            for product, (revenue_var, gp_var) in self.scenario_rows.items():
                revenue_change = float(revenue_var.get() or 0)
                gross_profit_change = float(gp_var.get() or 0)
                if revenue_change == 0 and gross_profit_change == 0:
                    continue
                impacts.append(
                    {
                        "company": company,
                        "period": period,
                        "product": product,
                        "revenue_change": revenue_change,
                        "gross_profit_change": gross_profit_change,
                    }
                )

            if not impacts:
                self.status_var.set("Enter at least one non-zero product scenario")
                return

            assumptions = CompanyBridgeAssumptions(
                variable_opex_pct_of_revenue_change=float(self.opex_var.get() or 0),
                non_operating_income_change=float(self.nonop_var.get() or 0),
            )
            result = bridge_product_impacts_to_company(company, period, impacts, assumptions)
            self._render_result(result)
            self.status_var.set(f"Calculated {len(impacts)} product contribution(s)")
        except Exception as exc:
            self.status_var.set(f"Error: {exc}")
            if not quiet:
                messagebox.showerror("Scenario error", str(exc))

    def _render_result(self, result: dict) -> None:
        self.metric_labels["base_eps"].configure(text=f"{result['base_eps']:.3f}")
        self.metric_labels["scenario_eps"].configure(text=f"{result['scenario_eps']:.3f}")
        self.metric_labels["eps_change"].configure(text=f"{result['eps_change']:+.3f}")
        pct = result["eps_change_pct"]
        self.metric_labels["eps_change_pct"].configure(text="-" if pct is None else f"{pct:+.2f}%")

        self.result_tree.delete(*self.result_tree.get_children())
        contributions = result["product_contributions"]
        for row in contributions:
            contribution_pct = row["eps_contribution_pct"]
            self.result_tree.insert(
                "",
                "end",
                values=(
                    row["product"],
                    f"{row['revenue_change']:+.2f}",
                    f"{row['gross_profit_change']:+.2f}",
                    f"{row['operating_income_change']:+.2f}",
                    f"{row['eps_change']:+.3f}",
                    "-" if contribution_pct is None else f"{contribution_pct:+.1f}%",
                ),
            )

        if abs(result["non_operating_eps_change"]) > 1e-12:
            self.result_tree.insert(
                "",
                "end",
                values=("Non-operating", "-", "-", "-", f"{result['non_operating_eps_change']:+.3f}", "separate"),
            )

        self.figure.clear()
        ax = self.figure.add_subplot(111)
        labels = [row["product"] for row in contributions]
        values = [row["eps_change"] for row in contributions]
        if abs(result["non_operating_eps_change"]) > 1e-12:
            labels.append("Non-operating")
            values.append(result["non_operating_eps_change"])
        positions = list(range(len(labels)))
        ax.barh(positions, values)
        ax.set_yticks(positions, labels=labels)
        ax.axvline(0, linewidth=1)
        ax.set_xlabel("EPS contribution")
        ax.set_title("Scenario EPS contribution by product")
        ax.invert_yaxis()
        self.figure.tight_layout()
        self.canvas.draw()


def launch_dashboard() -> None:
    app = ProductEpsDashboard()
    app.mainloop()


if __name__ == "__main__":
    launch_dashboard()
