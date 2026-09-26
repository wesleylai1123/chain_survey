from __future__ import annotations

import json
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from core.abf_sensitivity_engine import SensitivityConfig, estimate_company_revenue_sensitivities
from core.indicator_taxonomy import indicator_table

HISTORY=ROOT/"data"/"history"/"free_industry_history_panel.csv"


class AbfResearchLab(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("ABF Research Lab — Timing, Driver, Sensitivity, Model")
        self.geometry("1600x980")
        self.minsize(1300,800)
        self.indicators=indicator_table()
        self.sensitivity=self._load_sensitivity()
        self._build()

    def _load_sensitivity(self) -> pd.DataFrame:
        if not HISTORY.exists():
            return pd.DataFrame()
        history=pd.read_csv(HISTORY)
        return estimate_company_revenue_sensitivities(history,config=SensitivityConfig(bootstrap_iterations=500))

    def _build(self) -> None:
        root=ttk.Frame(self,padding=14)
        root.pack(fill="both",expand=True)
        ttk.Label(root,text="ABF Research Model",font=("Segoe UI",18,"bold")).pack(anchor="w")
        ttk.Label(
            root,
            text=(
                "Indicator = what is observed and when. Driver = economic state. "
                "Sensitivity = how much a validated observable moves a downstream metric. "
                "Model = structural equations that connect demand → revenue → margin → EPS."
            ),
            wraplength=1500
        ).pack(anchor="w",pady=(4,10))

        book=ttk.Notebook(root)
        book.pack(fill="both",expand=True)

        timing=ttk.Frame(book,padding=10)
        sens=ttk.Frame(book,padding=10)
        flow=ttk.Frame(book,padding=10)
        book.add(timing,text="Indicator Timing")
        book.add(sens,text="Revenue Sensitivity")
        book.add(flow,text="Driver ↔ Sensitivity ↔ Model")

        cols=("indicator","class","relative_to","lag","status","role")
        tree=ttk.Treeview(timing,columns=cols,show="headings",height=20)
        widths={"indicator":220,"class":100,"relative_to":220,"lag":100,"status":150,"role":650}
        for c in cols:
            tree.heading(c,text=c.replace("_"," ").title())
            tree.column(c,width=widths[c],anchor="w" if c in {"indicator","relative_to","role"} else "center")
        tree.pack(fill="both",expand=True)
        for _,r in self.indicators.iterrows():
            lag="-" if pd.isna(r["lag_value"]) else f"{int(r['lag_value'])} {r['lag_unit']}"
            tree.insert("","end",values=(r["name"],r["timing_class"],r["relative_to"],lag,r["evidence_status"],r["role"]))

        ttk.Label(
            timing,
            text="Important: leading/coincident/lagging is target-relative. The same metric can lead one target and coincide with another.",
            font=("Segoe UI",10,"italic")
        ).pack(anchor="w",pady=(8,0))

        if self.sensitivity.empty:
            ttk.Label(
                sens,
                text="Historical panel not present locally. Restore data/history from evidence-data to calculate real sensitivity.",
                font=("Segoe UI",11)
            ).pack(anchor="w")
        else:
            scols=("company","beta","ci","r2","oos_r2","impact")
            st=ttk.Treeview(sens,columns=scols,show="headings",height=10)
            for c,w in [("company",120),("beta",90),("ci",180),("r2",90),("oos_r2",100),("impact",180)]:
                st.heading(c,text={"ci":"95% Beta CI","impact":"Impact / +10ppt PCB YoY"}.get(c,c.replace("_"," ").title()))
                st.column(c,width=w,anchor="center")
            st.pack(fill="x")
            for _,r in self.sensitivity.iterrows():
                st.insert("","end",values=(
                    r["company"],f"{r['beta']:+.3f}",
                    f"[{r['beta_ci_low']:+.3f}, {r['beta_ci_high']:+.3f}]",
                    f"{r['r2']:.3f}",f"{r['oos_r2']:.3f}",
                    f"{r['impact_per_10ppt_driver']:+.2f} ppt"
                ))
            ttk.Label(
                sens,
                text=(
                    "Interpretation: beta translates a validated leading indicator into revenue YoY sensitivity. "
                    "It does NOT mean the 0–100 driver score itself has this beta."
                ),
                wraplength=1450
            ).pack(anchor="w",pady=(10,0))

        text=tk.Text(flow,wrap="word",font=("Consolas",11))
        text.pack(fill="both",expand=True)
        text.insert("end",
"""1) INDICATOR — observable, dated evidence
   TPCA PCB Revenue YoY
   Timing: LEADING relative to ABF Revenue
   Validated lag: +1 month

                    │ observed point-in-time
                    ▼

2) DRIVER — economic state, not a financial beta
   end_demand = Compute / networking end-demand state
   Inputs can include orders, physical throughput, buyer commitment...
   Driver score answers: improving or deteriorating? how confident?

                    │ choose validated observable relation
                    ▼

3) SENSITIVITY — quantitative transmission
   Δ ABF Revenue YoY = α + β × TPCA PCB Revenue YoY(t-1) + ε

   beta answers:
   "If the validated leading indicator changes by +10ppt,
    historically how many ppt does ABF Revenue YoY change?"

                    │ revenue impact
                    ▼

4) INDUSTRY MODEL — structural routing
   ABF Demand = Chip Shipment × Area/Chip × Complexity
   Revenue = Volume × ASP
   GM = f(ASP, Utilization, Mix, Yield, Material Cost)

   The model decides WHERE a driver belongs.
   Sensitivity estimates HOW MUCH the downstream metric moves.

                    │
                    ▼

5) CONFIRMATION STACK
   LEADING:   TPCA PCB Revenue → future ABF revenue
   COINCIDENT: ABF company monthly revenue → current operating state
   LAGGING:   GM / Operating Margin / EPS → financial propagation confirmation

CURRENT CALIBRATION STATUS
   Driver → Revenue         CALIBRATED (v1)
   Revenue → Gross Margin   NOT YET CALIBRATED
   GM → Operating Margin    NOT YET CALIBRATED
   Operating → EPS          structural bridge exists; empirical calibration pending

RULE
   Never use lagging confirmation as if it were an early signal.
   Never use a driver score as if it were a revenue beta.
   Never add validated correlation as a second copy of the same evidence.
""")
        text.configure(state="disabled")


def launch_abf_research_lab() -> None:
    AbfResearchLab().mainloop()


if __name__=="__main__":
    launch_abf_research_lab()
