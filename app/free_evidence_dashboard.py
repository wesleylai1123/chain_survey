from __future__ import annotations

import json
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

ARTIFACTS = ROOT / "artifacts"
EVIDENCE_CSV = ARTIFACTS / "free_evidence_latest.csv"
STATUS_JSON = ARTIFACTS / "free_evidence_collection_status.json"


class FreeEvidenceDashboard(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Free Evidence Connectors")
        self.geometry("1500x900")
        self.minsize(1200, 720)
        self.evidence = pd.read_csv(EVIDENCE_CSV) if EVIDENCE_CSV.exists() else pd.DataFrame()
        self.status = json.loads(STATUS_JSON.read_text(encoding="utf-8")) if STATUS_JSON.exists() else {}
        self._build()

    def _build(self) -> None:
        root = ttk.Frame(self, padding=14)
        root.pack(fill="both", expand=True)
        ttk.Label(root, text="Free Evidence Connectors v1", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(
            root,
            text=(
                "Forward-collected public evidence from TWSE/TPEx, MOEA and TPCA. "
                "If an upstream source does not expose an exact publication timestamp, availability is conservatively "
                "anchored to collection time so historical research cannot look ahead."
            ),
            wraplength=1450,
        ).pack(anchor="w", pady=(4, 10))

        cards = ttk.Frame(root)
        cards.pack(fill="x", pady=(0, 10))
        values = [
            ("Sources OK", f"{self.status.get('sources_ok', 0)} / {self.status.get('sources_total', 0)}"),
            ("Source errors", str(self.status.get("sources_error", 0))),
            ("Evidence rows", str(self.status.get("evidence_rows", len(self.evidence)))),
            ("Collected at", str(self.status.get("collected_at", "-"))[:19]),
        ]
        for i, (label, value) in enumerate(values):
            box = ttk.LabelFrame(cards, text=label, padding=8)
            box.grid(row=0, column=i, sticky="nsew", padx=(0, 8 if i < len(values)-1 else 0))
            cards.columnconfigure(i, weight=1)
            ttk.Label(box, text=value, font=("Segoe UI", 12, "bold")).pack(anchor="w")

        notebook = ttk.Notebook(root)
        notebook.pack(fill="both", expand=True)
        source_tab = ttk.Frame(notebook, padding=8)
        evidence_tab = ttk.Frame(notebook, padding=8)
        notebook.add(source_tab, text="Connector health")
        notebook.add(evidence_tab, text="Latest evidence")

        scols=("source_id","status","rows","error")
        source_tree=ttk.Treeview(source_tab,columns=scols,show="headings",height=12)
        for c,w in [("source_id",270),("status",90),("rows",80),("error",700)]:
            source_tree.heading(c,text=c.replace("_"," ").title())
            source_tree.column(c,width=w,anchor="w" if c in {"source_id","error"} else "center")
        source_tree.pack(fill="x")
        for row in self.status.get("sources", []):
            source_tree.insert("","end",values=(
                row.get("source_id",""),row.get("status",""),row.get("rows",0),row.get("error","")
            ))

        ecols=("published","source_id","chain","dimension","indicator","yoy","signal","company")
        evidence_tree=ttk.Treeview(evidence_tab,columns=ecols,show="headings",height=24)
        widths={"published":110,"source_id":210,"chain":100,"dimension":150,"indicator":280,"yoy":80,"signal":80,"company":110}
        for c in ecols:
            evidence_tree.heading(c,text=c.replace("_"," ").title())
            evidence_tree.column(c,width=widths[c],anchor="w" if c in {"source_id","dimension","indicator","company"} else "center")
        evidence_tree.pack(fill="both",expand=True)
        if not self.evidence.empty:
            for _,row in self.evidence.sort_values("published_at",ascending=False).head(200).iterrows():
                evidence_tree.insert("","end",values=(
                    str(row.get("published_at",""))[:10],
                    row.get("source_id",""),
                    row.get("chain",""),
                    row.get("dimension",""),
                    row.get("indicator",""),
                    f"{float(row['yoy_pct']):+.1f}%" if pd.notna(row.get("yoy_pct")) else "-",
                    f"{float(row['signal']):+.2f}" if pd.notna(row.get("signal")) else "-",
                    row.get("company",""),
                ))


def launch_free_evidence_dashboard() -> None:
    FreeEvidenceDashboard().mainloop()


if __name__ == "__main__":
    launch_free_evidence_dashboard()
