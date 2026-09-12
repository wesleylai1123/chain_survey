from __future__ import annotations

import json
import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = Path(
    os.environ.get(
        "COLLECTION_PROGRESS_ROOT",
        ROOT / "artifacts" / "persistent" / "factor_validation",
    )
)
DATASET_LABELS = {
    "TaiwanStockFinancialStatements": "Financial Statements",
    "TaiwanStockBalanceSheet": "Balance Sheet",
    "TaiwanStockCashFlowsStatement": "Cash Flow",
    "TaiwanStockMonthRevenue": "Monthly Revenue",
    "TaiwanStockPrice": "Price",
    "TaiwanStockPER": "Valuation",
}


class CollectionProgressDashboard(tk.Tk):
    def __init__(self, data_root: str | Path | None = None) -> None:
        super().__init__()
        self.title("Collection Progress Dashboard")
        self.geometry("1480x940")
        self.minsize(1180, 760)
        self.data_root = Path(data_root) if data_root else DEFAULT_ROOT

        self.overall_var = tk.StringVar(value="0.0%")
        self.company_var = tk.StringVar(value="0 / 0")
        self.batch_var = tk.StringVar(value="0 / 0")
        self.rows_var = tk.StringVar(value="0")
        self.failed_var = tk.StringVar(value="0")
        self.next_batch_var = tk.StringVar(value="-")
        self.updated_var = tk.StringVar(value="No collection state loaded")
        self._build()
        self.load()

    def _build(self) -> None:
        root = ttk.Frame(self, padding=16)
        root.pack(fill="both", expand=True)

        header = ttk.Frame(root)
        header.pack(fill="x")
        ttk.Label(header, text="Collection Progress Dashboard", font=("Segoe UI", 20, "bold")).pack(side="left")
        ttk.Button(header, text="Reload", command=self.load).pack(side="right")
        ttk.Button(header, text="Select data folder", command=self.choose_root).pack(side="right", padx=8)
        ttk.Label(
            root,
            text="Persistent Taiwan-universe factor collection: durable batches from factor-data, cache health, coverage, and the next resumable batch.",
        ).pack(anchor="w", pady=(6, 12))

        cards = ttk.Frame(root)
        cards.pack(fill="x", pady=(0, 12))
        card_specs = (
            ("Overall", self.overall_var),
            ("Companies", self.company_var),
            ("Batches", self.batch_var),
            ("Factor Rows", self.rows_var),
            ("Failed States", self.failed_var),
            ("Next Batch", self.next_batch_var),
        )
        for label, variable in card_specs:
            box = ttk.LabelFrame(cards, text=label, padding=10)
            box.pack(side="left", fill="x", expand=True, padx=4)
            ttk.Label(box, textvariable=variable, font=("Segoe UI", 18, "bold")).pack()

        self.progress = ttk.Progressbar(root, maximum=100.0, mode="determinate")
        self.progress.pack(fill="x", pady=(0, 14))

        body = ttk.Panedwindow(root, orient="horizontal")
        body.pack(fill="both", expand=True)
        left = ttk.Frame(body, padding=(0, 0, 8, 0))
        right = ttk.Frame(body, padding=(8, 0, 0, 0))
        body.add(left, weight=1)
        body.add(right, weight=2)

        coverage = ttk.LabelFrame(left, text="Dataset Coverage", padding=8)
        coverage.pack(fill="both", expand=True)
        self.coverage_tree = ttk.Treeview(
            coverage,
            columns=("dataset", "success", "failed", "pending", "coverage"),
            show="headings",
            height=9,
        )
        for col, width in (("dataset", 180), ("success", 80), ("failed", 70), ("pending", 80), ("coverage", 90)):
            self.coverage_tree.heading(col, text=col.title())
            self.coverage_tree.column(col, width=width, anchor="w" if col == "dataset" else "center")
        self.coverage_tree.pack(fill="both", expand=True)

        failed = ttk.LabelFrame(left, text="Failed Dataset States", padding=8)
        failed.pack(fill="both", expand=True, pady=(10, 0))
        self.failed_tree = ttk.Treeview(
            failed,
            columns=("stock", "dataset", "error"),
            show="headings",
            height=9,
        )
        for col, width in (("stock", 70), ("dataset", 150), ("error", 260)):
            self.failed_tree.heading(col, text=col.title())
            self.failed_tree.column(col, width=width, anchor="w")
        self.failed_tree.pack(fill="both", expand=True)

        recent = ttk.LabelFrame(right, text="Persistent Batch Progress", padding=8)
        recent.pack(fill="both", expand=True)
        self.batch_tree = ttk.Treeview(
            recent,
            columns=("batch", "companies", "rows", "first_stock", "last_stock", "report_start", "report_end"),
            show="headings",
        )
        widths = {"batch":70, "companies":90, "rows":90, "first_stock":100, "last_stock":100, "report_start":110, "report_end":110}
        for col in self.batch_tree["columns"]:
            self.batch_tree.heading(col, text=col.replace("_", " ").title())
            self.batch_tree.column(col, width=widths[col], anchor="center")
        self.batch_tree.pack(fill="both", expand=True)

        ttk.Label(root, textvariable=self.updated_var).pack(anchor="w", pady=(10, 0))

    def choose_root(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.data_root if self.data_root.exists() else ROOT)
        if selected:
            self.data_root = Path(selected)
            self.load()

    def _read_json(self, name: str) -> dict:
        path = self.data_root / name
        if not path.exists():
            raise FileNotFoundError(f"Missing {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    def load(self) -> None:
        try:
            status = self._read_json("collection_status.json")
            manifest = self._read_json("cache_manifest_latest.json")
            universe_path = self.data_root / "taiwan_stock_universe.csv"
            universe = pd.read_csv(universe_path) if universe_path.exists() else pd.DataFrame()

            total_companies = int(status.get("universe_companies", len(universe)))
            companies = int(status.get("companies_materialized", 0))
            total_batches = int(status.get("total_batches", 0))
            completed_batches = int(status.get("completed_batch_count", 0))
            factor_rows = int(status.get("factor_rows", 0))
            next_batch = status.get("next_batch")
            progress = (completed_batches / total_batches * 100.0) if total_batches else 0.0

            entries = list(manifest.get("entries", {}).values())
            failed_entries = [entry for entry in entries if entry.get("status") == "failed"]

            self.overall_var.set(f"{progress:.1f}%")
            self.company_var.set(f"{companies:,} / {total_companies:,}")
            self.batch_var.set(f"{completed_batches} / {total_batches}")
            self.rows_var.set(f"{factor_rows:,}")
            self.failed_var.set(str(len(failed_entries)))
            self.next_batch_var.set("Done" if next_batch is None else str(next_batch))
            self.progress["value"] = progress

            self._load_coverage(entries, total_companies)
            self._load_failures(failed_entries)
            self._load_batches()
            self.updated_var.set(
                f"Data: {self.data_root} | updated {status.get('updated_at', '')} | durable completed batches: {completed_batches}/{total_batches}"
            )
        except Exception as exc:
            self.updated_var.set(str(exc))
            if self.winfo_viewable():
                messagebox.showerror("Collection Progress Dashboard", str(exc))

    def _load_coverage(self, entries: list[dict], total_companies: int) -> None:
        self.coverage_tree.delete(*self.coverage_tree.get_children())
        by_dataset: dict[str, list[dict]] = {}
        for entry in entries:
            by_dataset.setdefault(str(entry.get("dataset_key", "Unknown")), []).append(entry)
        keys = list(DATASET_LABELS)
        for key in by_dataset:
            if key not in keys:
                keys.append(key)
        for key in keys:
            group = by_dataset.get(key, [])
            success = sum(item.get("status") == "success" for item in group)
            failed = sum(item.get("status") == "failed" for item in group)
            pending = max(total_companies - success, 0)
            pct = success / total_companies * 100.0 if total_companies else 0.0
            self.coverage_tree.insert("", "end", values=(DATASET_LABELS.get(key, key), success, failed, pending, f"{pct:.1f}%"))

    def _load_failures(self, failed_entries: list[dict]) -> None:
        self.failed_tree.delete(*self.failed_tree.get_children())
        for entry in failed_entries[:100]:
            self.failed_tree.insert(
                "", "end",
                values=(entry.get("stock_id", ""), DATASET_LABELS.get(entry.get("dataset_key", ""), entry.get("dataset_key", "")), entry.get("error", "") or ""),
            )
        if not failed_entries:
            self.failed_tree.insert("", "end", values=("-", "No failures", "All persisted dataset states are healthy"))

    def _load_batches(self) -> None:
        self.batch_tree.delete(*self.batch_tree.get_children())
        batch_dir = self.data_root / "batches"
        if not batch_dir.exists():
            return
        for path in sorted(batch_dir.glob("factor_batch_*.csv"), reverse=True)[:30]:
            frame = pd.read_csv(path)
            batch_number = path.stem.rsplit("_", 1)[-1]
            stocks = frame["stock_id"].astype(str) if "stock_id" in frame.columns else pd.Series(dtype=str)
            reports = pd.to_datetime(frame["report_date"], errors="coerce") if "report_date" in frame.columns else pd.Series(dtype="datetime64[ns]")
            self.batch_tree.insert(
                "", "end",
                values=(
                    int(batch_number),
                    stocks.nunique(),
                    len(frame),
                    stocks.min() if not stocks.empty else "",
                    stocks.max() if not stocks.empty else "",
                    reports.min().date().isoformat() if not reports.empty and reports.notna().any() else "",
                    reports.max().date().isoformat() if not reports.empty and reports.notna().any() else "",
                ),
            )


def launch_collection_progress_dashboard() -> None:
    CollectionProgressDashboard().mainloop()


if __name__ == "__main__":
    launch_collection_progress_dashboard()
