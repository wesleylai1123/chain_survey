from __future__ import annotations

import json
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

ARTIFACTS=ROOT/"artifacts"
EVIDENCE_CSV=ARTIFACTS/"free_evidence_latest.csv"
STATUS_JSON=ARTIFACTS/"free_evidence_collection_status.json"


class FreeEvidenceDashboard(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Live Free Evidence")
        self.geometry("1680x920")
        self.minsize(1250,720)
        self.evidence=pd.read_csv(EVIDENCE_CSV) if EVIDENCE_CSV.exists() else pd.DataFrame()
        self.status=json.loads(STATUS_JSON.read_text(encoding="utf-8")) if STATUS_JSON.exists() else {}
        self._build()

    def _build(self) -> None:
        root=ttk.Frame(self,padding=14)
        root.pack(fill="both",expand=True)
        ttk.Label(root,text="Live Free Evidence — forward-collected only",font=("Segoe UI",18,"bold")).pack(anchor="w")
        ttk.Label(
            root,
            text=(
                "Latest public snapshots from TWSE/TPEx, MOEA and TPCA. Fresh retrieval is always attempted first. "
                "A bounded STALE_FALLBACK may be used only when explicitly configured; it preserves the original PIT and shows stale age. "
                "Reliability values are source-class priors, "
                "not empirical probabilities; configured product exposure is not observed product mix."
            ),
            wraplength=1600,
        ).pack(anchor="w",pady=(4,10))

        cards=ttk.Frame(root); cards.pack(fill="x",pady=(0,10))
        values=[
            ("Fresh Sources",f"{self.status.get('sources_ok',0)} / {self.status.get('sources_total',0)}"),
            ("Stale Fallback",str(self.status.get("sources_stale",0))),
            ("Errors",str(self.status.get("sources_error",0))),
            ("Evidence rows",str(self.status.get("evidence_rows",len(self.evidence)))),
            ("Collected at",str(self.status.get("collected_at","-"))[:19]),
        ]
        for i,(label,value) in enumerate(values):
            box=ttk.LabelFrame(cards,text=label,padding=8); box.grid(row=0,column=i,sticky="nsew",padx=(0,8))
            cards.columnconfigure(i,weight=1)
            ttk.Label(box,text=value,font=("Segoe UI",12,"bold")).pack(anchor="w")

        notebook=ttk.Notebook(root); notebook.pack(fill="both",expand=True)
        source_tab=ttk.Frame(notebook,padding=8); evidence_tab=ttk.Frame(notebook,padding=8)
        notebook.add(source_tab,text="Connector health"); notebook.add(evidence_tab,text="Latest evidence")

        scols=("source_id","provider","status","rows","retrieval_status","stale_age_hours","last_verified_at","error")
        st=ttk.Treeview(source_tab,columns=scols,show="headings",height=12)
        sw={"source_id":250,"provider":90,"status":110,"rows":65,"retrieval_status":145,"stale_age_hours":110,"last_verified_at":180,"error":560}
        for col in scols:
            st.heading(col,text=col.replace("_"," ").title()); st.column(col,width=sw[col],anchor="w")
        st.pack(fill="x")
        for row in self.status.get("sources",[]):
            st.insert("","end",values=tuple(row.get(c,"") for c in scols))

        ecols=(
            "available","source_id","retrieval_status","stale_age_hours","last_verified_at",
            "chain","dimension","indicator","yoy","signal",
            "reliability","reliability_basis","exposure","exposure_basis","availability_policy","provenance","source"
        )
        tree=ttk.Treeview(evidence_tab,columns=ecols,show="headings",height=25)
        widths={
            "available":115,"source_id":190,"retrieval_status":145,"stale_age_hours":105,"last_verified_at":175,
            "chain":100,"dimension":160,"indicator":280,"yoy":75,"signal":70,
            "reliability":80,"reliability_basis":170,"exposure":80,"exposure_basis":190,
            "availability_policy":210,"provenance":190,"source":360
        }
        for col in ecols:
            tree.heading(col,text=col.replace("_"," ").title()); tree.column(col,width=widths[col],anchor="w")
        y=ttk.Scrollbar(evidence_tab,orient="vertical",command=tree.yview)
        x=ttk.Scrollbar(evidence_tab,orient="horizontal",command=tree.xview)
        tree.configure(yscrollcommand=y.set,xscrollcommand=x.set)
        tree.grid(row=0,column=0,sticky="nsew"); y.grid(row=0,column=1,sticky="ns"); x.grid(row=1,column=0,sticky="ew")
        evidence_tab.grid_rowconfigure(0,weight=1); evidence_tab.grid_columnconfigure(0,weight=1)

        if not self.evidence.empty:
            for _,row in self.evidence.sort_values("published_at",ascending=False).head(300).iterrows():
                def fmt(v,digits=2):
                    return "-" if pd.isna(v) else f"{float(v):+.{digits}f}"
                tree.insert("","end",values=(
                    str(row.get("published_at",""))[:19],row.get("source_id",""),
                    row.get("retrieval_status",""),fmt(row.get("stale_age_hours"),1),str(row.get("last_verified_at",""))[:19],
                    row.get("chain",""),row.get("dimension",""),row.get("indicator",""),fmt(row.get("yoy_pct"),1),fmt(row.get("signal")),
                    fmt(row.get("reliability"),2),row.get("reliability_basis",""),fmt(row.get("exposure_weight"),2),
                    row.get("exposure_basis",""),row.get("availability_policy",""),row.get("provenance",""),row.get("source",""),
                ))


def launch_free_evidence_dashboard() -> None:
    FreeEvidenceDashboard().mainloop()


if __name__=="__main__":
    launch_free_evidence_dashboard()
