from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from core.turnaround_engine import TARGET_COLUMNS, build_turnaround_radar, validate_turnaround_signal

DEFAULT_DATASET = ROOT / "artifacts" / "factor_validation_dataset.csv"


class TurnaroundRadar(tk.Tk):
    def __init__(self, dataset_path: str | Path | None = None) -> None:
        super().__init__()
        self.title("Turnaround / Inflection Radar")
        self.geometry("1520x940")
        self.minsize(1220, 760)
        self.dataset_path = Path(dataset_path) if dataset_path else DEFAULT_DATASET
        self.data = pd.DataFrame()
        self.radar = pd.DataFrame()
        self.target_var = tk.StringVar(value="future_6m_return")
        self.status_var = tk.StringVar(value="No dataset loaded")
        self.metric_vars = {
            key: tk.StringVar(value="-")
            for key in ("companies", "recovery", "early_reversal", "median_score", "ic", "spread")
        }
        self._build_ui()
        if self.dataset_path.exists():
            self.load_dataset(self.dataset_path)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=14)
        root.pack(fill="both", expand=True)

        header = ttk.Frame(root)
        header.pack(fill="x", pady=(0, 8))
        ttk.Label(header, text="Turnaround / Inflection Radar", font=("Segoe UI", 18, "bold")).pack(side="left")
        ttk.Button(header, text="Load factor CSV", command=self.choose_dataset).pack(side="right")

        ttk.Label(
            root,
            text=(
                "Ranks companies by fundamental inflection, not absolute quality. The score combines revenue acceleration, "
                "margin momentum, EPS acceleration, cash-flow improvement, inventory relief and recovery-cycle context. "
                "Future returns are used only for validation, never as score inputs."
            ),
            wraplength=1450,
        ).pack(anchor="w", pady=(0, 10))

        cards = ttk.Frame(root)
        cards.pack(fill="x", pady=(0, 10))
        card_defs = (
            ("Companies", "companies"),
            ("Recovery", "recovery"),
            ("Early reversal", "early_reversal"),
            ("Median score", "median_score"),
            ("6M Spearman IC", "ic"),
            ("Top-bottom spread", "spread"),
        )
        for idx, (title, key) in enumerate(card_defs):
            box = ttk.LabelFrame(cards, text=title, padding=8)
            box.grid(row=0, column=idx, sticky="nsew", padx=(0, 7 if idx < len(card_defs) - 1 else 0))
            cards.columnconfigure(idx, weight=1)
            ttk.Label(box, textvariable=self.metric_vars[key], font=("Segoe UI", 12, "bold")).pack(anchor="w")

        controls = ttk.Frame(root)
        controls.pack(fill="x", pady=(0, 8))
        ttk.Label(controls, text="Validation target").pack(side="left")
        ttk.Combobox(controls, textvariable=self.target_var, values=TARGET_COLUMNS, state="readonly", width=22).pack(side="left", padx=(8, 12))
        ttk.Button(controls, text="Recalculate", command=self.refresh).pack(side="left")
        ttk.Label(
            controls,
            text="Score = same-period cross-sectional percentile of improving fundamental trends; no fixed buy/sell threshold.",
        ).pack(side="left", padx=(12, 0))

        notebook = ttk.Notebook(root)
        notebook.pack(fill="both", expand=True)
        radar_tab = ttk.Frame(notebook, padding=8)
        validation_tab = ttk.Frame(notebook, padding=8)
        notebook.add(radar_tab, text="Latest radar")
        notebook.add(validation_tab, text="Signal validation")

        radar_columns = (
            "rank", "ticker", "name", "industry", "period", "stage", "score", "confidence",
            "revenue_growth", "revenue_accel", "gm_momentum", "eps_accel", "signals", "drivers",
        )
        self.radar_tree = ttk.Treeview(radar_tab, columns=radar_columns, show="headings", height=24)
        headings = {
            "rank": "Rank",
            "ticker": "Ticker",
            "name": "Company",
            "industry": "Industry",
            "period": "Period",
            "stage": "Stage",
            "score": "Score",
            "confidence": "Confidence",
            "revenue_growth": "Revenue YoY",
            "revenue_accel": "Revenue Accel",
            "gm_momentum": "GM Δ",
            "eps_accel": "EPS Accel",
            "signals": "+ Signals",
            "drivers": "Top Drivers",
        }
        widths = {
            "rank": 55, "ticker": 80, "name": 110, "industry": 130, "period": 95, "stage": 110,
            "score": 75, "confidence": 90, "revenue_growth": 95, "revenue_accel": 100, "gm_momentum": 80,
            "eps_accel": 90, "signals": 70, "drivers": 360,
        }
        for column in radar_columns:
            self.radar_tree.heading(column, text=headings[column])
            self.radar_tree.column(column, width=widths[column], anchor="w" if column in {"name", "industry", "stage", "drivers"} else "center")
        self.radar_tree.pack(fill="both", expand=True)

        validation_columns = ("target", "samples", "spearman_ic", "top_quintile", "bottom_quintile", "spread")
        self.validation_tree = ttk.Treeview(validation_tab, columns=validation_columns, show="headings", height=10)
        validation_headings = {
            "target": "Forward return",
            "samples": "Samples",
            "spearman_ic": "Spearman IC",
            "top_quintile": "Top 20% avg",
            "bottom_quintile": "Bottom 20% avg",
            "spread": "Top - Bottom",
        }
        for column in validation_columns:
            self.validation_tree.heading(column, text=validation_headings[column])
            self.validation_tree.column(column, width=180, anchor="center")
        self.validation_tree.pack(fill="x", pady=(0, 14))
        ttk.Label(
            validation_tab,
            text=(
                "Interpretation: IC measures monotonic relationship between the point-in-time turnaround score and later returns. "
                "The quintile spread compares the average future return of the highest-score 20% with the lowest-score 20%. "
                "These are research diagnostics, not a prediction guarantee."
            ),
            wraplength=1320,
        ).pack(anchor="w")

        ttk.Label(root, textvariable=self.status_var).pack(anchor="w", pady=(8, 0))

    @staticmethod
    def _pct(value: object) -> str:
        return "-" if pd.isna(value) else f"{float(value) * 100:+.1f}%"

    @staticmethod
    def _number(value: object, digits: int = 1) -> str:
        return "-" if pd.isna(value) else f"{float(value):.{digits}f}"

    def choose_dataset(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if path:
            self.load_dataset(Path(path))

    def load_dataset(self, path: Path) -> None:
        try:
            frame = pd.read_csv(path)
            required = {"ticker", "report_date"}
            missing = required - set(frame.columns)
            if frame.empty:
                raise ValueError("Dataset is empty")
            if missing:
                raise ValueError(f"Missing required columns: {sorted(missing)}")
            self.data = frame
            self.dataset_path = path
            self.refresh()
            self.status_var.set(f"Loaded {path.name}: {len(frame)} point-in-time observations")
        except Exception as exc:
            messagebox.showerror("Turnaround Radar", str(exc))

    def refresh(self) -> None:
        if self.data.empty:
            return
        try:
            self.radar = build_turnaround_radar(self.data)
            validations = [validate_turnaround_signal(self.data, target=target) for target in TARGET_COLUMNS if target in self.data.columns]
        except Exception as exc:
            messagebox.showerror("Turnaround Radar", str(exc))
            return

        self.radar_tree.delete(*self.radar_tree.get_children())
        for _, row in self.radar.head(150).iterrows():
            self.radar_tree.insert(
                "",
                "end",
                values=(
                    int(row["rank"]),
                    row.get("ticker", ""),
                    row.get("name", ""),
                    row.get("industry", ""),
                    row.get("report_date", ""),
                    row.get("stage", ""),
                    self._number(row.get("turnaround_score")),
                    f"{self._number(row.get('confidence'), 0)}%" if pd.notna(row.get("confidence")) else "-",
                    self._pct(row.get("revenue_growth")),
                    self._pct(row.get("revenue_acceleration")),
                    self._pct(row.get("gross_margin_momentum")),
                    self._pct(row.get("eps_acceleration")),
                    int(row.get("improving_signal_count", 0)),
                    row.get("driver_summary", ""),
                ),
            )

        self.validation_tree.delete(*self.validation_tree.get_children())
        for result in validations:
            self.validation_tree.insert(
                "",
                "end",
                values=(
                    result["target"],
                    result["samples"],
                    self._number(result["spearman_ic"], 3),
                    self._pct(result["top_quintile_return"]),
                    self._pct(result["bottom_quintile_return"]),
                    self._pct(result["top_bottom_spread"]),
                ),
            )

        selected = next((item for item in validations if item["target"] == self.target_var.get()), None)
        self.metric_vars["companies"].set(str(len(self.radar)))
        self.metric_vars["recovery"].set(str(int((self.radar["stage"] == "Recovery").sum())) if not self.radar.empty else "0")
        self.metric_vars["early_reversal"].set(str(int((self.radar["stage"] == "Early reversal").sum())) if not self.radar.empty else "0")
        self.metric_vars["median_score"].set(self._number(self.radar["turnaround_score"].median()) if not self.radar.empty else "-")
        if selected:
            self.metric_vars["ic"].set(self._number(selected["spearman_ic"], 3))
            self.metric_vars["spread"].set(self._pct(selected["top_bottom_spread"]))
        else:
            self.metric_vars["ic"].set("-")
            self.metric_vars["spread"].set("-")
        self.status_var.set(f"Radar updated: {len(self.radar)} companies ranked from {self.dataset_path.name}")


def launch_turnaround_radar(dataset_path: str | Path | None = None) -> None:
    app = TurnaroundRadar(dataset_path)
    app.mainloop()


if __name__ == "__main__":
    launch_turnaround_radar()
