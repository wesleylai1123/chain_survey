from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
PANEL=ROOT/"data"/"history"/"free_industry_history_panel.csv"
OUT=ROOT/"artifacts"/"free-industry-history-coverage.png"


def main() -> None:
    frame=pd.read_csv(PANEL)
    frame["period_date"]=pd.to_datetime(frame["period_date"],utc=True)
    counts=(
        frame.assign(month=frame["period_date"].dt.to_period("M").astype(str))
        .groupby(["month","source_id"])
        .size()
        .unstack(fill_value=0)
        .sort_index()
    )
    OUT.parent.mkdir(parents=True,exist_ok=True)
    fig,ax=plt.subplots(figsize=(14,7))
    counts.plot(ax=ax,marker="o")
    ax.set_title("Free industry evidence history coverage")
    ax.set_xlabel("Month")
    ax.set_ylabel("Observations")
    ax.tick_params(axis="x",rotation=60)
    fig.tight_layout()
    fig.savefig(OUT,dpi=160)
    plt.close(fig)
    print(f"FREE_HISTORY_COVERAGE_PLOT_OK {OUT}")


if __name__=="__main__":
    main()
