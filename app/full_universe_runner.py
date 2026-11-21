from __future__ import annotations

import json
import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = Path(os.environ.get("FACTOR_CACHE_MANIFEST", ROOT / "artifacts" / "factor_cache_manifest.json"))
DEFAULT_UNIVERSE = Path(os.environ.get("TAIWAN_UNIVERSE", ROOT / "artifacts" / "taiwan_stock_universe.csv"))
DEFAULT_COLLECTION_STATUS = Path(os.environ.get("FACTOR_COLLECTION_STATUS", ROOT / "artifacts" / "collection_status.json"))
DATASETS_PER_STOCK = 6


class FullUniverseRunnerStatus(tk.Tk):
    def __init__(self, manifest_path: str | Path | None = None, universe_path: str | Path | None = None, collection_status_path: str | Path | None = None) -> None:
        super().__init__()
        self.title("Full-Universe Data Runner")
        self.geometry("1400x860")
        self.manifest_path = Path(manifest_path) if manifest_path else DEFAULT_MANIFEST
        self.universe_path = Path(universe_path) if universe_path else DEFAULT_UNIVERSE
        self.collection_status_path = Path(collection_status_path) if collection_status_path else DEFAULT_COLLECTION_STATUS
        self.status = tk.StringVar(value="No runner state loaded")
        self.universe_var = tk.StringVar(value="0")
        self.cached_var = tk.StringVar(value="0")
        self.pending_var = tk.StringVar(value="0")
        self.failed_var = tk.StringVar(value="0")
        self.batch_progress_var = tk.StringVar(value="0 / 0")
        self.factor_rows_var = tk.StringVar(value="0")
        self._build()
        if self.manifest_path.exists():
            self.load()

    def _build(self) -> None:
        root = ttk.Frame(self, padding=14)
        root.pack(fill="both", expand=True)
        header = ttk.Frame(root)
        header.pack(fill="x")
        ttk.Label(header, text="Full-Universe Data Runner", font=("Segoe UI", 18, "bold")).pack(side="left")
        ttk.Button(header, text="Reload", command=self.load).pack(side="right")
        ttk.Button(header, text="Select manifest", command=self.choose_manifest).pack(side="right", padx=8)
        ttk.Label(root, text="Persistent Taiwan factor collection: durable batch progress is stored separately from the raw API cache, while incremental cache reduces refetching.").pack(anchor="w", pady=(8,12))

        cards = ttk.Frame(root)
        cards.pack(fill="x", pady=(0,8))
        for label, var in (("Universe", self.universe_var), ("Persistent batches", self.batch_progress_var), ("Factor rows", self.factor_rows_var)):
            box = ttk.LabelFrame(cards, text=label, padding=12)
            box.pack(side="left", fill="x", expand=True, padx=5)
            ttk.Label(box, textvariable=var, font=("Segoe UI", 20, "bold")).pack()

        cache_cards = ttk.Frame(root)
        cache_cards.pack(fill="x", pady=(0,12))
        for label, var in (("Cached datasets", self.cached_var), ("Pending datasets", self.pending_var), ("Failed datasets", self.failed_var)):
            box = ttk.LabelFrame(cache_cards, text=label, padding=10)
            box.pack(side="left", fill="x", expand=True, padx=5)
            ttk.Label(box, textvariable=var, font=("Segoe UI", 16, "bold")).pack()

        cols = ("stock","dataset","status","start","end","rows","last_success","error")
        self.tree = ttk.Treeview(root, columns=cols, show="headings")
        widths = {"stock":85,"dataset":180,"status":90,"start":100,"end":100,"rows":80,"last_success":190,"error":360}
        for col in cols:
            self.tree.heading(col, text=col.replace("_", " ").title())
            self.tree.column(col, width=widths[col], anchor="w")
        self.tree.pack(fill="both", expand=True)
        ttk.Label(root, textvariable=self.status).pack(anchor="w", pady=(8,0))

    def choose_manifest(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if path:
            self.manifest_path = Path(path)
            self.load()

    def load(self) -> None:
        try:
            payload = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            entries = list(payload.get("entries", {}).values())
            universe_count = len(pd.read_csv(self.universe_path)) if self.universe_path.exists() else 0
            success = sum(e.get("status") == "success" for e in entries)
            failed = sum(e.get("status") == "failed" for e in entries)
            expected = universe_count * DATASETS_PER_STOCK
            pending = max(expected - success, 0)
            self.universe_var.set(str(universe_count))
            self.cached_var.set(str(success))
            self.pending_var.set(str(pending))
            self.failed_var.set(str(failed))

            persistent = {}
            if self.collection_status_path.exists():
                persistent = json.loads(self.collection_status_path.read_text(encoding="utf-8"))
            completed = int(persistent.get("completed_batch_count", 0) or 0)
            total_batches = int(persistent.get("total_batches", 0) or 0)
            factor_rows = int(persistent.get("factor_rows", 0) or 0)
            next_batch = persistent.get("next_batch")
            self.batch_progress_var.set(f"{completed} / {total_batches}" if total_batches else "0 / 0")
            self.factor_rows_var.set(f"{factor_rows:,}")

            self.tree.delete(*self.tree.get_children())
            for entry in sorted(entries, key=lambda e: (e.get("status") != "failed", e.get("stock_id", ""), e.get("dataset_key", ""))):
                self.tree.insert("", "end", values=(
                    entry.get("stock_id", ""), entry.get("dataset_key", ""), entry.get("status", ""),
                    entry.get("start_date", ""), entry.get("end_date", ""), entry.get("row_count", 0),
                    entry.get("last_success", "") or "", entry.get("error", "") or "",
                ))
            persistent_text = f" | persistent next batch {next_batch}" if persistent else " | no persistent snapshot loaded"
            self.status.set(f"Manifest: {self.manifest_path} | updated {payload.get('updated_at','')} | {len(entries)} cached dataset states{persistent_text}")
        except Exception as exc:
            messagebox.showerror("Full-Universe Data Runner", str(exc))


if __name__ == "__main__":
    FullUniverseRunnerStatus().mainloop()
