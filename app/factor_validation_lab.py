from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from core.panel_correlation_engine import scan_panel_correlations

DEFAULT_DATASET = ROOT / "artifacts" / "factor_validation_dataset.csv"
TARGETS = ("future_3m_return", "future_6m_return", "future_12m_return")


class FactorValidationLab(tk.Tk):
    def __init__(self, dataset_path: str | Path | None = None) -> None:
        super().__init__()
        self.title("Factor Validation Dataset")
        self.geometry("1500x930")
        self.minsize(1200, 760)
        self.data = pd.DataFrame()
        self.dataset_path = Path(dataset_path) if dataset_path else DEFAULT_DATASET
        self.target_var = tk.StringVar(value="future_6m_return")
        self.status_var = tk.StringVar(value="No dataset loaded")
        self.metric_vars = {key: tk.StringVar(value="-") for key in ("rows", "companies", "periods", "factors", "target_coverage")}
        self._build_ui()
        if self.dataset_path.exists():
            self.load_dataset(self.dataset_path)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=14)
        root.pack(fill="both", expand=True)
        header = ttk.Frame(root)
        header.pack(fill="x", pady=(0, 8))
        ttk.Label(header, text="Factor Validation Dataset", font=("Segoe UI", 18, "bold")).pack(side="left")
        ttk.Button(header, text="Load CSV", command=self.choose_dataset).pack(side="right")

        ttk.Label(
            root,
            text=(
                "Quarterly point-in-time panel for factor research. Financial factors are aligned to a conservative "
                "availability-date proxy before future 3M/6M/12M returns are calculated."
            ),
            wraplength=1380,
        ).pack(anchor="w", pady=(0, 10))

        metrics = ttk.Frame(root)
        metrics.pack(fill="x", pady=(0, 10))
        for idx, (title, key) in enumerate((
            ("Rows", "rows"), ("Companies", "companies"), ("Periods", "periods"),
            ("Numeric factors", "factors"), ("Target coverage", "target_coverage"),
        )):
            box = ttk.LabelFrame(metrics, text=title, padding=8)
            box.grid(row=0, column=idx, sticky="nsew", padx=(0, 7 if idx < 4 else 0))
            metrics.columnconfigure(idx, weight=1)
            ttk.Label(box, textvariable=self.metric_vars[key], font=("Segoe UI", 13, "bold")).pack(anchor="w")

        controls = ttk.Frame(root)
        controls.pack(fill="x", pady=(0, 8))
        ttk.Label(controls, text="Target").pack(side="left")
        ttk.Combobox(controls, textvariable=self.target_var, values=TARGETS, state="readonly", width=22).pack(side="left", padx=(8, 12))
        ttk.Button(controls, text="Scan factors", command=self.run_scan).pack(side="left")
        ttk.Label(controls, text="Default scan: factor level → future return, lags 0..4, Spearman").pack(side="left", padx=(12, 0))

        notebook = ttk.Notebook(root)
        notebook.pack(fill="both", expand=True)
        data_tab = ttk.Frame(notebook, padding=8)
        scan_tab = ttk.Frame(notebook, padding=8)
        notebook.add(data_tab, text="Dataset preview")
        notebook.add(scan_tab, text="Factor scanner")

        preview_columns = (
            "ticker", "report_date", "available_date", "cycle", "revenue_yoy", "monthly_revenue_3m_yoy",
            "gross_margin", "eps_yoy", "inventory_yoy", "roe_proxy", "capex_to_revenue",
            "pe", "pb", "future_3m_return", "future_6m_return", "future_12m_return",
        )
        self.preview_tree = ttk.Treeview(data_tab, columns=preview_columns, show="headings")
        for col in preview_columns:
            self.preview_tree.heading(col, text=col)
            self.preview_tree.column(col, width=115, anchor="center")
        self.preview_tree.pack(fill="both", expand=True)

        scan_columns = (
            "feature", "lag", "pooled", "company", "company_agree", "cross", "cross_agree", "cycle", "cycle_agree", "score"
        )
        self.scan_tree = ttk.Treeview(scan_tab, columns=scan_columns, show="headings")
        for col in scan_columns:
            self.scan_tree.heading(col, text=col.replace("_", " ").title())
            self.scan_tree.column(col, width=115, anchor="center")
        self.scan_tree.column("feature", width=190, anchor="w")
        self.scan_tree.pack(fill="both", expand=True)
        ttk.Label(root, textvariable=self.status_var).pack(anchor="w", pady=(8, 0))

    def choose_dataset(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if path:
            self.load_dataset(Path(path))

    def load_dataset(self, path: Path) -> None:
        try:
            frame = pd.read_csv(path)
            if frame.empty:
                raise ValueError("Dataset is empty")
            required = {"ticker", "report_date", "cycle"}
            missing = required - set(frame.columns)
            if missing:
                raise ValueError(f"Missing required columns: {sorted(missing)}")
            self.data = frame
            self.dataset_path = path
            self._refresh_preview()
            self.run_scan()
            self.status_var.set(f"Loaded {path.name}: {len(frame)} rows")
        except Exception as exc:
            messagebox.showerror("Factor Validation Dataset", str(exc))

    def _numeric_factors(self) -> list[str]:
        excluded = {"stock_id", *TARGETS, "price_at_available", "universe_revenue_yoy", "universe_revenue_yoy_delta"}
        result = []
        for col in self.data.columns:
            if col in excluded:
                continue
            numeric = pd.to_numeric(self.data[col], errors="coerce")
            if numeric.notna().sum() >= 12:
                result.append(col)
        return result

    def _refresh_preview(self) -> None:
        self.preview_tree.delete(*self.preview_tree.get_children())
        for _, row in self.data.head(250).iterrows():
            values = []
            for col in self.preview_tree["columns"]:
                value = row[col] if col in row.index else ""
                if isinstance(value, float) and pd.notna(value):
                    values.append(f"{value:.3f}")
                else:
                    values.append("" if pd.isna(value) else value)
            self.preview_tree.insert("", "end", values=values)

        target = self.target_var.get()
        coverage = self.data[target].notna().mean() if target in self.data else 0.0
        self.metric_vars["rows"].set(str(len(self.data)))
        self.metric_vars["companies"].set(str(self.data["ticker"].nunique()))
        self.metric_vars["periods"].set(str(self.data["report_date"].nunique()))
        self.metric_vars["factors"].set(str(len(self._numeric_factors())))
        self.metric_vars["target_coverage"].set(f"{coverage * 100:.0f}%")

    def run_scan(self) -> None:
        if self.data.empty:
            return
        target = self.target_var.get()
        if target not in self.data.columns:
            return
        self._refresh_preview()
        try:
            result = scan_panel_correlations(
                self.data,
                "ticker",
                "report_date",
                target,
                cycle_column="cycle",
                feature_columns=self._numeric_factors(),
                method="spearman",
                feature_transform="level",
                target_transform="level",
                lags=range(0, 5),
                min_samples=18,
                min_group_samples=3,
            )
        except Exception as exc:
            messagebox.showerror("Factor scanner", str(exc))
            return

        self.scan_tree.delete(*self.scan_tree.get_children())
        for _, row in result.head(100).iterrows():
            def fmt(name: str) -> str:
                value = row[name]
                return "-" if pd.isna(value) else f"{value:+.3f}"
            def pct(name: str) -> str:
                value = row[name]
                return "-" if pd.isna(value) else f"{value * 100:.0f}%"
            self.scan_tree.insert("", "end", values=(
                row["feature"], int(row["lag"]), fmt("pooled_correlation"), fmt("median_company_correlation"),
                pct("company_sign_agreement"), fmt("median_cross_sectional_correlation"), pct("cross_sectional_sign_agreement"),
                fmt("median_cycle_correlation"), pct("cycle_sign_agreement"), f"{row['generalization_score']:.3f}",
            ))
        self.status_var.set(f"Scanned {len(result)} factor/lag combinations for {target}.")


def launch_factor_validation_lab(dataset_path: str | Path | None = None) -> None:
    app = FactorValidationLab(dataset_path)
    app.mainloop()


if __name__ == "__main__":
    launch_factor_validation_lab()
