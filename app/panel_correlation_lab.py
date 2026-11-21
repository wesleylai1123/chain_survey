from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from core.correlation_engine import METHODS, TRANSFORMS
from core.panel_correlation_engine import compute_panel_correlation, scan_panel_correlations


def panel_demo_data() -> pd.DataFrame:
    """Synthetic panel used only to demonstrate the validation workflow."""
    rng = np.random.default_rng(17)
    companies = ["Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot", "Golf", "Hotel"]
    periods = pd.period_range("2019Q1", periods=28, freq="Q").astype(str)
    rows: list[dict[str, object]] = []
    for company_index, company in enumerate(companies):
        price = 25.0 + company_index * 4
        utilization = 62.0 + company_index * 1.2
        gross_margin = 24.0 + company_index * 0.5
        roe = 7.0 + company_index * 0.4
        for period_index, period in enumerate(periods):
            cycle = ("Expansion", "Slowdown", "Recovery", "Expansion")[(period_index // 7) % 4]
            cycle_impulse = {"Expansion": 1.0, "Slowdown": -0.8, "Recovery": 0.7}[cycle]
            utilization_change = 0.7 * cycle_impulse + rng.normal(0, 1.1)
            utilization += utilization_change
            gross_margin_change = 0.22 * utilization_change + rng.normal(0, 0.35)
            gross_margin += gross_margin_change
            roe_change = 0.15 * gross_margin_change + rng.normal(0, 0.12)
            roe += roe_change
            future_return_signal = 0.006 * utilization_change + 0.010 * gross_margin_change + 0.006 * roe_change
            realised_return = 0.012 + future_return_signal + rng.normal(0, 0.012)
            price *= 1 + realised_return
            rows.append(
                {
                    "company": company,
                    "period": period,
                    "cycle": cycle,
                    "utilization": utilization,
                    "gross_margin": gross_margin,
                    "roe": roe,
                    "noise": rng.normal(0, 1),
                    "stock_price": price,
                }
            )
    return pd.DataFrame(rows)


class PanelCorrelationLab(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Cross-company Correlation Lab")
        self.geometry("1420x940")
        self.minsize(1180, 780)
        self.data = panel_demo_data()

        self.entity_var = tk.StringVar(value="company")
        self.time_var = tk.StringVar(value="period")
        self.cycle_var = tk.StringVar(value="cycle")
        self.x_var = tk.StringVar(value="utilization")
        self.y_var = tk.StringVar(value="stock_price")
        self.method_var = tk.StringVar(value="spearman")
        self.x_transform_var = tk.StringVar(value="diff")
        self.y_transform_var = tk.StringVar(value="forward_return")
        self.lag_var = tk.IntVar(value=0)
        self.periods_var = tk.IntVar(value=1)
        self.status_var = tk.StringVar(value="Synthetic multi-company demo loaded.")

        self._build_ui()
        self._refresh_columns()
        self.run_validation()
        self.run_scan()

    @staticmethod
    def _fmt(value: float) -> str:
        return "-" if pd.isna(value) else f"{value:+.3f}"

    @staticmethod
    def _pct(value: float) -> str:
        return "-" if pd.isna(value) else f"{value * 100:.0f}%"

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=14)
        root.pack(fill="both", expand=True)
        header = ttk.Frame(root)
        header.pack(fill="x", pady=(0, 8))
        ttk.Label(header, text="Cross-company / Cross-cycle Correlation", font=("Segoe UI", 18, "bold")).pack(side="left")
        ttk.Button(header, text="Load panel CSV", command=self.load_csv).pack(side="right")
        ttk.Label(
            root,
            text=(
                "Validate a factor before turning it into a rule. The same relationship is measured as pooled, "
                "within-company time-series, same-period cross-sectional, and cycle-level correlation."
            ),
            wraplength=1320,
        ).pack(anchor="w", pady=(0, 10))

        controls = ttk.LabelFrame(root, text="Panel definition and arbitrary X/Y test", padding=10)
        controls.pack(fill="x", pady=(0, 10))
        for column in range(11):
            controls.columnconfigure(column, weight=1)
        labels = ["Entity", "Time", "Cycle", "X", "X transform", "Y", "Y transform", "Method", "Lag", "Periods"]
        for index, label in enumerate(labels):
            ttk.Label(controls, text=label).grid(row=0, column=index, sticky="w")
        self.entity_combo = ttk.Combobox(controls, textvariable=self.entity_var, state="readonly")
        self.time_combo = ttk.Combobox(controls, textvariable=self.time_var, state="readonly")
        self.cycle_combo = ttk.Combobox(controls, textvariable=self.cycle_var, state="readonly")
        self.x_combo = ttk.Combobox(controls, textvariable=self.x_var, state="readonly")
        self.y_combo = ttk.Combobox(controls, textvariable=self.y_var, state="readonly")
        widgets = [
            self.entity_combo,
            self.time_combo,
            self.cycle_combo,
            self.x_combo,
            ttk.Combobox(controls, textvariable=self.x_transform_var, values=TRANSFORMS, state="readonly"),
            self.y_combo,
            ttk.Combobox(controls, textvariable=self.y_transform_var, values=TRANSFORMS, state="readonly"),
            ttk.Combobox(controls, textvariable=self.method_var, values=METHODS, state="readonly"),
            ttk.Spinbox(controls, from_=-8, to=8, textvariable=self.lag_var, width=6),
            ttk.Spinbox(controls, from_=1, to=8, textvariable=self.periods_var, width=6),
        ]
        for index, widget in enumerate(widgets):
            widget.grid(row=1, column=index, sticky="ew", padx=(0, 5))
        ttk.Button(controls, text="Validate", command=self.run_validation).grid(row=1, column=10, sticky="ew")

        metrics = ttk.Frame(root)
        metrics.pack(fill="x", pady=(0, 10))
        definitions = [
            ("Pooled r", "pooled"),
            ("Median company r", "company"),
            ("Company agreement", "company_agree"),
            ("Median cross-sec r", "cross"),
            ("Cross-sec agreement", "cross_agree"),
            ("Median cycle r", "cycle"),
            ("Cycle agreement", "cycle_agree"),
            ("Generalization", "score"),
        ]
        self.metric_vars = {key: tk.StringVar(value="-") for _, key in definitions}
        for index, (label, key) in enumerate(definitions):
            box = ttk.LabelFrame(metrics, text=label, padding=7)
            box.grid(row=0, column=index, sticky="nsew", padx=(0, 5 if index < len(definitions) - 1 else 0))
            metrics.columnconfigure(index, weight=1)
            ttk.Label(box, textvariable=self.metric_vars[key], font=("Segoe UI", 12, "bold")).pack(anchor="w")

        notebook = ttk.Notebook(root)
        notebook.pack(fill="both", expand=True)
        validation_tab = ttk.Frame(notebook, padding=8)
        scan_tab = ttk.Frame(notebook, padding=8)
        notebook.add(validation_tab, text="Generalization detail")
        notebook.add(scan_tab, text="Cross-company scanner")
        self.notebook = notebook
        self.validation_tab = validation_tab
        self.scan_tab = scan_tab

        body = ttk.Frame(validation_tab)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)
        chart_box = ttk.LabelFrame(body, text="Correlation by company / cycle", padding=8)
        chart_box.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.figure = Figure(figsize=(7.4, 4.6), dpi=100)
        self.canvas = FigureCanvasTkAgg(self.figure, master=chart_box)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

        table_box = ttk.LabelFrame(body, text="Raw validation results", padding=8)
        table_box.grid(row=0, column=1, sticky="nsew")
        columns = ("scope", "group", "correlation", "samples")
        self.detail_tree = ttk.Treeview(table_box, columns=columns, show="headings")
        for column in columns:
            self.detail_tree.heading(column, text=column.title())
            self.detail_tree.column(column, width=115, anchor="center")
        self.detail_tree.column("group", width=145, anchor="w")
        self.detail_tree.pack(fill="both", expand=True)

        scan_controls = ttk.Frame(scan_tab)
        scan_controls.pack(fill="x", pady=(0, 8))
        ttk.Button(scan_controls, text="Scan numeric factors", command=self.run_scan).pack(side="left")
        ttk.Label(scan_controls, text="Ranks raw correlation × sign consistency; still diagnostic, not a trading rule.").pack(side="left", padx=(12, 0))
        scan_columns = ("feature", "lag", "pooled", "company", "company_agree", "cross", "cross_agree", "cycle", "cycle_agree", "score")
        self.scan_tree = ttk.Treeview(scan_tab, columns=scan_columns, show="headings")
        for column in scan_columns:
            self.scan_tree.heading(column, text=column.replace("_", " ").title())
            self.scan_tree.column(column, width=112, anchor="center")
        self.scan_tree.column("feature", width=170, anchor="w")
        self.scan_tree.pack(fill="both", expand=True)
        ttk.Label(root, textvariable=self.status_var).pack(anchor="w", pady=(7, 0))

    def _numeric_columns(self) -> list[str]:
        return [c for c in self.data.columns if pd.to_numeric(self.data[c], errors="coerce").notna().sum() >= 8]

    def _refresh_columns(self) -> None:
        columns = list(self.data.columns)
        numeric = self._numeric_columns()
        for combo in (self.entity_combo, self.time_combo, self.cycle_combo):
            combo["values"] = columns
        self.x_combo["values"] = numeric
        self.y_combo["values"] = numeric

    def load_csv(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        try:
            frame = pd.read_csv(path)
            if frame.empty:
                raise ValueError("CSV has no rows")
            self.data = frame
            self._refresh_columns()
            self.status_var.set(f"Loaded {Path(path).name}: {len(frame)} rows")
        except Exception as exc:
            messagebox.showerror("Load panel CSV", str(exc))

    def run_validation(self) -> None:
        try:
            result = compute_panel_correlation(
                self.data,
                self.entity_var.get(),
                self.time_var.get(),
                self.x_var.get(),
                self.y_var.get(),
                cycle_column=self.cycle_var.get() or None,
                method=self.method_var.get(),
                x_transform=self.x_transform_var.get(),
                y_transform=self.y_transform_var.get(),
                transform_periods=int(self.periods_var.get()),
                lag=int(self.lag_var.get()),
                min_group_samples=4,
            )
        except Exception as exc:
            messagebox.showerror("Panel correlation", str(exc))
            return

        self.metric_vars["pooled"].set(self._fmt(result.pooled_correlation))
        self.metric_vars["company"].set(self._fmt(result.median_company_correlation))
        self.metric_vars["company_agree"].set(self._pct(result.company_sign_agreement))
        self.metric_vars["cross"].set(self._fmt(result.median_cross_sectional_correlation))
        self.metric_vars["cross_agree"].set(self._pct(result.cross_sectional_sign_agreement))
        self.metric_vars["cycle"].set(self._fmt(result.median_cycle_correlation))
        self.metric_vars["cycle_agree"].set(self._pct(result.cycle_sign_agreement))
        self.metric_vars["score"].set(f"{result.generalization_score:.3f}")

        self.detail_tree.delete(*self.detail_tree.get_children())
        for scope, frame, group_column in (
            ("Company", result.company_correlations, "entity"),
            ("Cross-sec", result.cross_sectional_correlations, "time"),
            ("Cycle", result.cycle_correlations, "cycle"),
        ):
            for _, row in frame.iterrows():
                self.detail_tree.insert("", "end", values=(scope, row[group_column], f"{row['correlation']:+.3f}", int(row["sample_size"])))

        self.figure.clear()
        ax = self.figure.add_subplot(111)
        labels: list[str] = []
        values: list[float] = []
        for _, row in result.company_correlations.iterrows():
            labels.append(str(row["entity"]))
            values.append(float(row["correlation"]))
        for _, row in result.cycle_correlations.iterrows():
            labels.append(f"Cycle:{row['cycle']}")
            values.append(float(row["correlation"]))
        if values:
            positions = np.arange(len(values))
            ax.bar(positions, values)
            ax.set_xticks(positions)
            ax.set_xticklabels(labels, rotation=35, ha="right")
        ax.axhline(0, linewidth=0.8)
        ax.set_ylim(-1.05, 1.05)
        ax.set_ylabel("Correlation")
        ax.set_title(f"{result.x_column} → {result.y_column} | pooled r={self._fmt(result.pooled_correlation)}")
        self.figure.tight_layout()
        self.canvas.draw_idle()
        self.status_var.set(
            f"Validated {result.sample_size} observations across {result.entity_count} companies, "
            f"{result.period_count} periods and {result.cycle_count} cycles."
        )

    def run_scan(self) -> None:
        excluded = {self.entity_var.get(), self.time_var.get(), self.cycle_var.get(), self.y_var.get()}
        features = [column for column in self._numeric_columns() if column not in excluded]
        try:
            result = scan_panel_correlations(
                self.data,
                self.entity_var.get(),
                self.time_var.get(),
                self.y_var.get(),
                cycle_column=self.cycle_var.get() or None,
                feature_columns=features,
                method=self.method_var.get(),
                feature_transform=self.x_transform_var.get(),
                target_transform=self.y_transform_var.get(),
                transform_periods=int(self.periods_var.get()),
                lags=range(0, 5),
                min_samples=24,
                min_group_samples=4,
            )
        except Exception as exc:
            messagebox.showerror("Panel scanner", str(exc))
            return
        self.scan_tree.delete(*self.scan_tree.get_children())
        for _, row in result.head(80).iterrows():
            self.scan_tree.insert(
                "",
                "end",
                values=(
                    row["feature"], int(row["lag"]), f"{row['pooled_correlation']:+.3f}",
                    self._fmt(row["median_company_correlation"]), self._pct(row["company_sign_agreement"]),
                    self._fmt(row["median_cross_sectional_correlation"]), self._pct(row["cross_sectional_sign_agreement"]),
                    self._fmt(row["median_cycle_correlation"]), self._pct(row["cycle_sign_agreement"]),
                    f"{row['generalization_score']:.3f}",
                ),
            )
        self.status_var.set(f"Cross-company scanner found {len(result)} valid factor/lag combinations.")


def launch_panel_correlation_lab() -> None:
    app = PanelCorrelationLab()
    app.mainloop()


if __name__ == "__main__":
    launch_panel_correlation_lab()
