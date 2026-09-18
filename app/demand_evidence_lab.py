from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from core.evidence_demand_engine import infer_demand_state, score_evidence

DEFAULT_EVIDENCE = ROOT / "data" / "evidence_observations.csv"


class DemandEvidenceLab(tk.Tk):
    def __init__(self, evidence_path: str | Path | None = None) -> None:
        super().__init__()
        self.title("Evidence-based Demand Inference")
        self.geometry("1540x940")
        self.minsize(1240, 760)
        self.evidence_path = Path(evidence_path) if evidence_path else DEFAULT_EVIDENCE
        self.data = pd.DataFrame()
        self.result: dict[str, object] = {}
        self.theme_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="No evidence loaded")
        self.metric_vars = {
            key: tk.StringVar(value="-")
            for key in ("score", "state", "confidence", "chains", "groups", "conflicts")
        }
        self._build_ui()
        if self.evidence_path.exists():
            self.load_evidence(self.evidence_path)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=14)
        root.pack(fill="both", expand=True)

        header = ttk.Frame(root)
        header.pack(fill="x", pady=(0, 8))
        ttk.Label(header, text="Evidence-based Demand Inference", font=("Segoe UI", 18, "bold")).pack(side="left")
        ttk.Button(header, text="Load evidence CSV", command=self.choose_evidence).pack(side="right")

        ttk.Label(
            root,
            text=(
                "Demand is inferred from evidence, not declared from headlines. Each observation is discounted by source "
                "reliability and freshness, repeated reports of the same causal event are deduplicated, and independent "
                "supply-chain confirmations raise confidence. The bundled dataset is illustrative demo data only."
            ),
            wraplength=1460,
        ).pack(anchor="w", pady=(0, 10))

        cards = ttk.Frame(root)
        cards.pack(fill="x", pady=(0, 10))
        for idx, (title, key) in enumerate((
            ("Demand score", "score"),
            ("State", "state"),
            ("Confidence", "confidence"),
            ("Independent chains", "chains"),
            ("Evidence groups", "groups"),
            ("Conflicts", "conflicts"),
        )):
            box = ttk.LabelFrame(cards, text=title, padding=8)
            box.grid(row=0, column=idx, sticky="nsew", padx=(0, 7 if idx < 5 else 0))
            cards.columnconfigure(idx, weight=1)
            ttk.Label(box, textvariable=self.metric_vars[key], font=("Segoe UI", 12, "bold")).pack(anchor="w")

        controls = ttk.Frame(root)
        controls.pack(fill="x", pady=(0, 8))
        ttk.Label(controls, text="Theme").pack(side="left")
        self.theme_combo = ttk.Combobox(controls, textvariable=self.theme_var, state="readonly", width=28)
        self.theme_combo.pack(side="left", padx=(8, 12))
        ttk.Button(controls, text="Recalculate", command=self.refresh).pack(side="left")
        ttk.Label(
            controls,
            text="Formula: signal × source reliability × exponential freshness; duplicate causal groups count once.",
        ).pack(side="left", padx=(12, 0))

        notebook = ttk.Notebook(root)
        notebook.pack(fill="both", expand=True)
        dim_tab = ttk.Frame(notebook, padding=8)
        evidence_tab = ttk.Frame(notebook, padding=8)
        raw_tab = ttk.Frame(notebook, padding=8)
        notebook.add(dim_tab, text="Demand dimensions")
        notebook.add(evidence_tab, text="Evidence trace")
        notebook.add(raw_tab, text="Raw observations")

        dim_columns = ("dimension", "score", "confidence", "groups")
        self.dimension_tree = ttk.Treeview(dim_tab, columns=dim_columns, show="headings", height=12)
        for col, title, width in (
            ("dimension", "Dimension", 230),
            ("score", "Score", 120),
            ("confidence", "Confidence", 140),
            ("groups", "Evidence groups", 130),
        ):
            self.dimension_tree.heading(col, text=title)
            self.dimension_tree.column(col, width=width, anchor="center" if col != "dimension" else "w")
        self.dimension_tree.pack(fill="x", pady=(0, 12))
        ttk.Label(
            dim_tab,
            text=(
                "Suggested interpretation: Buyer commitment and order/backlog show willingness to spend; physical throughput "
                "is the highest-weight confirmation; market tightness tests whether demand is stressing supply; financial "
                "results are treated as lagging confirmation."
            ),
            wraplength=1350,
        ).pack(anchor="w")

        ev_columns = ("chain", "dimension", "group", "indicator", "signal", "confidence", "observations", "latest", "sources")
        self.evidence_tree = ttk.Treeview(evidence_tab, columns=ev_columns, show="headings", height=22)
        widths = {
            "chain": 110, "dimension": 150, "group": 150, "indicator": 280, "signal": 90,
            "confidence": 100, "observations": 95, "latest": 100, "sources": 210,
        }
        for col in ev_columns:
            self.evidence_tree.heading(col, text=col.replace("_", " ").title())
            self.evidence_tree.column(col, width=widths[col], anchor="w" if col in {"chain", "dimension", "group", "indicator", "sources"} else "center")
        self.evidence_tree.pack(fill="both", expand=True)

        raw_columns = ("id", "date", "chain", "indicator", "signal", "reliability", "freshness", "effective", "source_type")
        self.raw_tree = ttk.Treeview(raw_tab, columns=raw_columns, show="headings", height=22)
        for col in raw_columns:
            self.raw_tree.heading(col, text=col.replace("_", " ").title())
            self.raw_tree.column(col, width=145 if col in {"indicator", "source_type"} else 105, anchor="center")
        self.raw_tree.column("indicator", width=300, anchor="w")
        self.raw_tree.pack(fill="both", expand=True)

        ttk.Label(root, textvariable=self.status_var).pack(anchor="w", pady=(8, 0))

    def choose_evidence(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if path:
            self.load_evidence(Path(path))

    def load_evidence(self, path: Path) -> None:
        try:
            frame = pd.read_csv(path)
            if frame.empty:
                raise ValueError("Evidence dataset is empty")
            self.data = frame
            self.evidence_path = path
            themes = sorted(frame["theme"].dropna().astype(str).unique())
            if not themes:
                raise ValueError("No theme found in evidence dataset")
            self.theme_combo["values"] = themes
            if self.theme_var.get() not in themes:
                self.theme_var.set(themes[0])
            self.refresh()
            self.status_var.set(f"Loaded {path.name}: {len(frame)} raw observations")
        except Exception as exc:
            messagebox.showerror("Demand Evidence Lab", str(exc))

    @staticmethod
    def _num(value: object, digits: int = 1) -> str:
        return "-" if pd.isna(value) else f"{float(value):.{digits}f}"

    def refresh(self) -> None:
        if self.data.empty or not self.theme_var.get():
            return
        try:
            selected = self.data[self.data["theme"].astype(str) == self.theme_var.get()].copy()
            self.result = infer_demand_state(selected, theme=self.theme_var.get())
            scored = score_evidence(selected)
        except Exception as exc:
            messagebox.showerror("Demand Evidence Lab", str(exc))
            return

        self.metric_vars["score"].set(self._num(self.result["score"]))
        self.metric_vars["state"].set(str(self.result["state"]))
        self.metric_vars["confidence"].set(f"{self._num(self.result['confidence'], 0)}%")
        self.metric_vars["chains"].set(f"{self.result['positive_chains']} / {self.result['independent_chains']} positive")
        self.metric_vars["groups"].set(str(self.result["deduplicated_groups"]))
        self.metric_vars["conflicts"].set(str(len(self.result["conflicting_evidence"])))

        self.dimension_tree.delete(*self.dimension_tree.get_children())
        dimensions = self.result["dimensions"]
        for _, row in dimensions.iterrows():
            self.dimension_tree.insert("", "end", values=(
                row["dimension"].replace("_", " ").title(),
                self._num(row["score"]),
                f"{self._num(row['confidence'], 0)}%",
                int(row["groups"]),
            ))

        self.evidence_tree.delete(*self.evidence_tree.get_children())
        groups = self.result["evidence_groups"]
        for _, row in groups.iterrows():
            self.evidence_tree.insert("", "end", values=(
                row["chain"], row["dimension"], row["evidence_group"], row["indicator"],
                f"{float(row['group_signal']):+.3f}", f"{float(row['group_confidence']) * 100:.0f}%",
                int(row["observation_count"]), row["latest_date"], row["source_types"],
            ))

        self.raw_tree.delete(*self.raw_tree.get_children())
        for _, row in scored.sort_values("effective_signal", ascending=False).iterrows():
            self.raw_tree.insert("", "end", values=(
                row["evidence_id"], row["as_of_date"].date().isoformat(), row["chain"], row["indicator"],
                f"{float(row['signal']):+.2f}", f"{float(row['reliability_used']):.2f}",
                f"{float(row['freshness']):.2f}", f"{float(row['effective_signal']):+.3f}", row["source_type"],
            ))
        self.status_var.set(
            f"{self.result['theme']} as of {self.result['as_of_date']}: "
            f"{self.result['state']} ({self.result['score']:.1f}/100), "
            f"{self.result['raw_observations']} observations → {self.result['deduplicated_groups']} causal groups"
        )


def launch_demand_evidence_lab(evidence_path: str | Path | None = None) -> None:
    app = DemandEvidenceLab(evidence_path)
    app.mainloop()


if __name__ == "__main__":
    launch_demand_evidence_lab()
