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
DATASETS_PER_STOCK = 6


class FullUniverseRunnerStatus(tk.Tk):
    def __init__(self, manifest_path: str | Path | None = None, universe_path: str | Path | None = None) -> None:
        super().__init__()
        self.title("Full-Universe Data Runner")
        self.geometry("1320x820")
        self.manifest_path = Path(manifest_path) if manifest_path else DEFAULT_MANIFEST
        self.universe_path = Path(universe_path) if universe_path else DEFAULT_UNIVERSE
        self.status = tk.StringVar(value="No runner state loaded")
        self.universe_var = tk.StringVar(value="0")
        self.cached_var = tk.StringVar(value="0")
        self.pending_var = tk.StringVar(value="0")
        self.failed_var = tk.StringVar(value="0")
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
        ttk.Label(root, text="Persistent cache status for Taiwan full-universe factor collection. Cached datasets are reused; only missing or newer ranges are fetched.").pack(anchor="w", pady=(8,12))

        cards = ttk.Frame(root)
        cards.pack(fill="x", pady=(0,12))
        for label, var in (("Universe", self.universe_var), ("Cached datasets", self.cached_var), ("Pending datasets", self.pending_var), ("Failed datasets", self.failed_var)):
            box = ttk.LabelFrame(cards, text=label, padding=12)
            box.pack(side="left", fill="x", expand=True, padx=5)
            ttk.Label(box, textvariable=var, font=("Segoe UI", 20, "bold")).pack()

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
            universe_count = 0
            if self.universe_path.exists():
                universe_count = len(pd.read_csv(self.universe_path))
            success = sum(e.get("status") == "success" for e in entries)
            failed = sum(e.get("status") == "failed" for e in entries)
            expected = universe_count * DATASETS_PER_STOCK
            pending = max(expected - success, 0)
            self.universe_var.set(str(universe_count))
            self.cached_var.set(str(success))
            self.pending_var.set(str(pending))
            self.failed_var.set(str(failed))
            self.tree.delete(*self.tree.get_children())
            for entry in sorted(entries, key=lambda e: (e.get("status") != "failed", e.get("stock_id", ""), e.get("dataset_key", ""))):
                self.tree.insert("", "end", values=(
                    entry.get("stock_id", ""), entry.get("dataset_key", ""), entry.get("status", ""),
                    entry.get("start_date", ""), entry.get("end_date", ""), entry.get("row_count", 0),
                    entry.get("last_success", "") or "", entry.get("error", "") or "",
                ))
            self.status.set(f"Manifest: {self.manifest_path} | updated {payload.get('updated_at','')} | {len(entries)} cached dataset states")
        except Exception as exc:
            messagebox.showerror("Full-Universe Data Runner", str(exc))


if __name__ == "__main__":
    FullUniverseRunnerStatus().mainloop()
