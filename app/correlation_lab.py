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

from core.correlation_engine import METHODS, TRANSFORMS, compute_correlation, prepare_pair, scan_correlations


def _demo_data() -> pd.DataFrame:
    rng = np.random.default_rng(7)
    periods = 48
    demand = np.linspace(100, 180, periods) + rng.normal(0, 4, periods)
    utilization = 65 + 0.16 * demand + rng.normal(0, 2, periods)
    gross_margin = 18 + 0.28 * utilization + rng.normal(0, 1.5, periods)
    eps = 1.0 + 0.11 * gross_margin + rng.normal(0, 0.12, periods)
    price_return = np.clip(0.012 * (eps - np.roll(eps, 1)) + rng.normal(0.008, 0.025, periods), -0.2, 0.2)
    price_return[0] = 0.0
    stock_price = 20 * np.cumprod(1 + price_return)
    return pd.DataFrame(
        {
            "period": pd.period_range("2022Q1", periods=periods, freq="Q").astype(str),
            "industry_demand": demand,
            "utilization": utilization,
            "gross_margin": gross_margin,
            "eps": eps,
            "stock_price": stock_price,
        }
    )


class CorrelationLab(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Correlation Lab")
        self.geometry("1320x880")
        self.minsize(1080, 720)
        self.data = _demo_data()

        self.x_var = tk.StringVar(value="utilization")
        self.y_var = tk.StringVar(value="stock_price")
        self.method_var = tk.StringVar(value="spearman")
        self.x_transform_var = tk.StringVar(value="pct_change")
        self.y_transform_var = tk.StringVar(value="forward_return")
        self.lag_var = tk.IntVar(value=0)
        self.periods_var = tk.IntVar(value=1)
        self.target_var = tk.StringVar(value="stock_price")
        self.status_var = tk.StringVar(value="Demo data loaded. Choose any two numeric columns.")

        self._build_ui()
        self._refresh_column_choices()
        self.run_pair_analysis()
        self.run_scan()

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=14)
        root.pack(fill="both", expand=True)

        header = ttk.Frame(root)
        header.pack(fill="x", pady=(0, 10))
        ttk.Label(header, text="Correlation Lab", font=("Segoe UI", 18, "bold")).pack(side="left")
        ttk.Button(header, text="Load CSV", command=self.load_csv).pack(side="right")
        ttk.Button(header, text="Load demo", command=self.load_demo).pack(side="right", padx=(0, 8))

        ttk.Label(
            root,
            text=(
                "Test arbitrary relationships before turning them into rules. Positive lag means X leads Y. "
                "For stock research, prefer changes/returns over two trending raw levels."
            ),
            wraplength=1200,
        ).pack(anchor="w", pady=(0, 10))

        notebook = ttk.Notebook(root)
        notebook.pack(fill="both", expand=True)
        self.pair_tab = ttk.Frame(notebook, padding=12)
        self.scan_tab = ttk.Frame(notebook, padding=12)
        notebook.add(self.pair_tab, text="Pair Analysis")
        notebook.add(self.scan_tab, text="Correlation Scanner")
        self._build_pair_tab()
        self._build_scan_tab()

        ttk.Label(root, textvariable=self.status_var).pack(anchor="w", pady=(8, 0))

    def _build_pair_tab(self) -> None:
        controls = ttk.LabelFrame(self.pair_tab, text="Arbitrary correlation", padding=10)
        controls.pack(fill="x", pady=(0, 10))
        for index in range(8):
            controls.columnconfigure(index, weight=1)

        labels = ["X", "X transform", "Y", "Y transform", "Method", "Lag", "Periods"]
        for idx, text in enumerate(labels):
            ttk.Label(controls, text=text).grid(row=0, column=idx, sticky="w")

        self.x_combo = ttk.Combobox(controls, textvariable=self.x_var, state="readonly")
        self.x_combo.grid(row=1, column=0, sticky="ew", padx=(0, 6))
        ttk.Combobox(controls, textvariable=self.x_transform_var, values=TRANSFORMS, state="readonly").grid(
            row=1, column=1, sticky="ew", padx=(0, 6)
        )
        self.y_combo = ttk.Combobox(controls, textvariable=self.y_var, state="readonly")
        self.y_combo.grid(row=1, column=2, sticky="ew", padx=(0, 6))
        ttk.Combobox(controls, textvariable=self.y_transform_var, values=TRANSFORMS, state="readonly").grid(
            row=1, column=3, sticky="ew", padx=(0, 6)
        )
        ttk.Combobox(controls, textvariable=self.method_var, values=METHODS, state="readonly").grid(
            row=1, column=4, sticky="ew", padx=(0, 6)
        )
        ttk.Spinbox(controls, from_=-12, to=12, textvariable=self.lag_var, width=7).grid(row=1, column=5, sticky="ew", padx=(0, 6))
        ttk.Spinbox(controls, from_=1, to=12, textvariable=self.periods_var, width=7).grid(row=1, column=6, sticky="ew", padx=(0, 6))
        ttk.Button(controls, text="Analyze", command=self.run_pair_analysis).grid(row=1, column=7, sticky="ew")

        metrics = ttk.Frame(self.pair_tab)
        metrics.pack(fill="x", pady=(0, 10))
        self.metric_vars = {
            "corr": tk.StringVar(value="-"),
            "samples": tk.StringVar(value="-"),
            "first": tk.StringVar(value="-"),
            "second": tk.StringVar(value="-"),
            "stability": tk.StringVar(value="-"),
        }
        for idx, (label, key) in enumerate(
            [
                ("Correlation", "corr"),
                ("Samples", "samples"),
                ("First half", "first"),
                ("Second half", "second"),
                ("Stability", "stability"),
            ]
        ):
            box = ttk.LabelFrame(metrics, text=label, padding=8)
            box.grid(row=0, column=idx, sticky="nsew", padx=(0, 8 if idx < 4 else 0))
            metrics.columnconfigure(idx, weight=1)
            ttk.Label(box, textvariable=self.metric_vars[key], font=("Segoe UI", 14, "bold")).pack(anchor="w")

        body = ttk.Frame(self.pair_tab)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        scatter_box = ttk.LabelFrame(body, text="Aligned observations", padding=8)
        scatter_box.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.scatter_figure = Figure(figsize=(5.4, 4.3), dpi=100)
        self.scatter_canvas = FigureCanvasTkAgg(self.scatter_figure, master=scatter_box)
        self.scatter_canvas.get_tk_widget().pack(fill="both", expand=True)

        note_box = ttk.LabelFrame(body, text="Interpretation", padding=10)
        note_box.grid(row=0, column=1, sticky="nsew")
        self.note_text = tk.Text(note_box, wrap="word", height=20)
        self.note_text.pack(fill="both", expand=True)
        self.note_text.configure(state="disabled")

    def _build_scan_tab(self) -> None:
        controls = ttk.Frame(self.scan_tab)
        controls.pack(fill="x", pady=(0, 10))
        ttk.Label(controls, text="Target").pack(side="left")
        self.target_combo = ttk.Combobox(controls, textvariable=self.target_var, state="readonly", width=24)
        self.target_combo.pack(side="left", padx=(8, 12))
        ttk.Button(controls, text="Scan all numeric columns", command=self.run_scan).pack(side="left")
        ttk.Label(
            controls,
            text="Default: feature % change → target forward return, lags 0..4, Spearman",
        ).pack(side="left", padx=(14, 0))

        columns = ("feature", "lag", "correlation", "samples", "first_half", "second_half", "stability", "score")
        self.scan_tree = ttk.Treeview(self.scan_tab, columns=columns, show="headings")
        for col in columns:
            self.scan_tree.heading(col, text=col.replace("_", " ").title())
            self.scan_tree.column(col, width=120, anchor="center")
        self.scan_tree.column("feature", width=190, anchor="w")
        self.scan_tree.pack(fill="both", expand=True)

    def _numeric_columns(self) -> list[str]:
        return [column for column in self.data.columns if pd.to_numeric(self.data[column], errors="coerce").notna().sum() >= 3]

    def _refresh_column_choices(self) -> None:
        columns = self._numeric_columns()
        self.x_combo["values"] = columns
        self.y_combo["values"] = columns
        self.target_combo["values"] = columns
        if self.x_var.get() not in columns and columns:
            self.x_var.set(columns[0])
        if self.y_var.get() not in columns and columns:
            self.y_var.set(columns[-1])
        if self.target_var.get() not in columns and columns:
            self.target_var.set(columns[-1])

    def load_demo(self) -> None:
        self.data = _demo_data()
        self.x_var.set("utilization")
        self.y_var.set("stock_price")
        self.target_var.set("stock_price")
        self._refresh_column_choices()
        self.run_pair_analysis()
        self.run_scan()
        self.status_var.set("Demo data loaded.")

    def load_csv(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        try:
            frame = pd.read_csv(path)
        except Exception as exc:
            messagebox.showerror("Load CSV", str(exc))
            return
        if frame.empty:
            messagebox.showerror("Load CSV", "CSV has no rows")
            return
        self.data = frame
        self._refresh_column_choices()
        self.status_var.set(f"Loaded {Path(path).name}: {len(frame)} rows, {len(frame.columns)} columns")
        self.run_pair_analysis()
        self.run_scan()

    @staticmethod
    def _fmt(value: float) -> str:
        return "-" if pd.isna(value) else f"{value:+.3f}"

    def run_pair_analysis(self) -> None:
        try:
            result = compute_correlation(
                self.data,
                self.x_var.get(),
                self.y_var.get(),
                method=self.method_var.get(),
                x_transform=self.x_transform_var.get(),
                y_transform=self.y_transform_var.get(),
                transform_periods=int(self.periods_var.get()),
                lag=int(self.lag_var.get()),
            )
            pair = prepare_pair(
                self.data,
                self.x_var.get(),
                self.y_var.get(),
                x_transform=self.x_transform_var.get(),
                y_transform=self.y_transform_var.get(),
                transform_periods=int(self.periods_var.get()),
                lag=int(self.lag_var.get()),
            )
        except Exception as exc:
            messagebox.showerror("Correlation", str(exc))
            return

        self.metric_vars["corr"].set(self._fmt(result.correlation))
        self.metric_vars["samples"].set(str(result.sample_size))
        self.metric_vars["first"].set(self._fmt(result.first_half_correlation))
        self.metric_vars["second"].set(self._fmt(result.second_half_correlation))
        self.metric_vars["stability"].set(f"{result.stability_score:.2f}")

        self.scatter_figure.clear()
        ax = self.scatter_figure.add_subplot(111)
        if not pair.empty:
            ax.scatter(pair["x"], pair["y"], alpha=0.75)
        ax.set_xlabel(f"{result.x_column} [{result.x_transform}]")
        ax.set_ylabel(f"{result.y_column} [{result.y_transform}]")
        ax.set_title(f"{result.method.title()} r={self._fmt(result.correlation)} | lag={result.lag}")
        ax.grid(alpha=0.25)
        self.scatter_figure.tight_layout()
        self.scatter_canvas.draw_idle()

        if abs(result.correlation) >= 0.7:
            strength = "strong"
        elif abs(result.correlation) >= 0.4:
            strength = "moderate"
        else:
            strength = "weak"
        direction = "positive" if result.correlation >= 0 else "negative"
        warning = (
            "\n\nCaution: correlation is not causation. A high value can disappear out of sample. "
            "The stability metric compares first-half and second-half sign/magnitude; 1 is more stable."
        )
        explanation = (
            f"Observed {strength} {direction} association.\n\n"
            f"Positive lag={result.lag} means X leads Y by that many rows.\n"
            f"Samples after transforms/alignment: {result.sample_size}.\n"
            f"First-half correlation: {self._fmt(result.first_half_correlation)}.\n"
            f"Second-half correlation: {self._fmt(result.second_half_correlation)}.\n"
            f"Stability score: {result.stability_score:.2f}."
            + warning
        )
        self.note_text.configure(state="normal")
        self.note_text.delete("1.0", "end")
        self.note_text.insert("1.0", explanation)
        self.note_text.configure(state="disabled")
        self.status_var.set("Pair correlation calculated.")

    def run_scan(self) -> None:
        target = self.target_var.get()
        if not target:
            return
        try:
            result = scan_correlations(
                self.data,
                target,
                method="spearman",
                feature_transform="pct_change",
                target_transform="forward_return",
                transform_periods=1,
                lags=range(0, 5),
                min_samples=8,
            )
        except Exception as exc:
            messagebox.showerror("Correlation scanner", str(exc))
            return

        self.scan_tree.delete(*self.scan_tree.get_children())
        for _, row in result.head(100).iterrows():
            self.scan_tree.insert(
                "",
                "end",
                values=(
                    row["feature"],
                    int(row["lag"]),
                    f"{row['correlation']:+.3f}",
                    int(row["sample_size"]),
                    self._fmt(row["first_half"]),
                    self._fmt(row["second_half"]),
                    f"{row['stability']:.2f}",
                    f"{row['score']:.3f}",
                ),
            )
        self.status_var.set(f"Scanner found {len(result)} valid feature/lag combinations.")


def launch_correlation_lab() -> None:
    app = CorrelationLab()
    app.mainloop()


if __name__ == "__main__":
    launch_correlation_lab()
