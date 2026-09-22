from __future__ import annotations

from pathlib import Path
import matplotlib.pyplot as plt
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
INPUT=ROOT/"artifacts"/"operating_correlation_results.csv"


def main() -> None:
    df=pd.read_csv(INPUT)
    basket=df[df["target"]=="abf_revenue_yoy_basket"].copy()
    if basket.empty:
        basket=df.copy()

    best=(
        basket.sort_values(["score","sample_size"],ascending=False)
        .groupby("feature",as_index=False)
        .first()
        .sort_values("spearman")
    )
    fig,ax=plt.subplots(figsize=(12,6))
    labels=[f"{f}\nlag {int(l)}M" for f,l in zip(best["feature"],best["lag_months"])]
    ax.barh(labels,best["spearman"])
    ax.axvline(0,linewidth=1)
    ax.set_title("Best point-in-time lead/lag correlation vs ABF revenue basket")
    ax.set_xlabel("Spearman correlation")
    fig.tight_layout()
    out=ROOT/"artifacts"/"operating-correlation-best-lags.png"
    fig.savefig(out,dpi=160)
    plt.close(fig)

    pivot=basket.pivot_table(index="feature",columns="lag_months",values="spearman",aggfunc="first")
    fig,ax=plt.subplots(figsize=(12,6))
    im=ax.imshow(pivot.values,aspect="auto")
    ax.set_xticks(range(len(pivot.columns)),[f"{int(x)}M" for x in pivot.columns])
    ax.set_yticks(range(len(pivot.index)),pivot.index)
    ax.set_title("Spearman correlation by lead lag")
    ax.set_xlabel("Feature lead")
    for i in range(pivot.shape[0]):
        for j in range(pivot.shape[1]):
            value=pivot.iloc[i,j]
            if pd.notna(value):
                ax.text(j,i,f"{value:.2f}",ha="center",va="center",fontsize=8)
    fig.colorbar(im,ax=ax,label="Spearman")
    fig.tight_layout()
    out2=ROOT/"artifacts"/"operating-correlation-heatmap.png"
    fig.savefig(out2,dpi=160)
    plt.close(fig)
    print("OPERATING_CORRELATION_CHARTS_OK",out,out2)


if __name__=="__main__":
    main()
