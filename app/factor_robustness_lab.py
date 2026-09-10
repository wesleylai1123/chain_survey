from __future__ import annotations

import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from core.factor_validation_engine import scan_oos_factors

DEFAULT_DATASET = Path(os.environ.get("FACTOR_VALIDATION_DATASET", ROOT / "artifacts" / "factor_validation_dataset.csv"))
TARGETS = ("future_3m_return", "future_6m_return", "future_12m_return")


class FactorRobustnessLab(tk.Tk):
    def __init__(self, dataset_path: str | Path | None = None) -> None:
        super().__init__()
        self.title("Factor Robustness Lab")
        self.geometry("1420x900")
        self.data = pd.DataFrame()
        self.path = Path(dataset_path) if dataset_path else DEFAULT_DATASET
        self.target_var = tk.StringVar(value="future_6m_return")
        self.neutral_var = tk.BooleanVar(value=True)
        self.train_var = tk.DoubleVar(value=0.70)
        self.status_var = tk.StringVar(value="No dataset loaded")
        self._build()
        if self.path.exists():
            self.load(self.path)

    def _build(self) -> None:
        root = ttk.Frame(self, padding=14)
        root.pack(fill="both", expand=True)
        header = ttk.Frame(root)
        header.pack(fill="x")
        ttk.Label(header, text="Factor Robustness Lab", font=("Segoe UI", 18, "bold")).pack(side="left")
        ttk.Button(header, text="Load CSV", command=self.choose).pack(side="right")
        ttk.Label(root, text="Industry-neutral + chronological out-of-sample validation. A factor should survive both before it becomes a Transformation rule.").pack(anchor="w", pady=(8,12))

        controls = ttk.Frame(root)
        controls.pack(fill="x", pady=(0,10))
        ttk.Label(controls, text="Target").pack(side="left")
        ttk.Combobox(controls, textvariable=self.target_var, values=TARGETS, state="readonly", width=22).pack(side="left", padx=(6,16))
        ttk.Checkbutton(controls, text="Industry neutral", variable=self.neutral_var).pack(side="left")
        ttk.Label(controls, text="Train fraction").pack(side="left", padx=(16,6))
        ttk.Spinbox(controls, from_=0.5, to=0.9, increment=0.05, textvariable=self.train_var, width=7).pack(side="left")
        ttk.Button(controls, text="Run robustness scan", command=self.run_scan).pack(side="left", padx=(16,0))

        cols = ("feature","split","in_r","out_r","direction","degradation","in_n","out_n","score")
        self.tree = ttk.Treeview(root, columns=cols, show="headings")
        headings = {"feature":"Factor","split":"OOS starts","in_r":"In-sample r","out_r":"Out-of-sample r","direction":"Same direction","degradation":"|r| degradation","in_n":"Train N","out_n":"Test N","score":"Robust score"}
        for col in cols:
            self.tree.heading(col, text=headings[col])
            self.tree.column(col, width=135, anchor="center")
        self.tree.column("feature", width=220, anchor="w")
        self.tree.pack(fill="both", expand=True)
        ttk.Label(root, textvariable=self.status_var).pack(anchor="w", pady=(8,0))

    def choose(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("CSV", "*.csv")])
        if path:
            self.load(Path(path))

    def load(self, path: Path) -> None:
        try:
            data = pd.read_csv(path)
            required = {"ticker","report_date","industry",*TARGETS}
            missing = required - set(data.columns)
            if missing:
                raise ValueError(f"Missing columns: {sorted(missing)}")
            self.data = data
            self.path = path
            self.run_scan()
        except Exception as exc:
            messagebox.showerror("Factor Robustness Lab", str(exc))

    def _factors(self) -> list[str]:
        excluded = {"stock_id",*TARGETS,"price_at_available","universe_revenue_yoy","universe_revenue_yoy_delta"}
        factors=[]
        for col in self.data.columns:
            if col in excluded:
                continue
            if pd.to_numeric(self.data[col], errors="coerce").notna().sum() >= 18:
                factors.append(col)
        return factors

    def run_scan(self) -> None:
        if self.data.empty:
            return
        try:
            result = scan_oos_factors(self.data, self.target_var.get(), feature_columns=self._factors(), industry_neutral=self.neutral_var.get(), train_fraction=float(self.train_var.get()))
        except Exception as exc:
            messagebox.showerror("Robustness scan", str(exc))
            return
        self.tree.delete(*self.tree.get_children())
        for _, row in result.head(100).iterrows():
            self.tree.insert("", "end", values=(
                row["feature"], row["split_date"], f"{row['in_sample_r']:+.3f}", f"{row['out_of_sample_r']:+.3f}",
                "YES" if row["direction_consistent"] else "NO", f"{row['degradation']:+.3f}", int(row["in_sample_samples"]), int(row["out_of_sample_samples"]), f"{row['robust_score']:.3f}"
            ))
        self.status_var.set(f"{len(self.data)} rows | {self.data['ticker'].nunique()} companies | {len(result)} factors validated | industry-neutral={self.neutral_var.get()}")


def launch_factor_robustness_lab(dataset_path: str | Path | None = None) -> None:
    FactorRobustnessLab(dataset_path).mainloop()


if __name__ == "__main__":
    launch_factor_robustness_lab()
