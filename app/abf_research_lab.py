from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from core.abf_sensitivity_engine import SensitivityConfig, estimate_company_revenue_sensitivities
from core.indicator_taxonomy import indicator_table
from core.directional_indicator_engine import scenario_transmission

HISTORY = ROOT / "data" / "history" / "free_industry_history_panel.csv"

BG = "#F3F6FA"
CARD = "#FFFFFF"
TEXT = "#172033"
MUTED = "#667085"
BORDER = "#D8E0EA"
NAVY = "#0F172A"
BLUE = "#2563EB"
BLUE_SOFT = "#EAF2FF"
TEAL = "#0F766E"
TEAL_SOFT = "#E8F7F3"
AMBER = "#B45309"
AMBER_SOFT = "#FFF4E5"
GREEN = "#15803D"
GREEN_SOFT = "#ECFDF3"
RED = "#B42318"
RED_SOFT = "#FEF3F2"
SLATE_SOFT = "#EEF2F6"


class AbfResearchLab(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("ABF Research Lab")
        self.geometry("1600x980")
        self.minsize(1320, 820)
        self.configure(bg=BG)
        self.indicators = indicator_table()
        self.sensitivity = self._load_sensitivity()
        self._configure_style()
        self._build()

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Research.TNotebook", background=BG, borderwidth=0)
        style.configure(
            "Research.TNotebook.Tab",
            background="#E8EDF4",
            foreground=MUTED,
            padding=(20, 10),
            font=("Segoe UI", 10, "bold"),
            borderwidth=0,
        )
        style.map(
            "Research.TNotebook.Tab",
            background=[("selected", CARD)],
            foreground=[("selected", TEXT)],
        )

    def _load_sensitivity(self) -> pd.DataFrame:
        if not HISTORY.exists():
            return pd.DataFrame()
        history = pd.read_csv(HISTORY)
        return estimate_company_revenue_sensitivities(
            history,
            config=SensitivityConfig(bootstrap_iterations=500),
        )

    def _card(self, parent, *, bg: str = CARD, padx: int = 16, pady: int = 14) -> tk.Frame:
        outer = tk.Frame(parent, bg=BORDER, bd=0, highlightthickness=0)
        inner = tk.Frame(outer, bg=bg, bd=0)
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        inner.configure(padx=padx, pady=pady)
        return outer

    def _inner(self, card: tk.Frame) -> tk.Frame:
        return card.winfo_children()[0]

    def _pill(self, parent, text: str, fg: str, bg: str) -> tk.Label:
        return tk.Label(
            parent,
            text=text,
            fg=fg,
            bg=bg,
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=4,
        )

    def _metric_card(self, parent, title: str, value: str, note: str, accent: str, soft: str) -> tk.Frame:
        card = self._card(parent)
        body = self._inner(card)
        tk.Frame(body, bg=accent, height=4).pack(fill="x", pady=(0, 12))
        tk.Label(body, text=title, bg=CARD, fg=MUTED, font=("Segoe UI", 9, "bold")).pack(anchor="w")
        tk.Label(body, text=value, bg=CARD, fg=TEXT, font=("Segoe UI", 17, "bold")).pack(anchor="w", pady=(4, 3))
        tk.Label(body, text=note, bg=CARD, fg=MUTED, font=("Segoe UI", 9), wraplength=300, justify="left").pack(anchor="w")
        return card

    def _build(self) -> None:
        shell = tk.Frame(self, bg=BG)
        shell.pack(fill="both", expand=True)

        self._build_header(shell)
        self._build_overview(shell)

        content = tk.Frame(shell, bg=BG)
        content.pack(fill="both", expand=True, padx=24, pady=(0, 20))

        self.book = ttk.Notebook(content, style="Research.TNotebook")
        self.book.pack(fill="both", expand=True)

        timing = tk.Frame(self.book, bg=BG)
        sensitivity = tk.Frame(self.book, bg=BG)
        flow = tk.Frame(self.book, bg=BG)
        self.book.add(timing, text="Indicator Timing")
        self.book.add(sensitivity, text="Revenue Sensitivity")
        self.book.add(flow, text="Driver → Sensitivity → Model")

        self._build_timing_tab(timing)
        self._build_sensitivity_tab(sensitivity)
        self._build_flow_tab(flow)

    def _build_header(self, parent) -> None:
        header = tk.Frame(parent, bg=NAVY, padx=24, pady=18)
        header.pack(fill="x")
        left = tk.Frame(header, bg=NAVY)
        left.pack(side="left", fill="x", expand=True)
        tk.Label(
            left,
            text="ABF Fundamental Research",
            bg=NAVY,
            fg="#FFFFFF",
            font=("Segoe UI", 20, "bold"),
        ).pack(anchor="w")
        tk.Label(
            left,
            text="Point-in-time evidence → validated leading driver → operating sensitivity → financial confirmation",
            bg=NAVY,
            fg="#CBD5E1",
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(4, 0))

        right = tk.Frame(header, bg=NAVY)
        right.pack(side="right")
        self._pill(right, "ABF REFERENCE MODEL", "#DBEAFE", "#1E3A8A").pack(anchor="e")

    def _build_overview(self, parent) -> None:
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", padx=24, pady=16)
        for i in range(4):
            row.grid_columnconfigure(i, weight=1, uniform="overview")

        basket = None
        if not self.sensitivity.empty:
            basket_rows = self.sensitivity[self.sensitivity["ticker"] == "ABF"]
            if not basket_rows.empty:
                basket = basket_rows.iloc[0]

        sample_note = "Real point-in-time history"
        sample_value = "—"
        if basket is not None:
            sample_value = str(int(basket["sample_size"]))
            sample_note = "Matched monthly observations"

        magnitude = "Candidate"
        magnitude_note = "Direction valid; exact beta not stable OOS"
        if basket is not None and bool(basket.get("magnitude_validation_pass", False)):
            magnitude = "Validated"
            magnitude_note = "Direction and magnitude pass OOS checks"

        cards = [
            ("Leading relation", "PCB YoY ↕ ABF", "+1 month · direction validated both ways", BLUE, BLUE_SOFT),
            ("Revenue magnitude", magnitude, magnitude_note, AMBER, AMBER_SOFT),
            ("Financial chain", "Revenue → GM → EPS", "GM = gross margin; downstream calibration pending", TEAL, TEAL_SOFT),
            ("Research sample", sample_value, sample_note, GREEN, GREEN_SOFT),
        ]
        for i, args in enumerate(cards):
            card = self._metric_card(row, *args)
            card.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 6, 0 if i == 3 else 6))

    def _timing_bucket(self, parent, title: str, subtitle: str, rows: pd.DataFrame, accent: str, soft: str) -> tk.Frame:
        card = self._card(parent)
        body = self._inner(card)
        head = tk.Frame(body, bg=CARD)
        head.pack(fill="x")
        self._pill(head, title, accent, soft).pack(side="left")
        tk.Label(head, text=subtitle, bg=CARD, fg=MUTED, font=("Segoe UI", 9)).pack(side="left", padx=(10, 0))

        tk.Frame(body, bg=BORDER, height=1).pack(fill="x", pady=12)

        for idx, (_, row) in enumerate(rows.iterrows()):
            item = tk.Frame(body, bg=CARD)
            item.pack(fill="x", pady=(0, 12))
            tk.Label(item, text=row["name"], bg=CARD, fg=TEXT, font=("Segoe UI", 11, "bold")).pack(anchor="w")
            relative = str(row["relative_to"]).replace("_", " ")
            lag = "lag not calibrated" if pd.isna(row["lag_value"]) else f"lag {int(row['lag_value'])} {row['lag_unit']}"
            tk.Label(
                item,
                text=f"vs {relative}  ·  {lag}",
                bg=CARD,
                fg=MUTED,
                font=("Segoe UI", 9),
            ).pack(anchor="w", pady=(2, 3))
            status_fg, status_bg = (GREEN, GREEN_SOFT) if row["evidence_status"] == "VALIDATED" else (MUTED, SLATE_SOFT)
            self._pill(item, str(row["evidence_status"]), status_fg, status_bg).pack(anchor="w")

            cases = tk.Frame(item, bg=CARD)
            cases.pack(fill="x", pady=(7, 0))
            pos = tk.Frame(cases, bg=GREEN_SOFT, padx=8, pady=6)
            pos.pack(fill="x", pady=(0, 4))
            tk.Label(pos, text="▲ Beneficial", bg=GREEN_SOFT, fg=GREEN, font=("Segoe UI", 8, "bold")).pack(anchor="w")
            tk.Label(pos, text=str(row.get("positive_case","")), bg=GREEN_SOFT, fg=TEXT, font=("Segoe UI", 8), wraplength=360, justify="left").pack(anchor="w")
            neg = tk.Frame(cases, bg=RED_SOFT, padx=8, pady=6)
            neg.pack(fill="x")
            tk.Label(neg, text="▼ Adverse", bg=RED_SOFT, fg=RED, font=("Segoe UI", 8, "bold")).pack(anchor="w")
            tk.Label(neg, text=str(row.get("negative_case","")), bg=RED_SOFT, fg=TEXT, font=("Segoe UI", 8), wraplength=360, justify="left").pack(anchor="w")

            if idx != len(rows) - 1:
                tk.Frame(body, bg="#EEF2F6", height=1).pack(fill="x", pady=(0, 12))
        return card

    def _build_timing_tab(self, parent) -> None:
        intro = tk.Frame(parent, bg=BG)
        intro.pack(fill="x", padx=18, pady=(18, 12))
        tk.Label(intro, text="When does each signal become useful?", bg=BG, fg=TEXT, font=("Segoe UI", 16, "bold")).pack(anchor="w")
        tk.Label(
            intro,
            text="Timing is target-relative: the same metric can be coincident for today's revenue state and leading for a future margin target.",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(4, 0))

        grid = tk.Frame(parent, bg=BG)
        grid.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        for i in range(3):
            grid.grid_columnconfigure(i, weight=1, uniform="timing")
        grid.grid_rowconfigure(0, weight=1)

        specs = [
            ("LEADING", "Early warning", BLUE, BLUE_SOFT),
            ("COINCIDENT", "Current-state confirmation", TEAL, TEAL_SOFT),
            ("LAGGING", "Financial confirmation", AMBER, AMBER_SOFT),
        ]
        for i, (klass, subtitle, accent, soft) in enumerate(specs):
            rows = self.indicators[self.indicators["timing_class"] == klass].reset_index(drop=True)
            card = self._timing_bucket(grid, klass, subtitle, rows, accent, soft)
            card.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 7, 0 if i == 2 else 7))

    def _company_sensitivity_card(self, parent, row: pd.Series) -> tk.Frame:
        status = str(row["sensitivity_status"])
        validated = status == "MAGNITUDE_VALIDATED"
        accent = GREEN if validated else AMBER
        soft = GREEN_SOFT if validated else AMBER_SOFT

        card = self._card(parent)
        body = self._inner(card)
        top = tk.Frame(body, bg=CARD)
        top.pack(fill="x")
        tk.Label(top, text=str(row["company"]), bg=CARD, fg=TEXT, font=("Segoe UI", 13, "bold")).pack(side="left")
        self._pill(top, "MAGNITUDE VALIDATED" if validated else "MAGNITUDE CANDIDATE", accent, soft).pack(side="right")

        tk.Label(
            body,
            text=f"β  {float(row['beta']):+.2f}",
            bg=CARD,
            fg=TEXT,
            font=("Segoe UI", 22, "bold"),
        ).pack(anchor="w", pady=(14, 2))
        upside = scenario_transmission(float(row["beta"]), 10.0)
        downside = scenario_transmission(float(row["beta"]), -10.0)
        tk.Label(
            body,
            text=f"+10ppt PCB YoY → fitted revenue effect {upside:+.1f}ppt",
            bg=CARD,
            fg=GREEN,
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w")
        tk.Label(
            body,
            text=f"-10ppt PCB YoY → fitted revenue effect {downside:+.1f}ppt",
            bg=CARD,
            fg=RED,
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w", pady=(2,0))

        stats = tk.Frame(body, bg=CARD)
        stats.pack(fill="x", pady=(14, 0))
        values = [
            ("95% CI", f"{float(row['beta_ci_low']):+.2f} ~ {float(row['beta_ci_high']):+.2f}"),
            ("In-sample R²", f"{float(row['r2']):.2f}"),
            ("OOS R²", f"{float(row['oos_r2']):.2f}"),
        ]
        for i, (label, value) in enumerate(values):
            box = tk.Frame(stats, bg=SLATE_SOFT, padx=10, pady=8)
            box.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 4, 0 if i == len(values)-1 else 4))
            stats.grid_columnconfigure(i, weight=1)
            tk.Label(box, text=label, bg=SLATE_SOFT, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(anchor="w")
            fg = RED if label == "OOS R²" and float(row["oos_r2"]) < 0 else TEXT
            tk.Label(box, text=value, bg=SLATE_SOFT, fg=fg, font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(2, 0))
        return card

    def _build_sensitivity_tab(self, parent) -> None:
        intro = tk.Frame(parent, bg=BG)
        intro.pack(fill="x", padx=18, pady=(18, 12))
        tk.Label(intro, text="How much does the validated leading signal move revenue?", bg=BG, fg=TEXT, font=("Segoe UI", 16, "bold")).pack(anchor="w")
        tk.Label(
            intro,
            text="Direction and magnitude are separate claims. A positive relationship can be directionally valid while its exact beta remains unstable out-of-sample.",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(4, 0))

        if self.sensitivity.empty:
            empty = self._card(parent)
            empty.pack(fill="x", padx=18)
            tk.Label(
                self._inner(empty),
                text="Historical panel not available. Restore evidence-data history to calculate real sensitivity.",
                bg=CARD, fg=MUTED, font=("Segoe UI", 11)
            ).pack(anchor="w")
            return

        grid = tk.Frame(parent, bg=BG)
        grid.pack(fill="x", padx=18)
        for i in range(2):
            grid.grid_columnconfigure(i, weight=1, uniform="sens")
        for idx, (_, row) in enumerate(self.sensitivity.iterrows()):
            card = self._company_sensitivity_card(grid, row)
            card.grid(row=idx // 2, column=idx % 2, sticky="nsew", padx=(0 if idx % 2 == 0 else 7, 7 if idx % 2 == 0 else 0), pady=7)

        note = self._card(parent, bg=RED_SOFT)
        note.pack(fill="x", padx=18, pady=(12, 18))
        body = self._inner(note)
        tk.Label(body, text="How to read OOS R²", bg=RED_SOFT, fg=RED, font=("Segoe UI", 11, "bold")).pack(anchor="w")
        tk.Label(
            body,
            text=(
                "OOS = Out-of-Sample: data the beta was not fitted on. "
                "If OOS R² is below 0, the fixed beta predicts unseen data worse than simply using the test-period average. "
                "That is why the current ABF beta is still a magnitude candidate even though the leading direction is validated."
            ),
            bg=RED_SOFT, fg=TEXT, font=("Segoe UI", 10), wraplength=1450, justify="left"
        ).pack(anchor="w", pady=(5, 0))

    def _flow_card(self, parent, step: str, title: str, detail: str, status: str, accent: str, soft: str) -> tk.Frame:
        card = self._card(parent)
        body = self._inner(card)
        top = tk.Frame(body, bg=CARD)
        top.pack(fill="x")
        tk.Label(top, text=step, bg=CARD, fg=accent, font=("Segoe UI", 9, "bold")).pack(side="left")
        self._pill(top, status, accent, soft).pack(side="right")
        tk.Label(body, text=title, bg=CARD, fg=TEXT, font=("Segoe UI", 13, "bold")).pack(anchor="w", pady=(12, 6))
        tk.Label(body, text=detail, bg=CARD, fg=MUTED, font=("Segoe UI", 9), wraplength=280, justify="left").pack(anchor="w")
        return card

    def _build_flow_tab(self, parent) -> None:
        intro = tk.Frame(parent, bg=BG)
        intro.pack(fill="x", padx=18, pady=(18, 12))
        tk.Label(intro, text="What each layer is responsible for", bg=BG, fg=TEXT, font=("Segoe UI", 16, "bold")).pack(anchor="w")
        tk.Label(
            intro,
            text="Indicator observes. Driver summarizes economic state. Sensitivity estimates transmission magnitude. The industry model decides where that transmission belongs.",
            bg=BG, fg=MUTED, font=("Segoe UI", 10)
        ).pack(anchor="w", pady=(4, 0))

        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", padx=18)
        for i in range(7):
            row.grid_columnconfigure(i, weight=1 if i % 2 == 0 else 0)

        blocks = [
            ("01 · INDICATOR", "TPCA PCB Revenue YoY", "Observed, dated point-in-time metric. Leading +1M vs ABF revenue.", "VALIDATED", BLUE, BLUE_SOFT),
            ("02 · DRIVER", "ABF End Demand", "Economic state: improving or deteriorating? Confidence comes from evidence breadth and quality.", "STATE", TEAL, TEAL_SOFT),
            ("03 · SENSITIVITY", "Revenue β", "How much does a validated observable move future revenue? Direction is valid; magnitude is still candidate.", "CANDIDATE", AMBER, AMBER_SOFT),
            ("04 · MODEL", "Revenue → GM → EPS", "Structural routing: Revenue = Volume × ASP; GM depends on utilization, pricing, mix, yield and cost.", "STRUCTURAL", NAVY, SLATE_SOFT),
        ]
        for i, block in enumerate(blocks):
            card = self._flow_card(row, *block)
            col = i * 2
            card.grid(row=0, column=col, sticky="nsew")
            if i < len(blocks) - 1:
                tk.Label(row, text="→", bg=BG, fg="#98A2B3", font=("Segoe UI", 18, "bold")).grid(row=0, column=col + 1, padx=8)

        status = self._card(parent)
        status.pack(fill="both", expand=True, padx=18, pady=(16, 18))
        body = self._inner(status)
        tk.Label(body, text="ABF calibration ladder", bg=CARD, fg=TEXT, font=("Segoe UI", 13, "bold")).pack(anchor="w")
        tk.Label(body, text="What is proven today vs what remains research work", bg=CARD, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(3, 12))

        ladder = [
            ("Leading direction", "TPCA PCB Revenue → future ABF Revenue", "VALIDATED", GREEN, GREEN_SOFT),
            ("Revenue magnitude", "Exact beta / impact size", "CANDIDATE", AMBER, AMBER_SOFT),
            ("Revenue → GM", "Does monthly revenue lead gross-margin expansion?", "NOT CALIBRATED", MUTED, SLATE_SOFT),
            ("GM → EPS", "How margin improvement propagates to earnings", "NOT CALIBRATED", MUTED, SLATE_SOFT),
        ]
        for idx, (name, desc, state, accent, soft) in enumerate(ladder):
            line = tk.Frame(body, bg=CARD)
            line.pack(fill="x", pady=6)
            tk.Label(line, text=f"{idx+1:02d}", bg=CARD, fg="#98A2B3", font=("Segoe UI", 10, "bold"), width=4).pack(side="left")
            text = tk.Frame(line, bg=CARD)
            text.pack(side="left", fill="x", expand=True)
            tk.Label(text, text=name, bg=CARD, fg=TEXT, font=("Segoe UI", 10, "bold")).pack(anchor="w")
            tk.Label(text, text=desc, bg=CARD, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w")
            self._pill(line, state, accent, soft).pack(side="right")


def launch_abf_research_lab() -> None:
    AbfResearchLab().mainloop()


if __name__ == "__main__":
    launch_abf_research_lab()
