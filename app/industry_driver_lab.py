from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from core.industry_driver_engine import (
    evaluate_all_industry_models,
    evaluate_industry_model,
    map_models_to_companies,
)
from scripts.build_real_point_in_time_evidence import DEFAULT_RAW, build_real_evidence

EVIDENCE_PATH = DEFAULT_RAW
REL_PATH = ROOT / "data" / "company_product_relationships.csv"


class IndustryDriverLab(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Industry Driver Model Lab — Real Point-in-Time Evidence")
        self.geometry("1580x980")
        self.minsize(1280, 780)
        self.evidence = build_real_evidence(pd.read_csv(EVIDENCE_PATH))
        self.relations = pd.read_csv(REL_PATH)
        self.models = evaluate_all_industry_models(self.evidence)
        self.selected_model = tk.StringVar(value=str(self.models.iloc[0]["model_id"]))
        self.status_var = tk.StringVar(value="")
        self._build_ui()
        self.refresh_detail()

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=14)
        root.pack(fill="both", expand=True)
        ttk.Label(root, text="Industry Driver Model v1 — REAL Point-in-Time", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(
            root,
            text=(
                "Official/company observations only. Each evidence row keeps its reporting period, actual publication "
                "timestamp, raw value, source URL and transform. Scores never use an observation before published_at."
            ),
            wraplength=1500,
        ).pack(anchor="w", pady=(4, 10))

        top = ttk.Panedwindow(root, orient="horizontal")
        top.pack(fill="both", expand=True)

        left = ttk.Frame(top, padding=6)
        right = ttk.Frame(top, padding=6)
        top.add(left, weight=3)
        top.add(right, weight=2)

        cols = ("model","score","state","confidence","coverage","volume","asp","margin")
        self.model_tree = ttk.Treeview(left, columns=cols, show="headings", height=16)
        labels = {
            "model":"Industry model","score":"Score","state":"State","confidence":"Confidence",
            "coverage":"Coverage","volume":"Volume","asp":"ASP","margin":"Margin"
        }
        widths = {"model":250,"score":70,"state":120,"confidence":90,"coverage":85,"volume":80,"asp":80,"margin":80}
        for c in cols:
            self.model_tree.heading(c, text=labels[c])
            self.model_tree.column(c, width=widths[c], anchor="w" if c in {"model","state"} else "center")
        self.model_tree.pack(fill="x")
        for _, row in self.models.iterrows():
            iid = str(row["model_id"])
            self.model_tree.insert("", "end", iid=iid, values=(
                row["model_name"], f"{row['score']:.1f}", row["state"], f"{row['confidence']:.0f}%",
                f"{row['coverage']:.0f}%", f"{row['volume_score']:.1f}", f"{row['asp_score']:.1f}", f"{row['margin_score']:.1f}"
            ))
        self.model_tree.bind("<<TreeviewSelect>>", self._on_select)
        self.model_tree.selection_set(self.selected_model.get())

        ttk.Label(left, text="Driver decomposition", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(12,4))
        dcols=("driver","score","confidence","groups","weight")
        self.driver_tree=ttk.Treeview(left,columns=dcols,show="headings",height=12)
        for c,w in [("driver",260),("score",80),("confidence",100),("groups",90),("weight",80)]:
            self.driver_tree.heading(c,text=c.replace("_"," ").title())
            self.driver_tree.column(c,width=w,anchor="w" if c=="driver" else "center")
        self.driver_tree.pack(fill="both",expand=True)

        ttk.Label(right, text="Real evidence provenance", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        ecols=("published","chain","indicator","yoy","source_type")
        self.evidence_tree=ttk.Treeview(right,columns=ecols,show="headings",height=7)
        for col,w in [("published",110),("chain",90),("indicator",240),("yoy",80),("source_type",150)]:
            self.evidence_tree.heading(col,text=col.replace("_"," ").title())
            self.evidence_tree.column(col,width=w,anchor="w" if col in {"indicator","source_type"} else "center")
        self.evidence_tree.pack(fill="x",pady=(4,10))
        for _,erow in self.evidence.sort_values("published_at",ascending=False).iterrows():
            self.evidence_tree.insert("","end",values=(
                pd.Timestamp(erow["published_at"]).strftime("%Y-%m-%d"),
                erow["chain"],
                erow["indicator"],
                f"{float(erow['yoy_pct']):+.1f}%",
                erow["source_type"],
            ))

        ttk.Label(right, text="Equations", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        self.equation_text=tk.Text(right,height=10,wrap="word")
        self.equation_text.pack(fill="x",pady=(4,10))

        ttk.Label(right, text="Company exposure", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        ccols=("company","product","score","exposure","adjusted","state")
        self.company_tree=ttk.Treeview(right,columns=ccols,show="headings",height=10)
        for c,w in [("company",110),("product",130),("score",70),("exposure",80),("adjusted",90),("state",120)]:
            self.company_tree.heading(c,text=c.replace("_"," ").title())
            self.company_tree.column(c,width=w,anchor="center")
        self.company_tree.pack(fill="both",expand=True)

        ttk.Label(root,textvariable=self.status_var).pack(anchor="w",pady=(8,0))

    def _on_select(self, _event=None) -> None:
        sel=self.model_tree.selection()
        if sel:
            self.selected_model.set(sel[0])
            self.refresh_detail()

    def refresh_detail(self) -> None:
        result=evaluate_industry_model(self.evidence,self.selected_model.get())
        self.driver_tree.delete(*self.driver_tree.get_children())
        for _,row in result["drivers"].iterrows():
            self.driver_tree.insert("","end",values=(
                row["driver_name"],f"{row['score']:.1f}",f"{row['confidence']:.0f}%",
                int(row["evidence_groups"]),f"{row['weight']:.2f}"
            ))

        self.equation_text.delete("1.0","end")
        for key,value in result["equations"].items():
            self.equation_text.insert("end",f"{key.replace('_',' ').title()}\n{value}\n\n")

        mapped=map_models_to_companies(self.models,self.relations)
        mapped=mapped[mapped["model_id"]==self.selected_model.get()]
        self.company_tree.delete(*self.company_tree.get_children())
        for _,row in mapped.iterrows():
            self.company_tree.insert("","end",values=(
                row["company"],row["product"],f"{row['industry_score']:.1f}",f"{row['exposure_weight']:.2f}",
                f"{row['exposure_adjusted_signal']:+.1f}",row["state"]
            ))
        self.status_var.set(
            f"{result['model_name']}: {result['state']} | score {result['score']:.1f} | "
            f"confidence {result['confidence']:.0f}% | evidence coverage {result['coverage']:.0f}% | "
            f"REAL point-in-time observations {len(self.evidence)}"
        )


def launch_industry_driver_lab() -> None:
    IndustryDriverLab().mainloop()


if __name__ == "__main__":
    launch_industry_driver_lab()
