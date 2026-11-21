from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from core.driver_validation_engine import benjamini_hochberg

ABF_STOCK_IDS=("3037","3189","8046")


@dataclass(frozen=True)
class MarginScanConfig:
    min_samples: int=18
    min_abs_spearman: float=0.25
    min_abs_oos: float=0.15
    min_cross_company_share: float=2/3
    train_fraction: float=0.70
    permutation_iterations: int=500
    block_size: int=2
    random_seed: int=20260926


def _corr(frame: pd.DataFrame) -> float:
    work=frame[["x","y"]].dropna()
    if len(work)<3 or work["x"].nunique()<2 or work["y"].nunique()<2:
        return float("nan")
    return float(work["x"].corr(work["y"],method="spearman"))


def _align_company(group: pd.DataFrame, feature: str, target: str, lag_quarters: int) -> pd.DataFrame:
    g=group.sort_values("report_date").copy()
    g["report_date"]=pd.to_datetime(g["report_date"],errors="coerce")
    g["available_date"]=pd.to_datetime(g["available_date"],errors="coerce")
    rows=[]
    g=g.dropna(subset=['report_date','available_date'])
    if g['report_date'].duplicated().any():
        raise ValueError('Conflicting quarterly vintages must be resolved before calibration')
    by_quarter={pd.Period(r['report_date'],freq='Q'):r for r in g.to_dict('records')}
    for f in g.to_dict('records'):
        t=by_quarter.get(pd.Period(f['report_date'],freq='Q')+lag_quarters)
        if t is None:
            continue
        x=pd.to_numeric(f.get(feature),errors="coerce")
        y=pd.to_numeric(t.get(target),errors="coerce")
        if pd.isna(x) or pd.isna(y):
            continue
        feature_available=f['available_date']
        if feature=='monthly_revenue_3m_yoy' and pd.notna(f.get('monthly_revenue_available_date')):
            feature_available=max(feature_available,pd.Timestamp(f['monthly_revenue_available_date']))
        if feature_available>t["available_date"]:
            continue
        rows.append({
            "ticker":str(f["ticker"]),
            "feature_report_date":f["report_date"],
            "target_report_date":t["report_date"],
            "feature_available_date":feature_available,
            "target_available_date":t["available_date"],
            "x":float(x),
            "y":float(y),
            'accounting_basis':'STANDALONE_QUARTER' if f.get('accounting_basis')==t.get('accounting_basis')=='STANDALONE_QUARTER' else 'UNKNOWN',
        })
    return pd.DataFrame(rows)


def _block_permutation_pvalue(aligned: pd.DataFrame, observed: float, *, iterations: int, block_size: int, seed: int) -> float:
    if aligned.empty or pd.isna(observed):
        return float("nan")
    rng=np.random.default_rng(seed)
    null=[]
    for _ in range(iterations):
        parts=[]
        for _,g in aligned.groupby("ticker",sort=False):
            g=g.sort_values("target_report_date").copy()
            n=len(g)
            if n<3:
                parts.append(g)
                continue
            blocks=[g.iloc[i:i+block_size].copy() for i in range(0,n,block_size)]
            order=rng.permutation(len(blocks))
            shuffled=pd.concat([blocks[i] for i in order],ignore_index=True)
            out=g.reset_index(drop=True).copy()
            out["y"]=shuffled["y"].to_numpy()
            parts.append(out)
        sample=pd.concat(parts,ignore_index=True)
        value=_corr(sample)
        if not pd.isna(value):
            null.append(abs(value))
    if not null:
        return float("nan")
    return float((1+sum(v>=abs(observed) for v in null))/(1+len(null)))


def scan_revenue_to_margin(
    panel: pd.DataFrame,
    *,
    features: tuple[str,...]=("monthly_revenue_3m_yoy","revenue_yoy"),
    targets: tuple[str,...]=("gross_margin_qoq","gross_margin_yoy_delta"),
    lags: tuple[int,...]=(0,1,2),
    config: MarginScanConfig=MarginScanConfig(),
) -> pd.DataFrame:
    required={"ticker","report_date","available_date"}
    missing=required-set(panel.columns)
    if missing:
        raise ValueError(f"Missing factor-data columns: {sorted(missing)}")

    abf=panel.copy()
    if "stock_id" in abf.columns:
        abf["_stock_id"]=abf["stock_id"].astype(str).str.extract(r"(\d{4})",expand=False)
    else:
        abf["_stock_id"]=abf["ticker"].astype(str).str.extract(r"(\d{4})",expand=False)
    abf=abf[abf["_stock_id"].isin(ABF_STOCK_IDS)].copy()
    rows=[]
    for feature in features:
        if feature not in abf.columns:
            continue
        for target in targets:
            if target not in abf.columns:
                continue
            for lag in lags:
                pieces=[]
                company_corrs=[]
                company_results=[]
                for ticker,g in abf.groupby("ticker",sort=False):
                    aligned=_align_company(g,feature,target,lag)
                    if not aligned.empty:
                        pieces.append(aligned)
                        corr=_corr(aligned)
                        if not pd.isna(corr):
                            company_corrs.append(corr)
                        company_results.append({'company':str(ticker),'product':'ABF','sample_size':len(aligned),
                            'spearman':None if pd.isna(corr) else corr,
                            'source_scope':'COMPANY_TOTAL','is_proxy':True,'evidence_status':'DERIVED',
                            'first_feature_available_date':aligned['feature_available_date'].min().isoformat(),
                            'last_target_available_date':aligned['target_available_date'].max().isoformat()})
                if not pieces:
                    continue
                aligned=pd.concat(pieces,ignore_index=True).sort_values("target_available_date")
                corr=_corr(aligned)
                dates=sorted(aligned['target_report_date'].unique())
                split=min(len(dates)-1,max(1,int(len(dates)*config.train_fraction)))
                test=aligned[aligned['target_report_date']>=dates[split]]
                cutoff=test['feature_available_date'].min()
                train=aligned[(aligned['target_report_date']<dates[split]) & (aligned['target_available_date']<cutoff)]
                oos=_corr(test)
                sign_share=(
                    float(sum(np.sign(v)==np.sign(corr) for v in company_corrs)/len(ABF_STOCK_IDS))
                    if company_corrs and not pd.isna(corr) else 0.0
                )
                pvalue=_block_permutation_pvalue(
                    aligned,corr,
                    iterations=config.permutation_iterations,
                    block_size=config.block_size,
                    seed=config.random_seed+lag,
                )
                rows.append({
                    "feature":feature,
                    "target":target,
                    "lag_quarters":lag,
                    "timing_class":"COINCIDENT" if lag==0 else "LEADING",
                    "sample_size":len(aligned),
                    "spearman":corr,
                    "oos_spearman":oos,
                    "cross_company_sign_share":sign_share,
                    "permutation_p":pvalue,
                    "availability_method":"factor-data available_date; currently filing-date proxy",
                    'product':'ABF','source_scope':'COMPANY_TOTAL','is_proxy':True,
                    'accounting_basis':next(iter(set(aligned['accounting_basis']))) if aligned['accounting_basis'].nunique()==1 else 'UNKNOWN',
                    'return_basis':'NOT_APPLICABLE','evidence_status':'DERIVED',
                    'company_product_results':company_results,
                    'train_sample_size':len(train),
                    'train_last_label_available_date':train['target_available_date'].max().isoformat() if len(train) else None,
                    'test_first_feature_available_date':cutoff.isoformat(),
                    'eligibility':'reject',
                })

    result=pd.DataFrame(rows)
    if result.empty:
        return result
    result["fdr_q"]=benjamini_hochberg(result["permutation_p"])
    result["status"]="WEAK"
    insufficient=result["sample_size"]<config.min_samples
    candidate=(
        ~insufficient
        & result["spearman"].abs().ge(config.min_abs_spearman)
        & result["oos_spearman"].notna()
        & (np.sign(result["oos_spearman"])==np.sign(result["spearman"]))
        & result["oos_spearman"].abs().ge(config.min_abs_oos)
        & result["cross_company_sign_share"].ge(config.min_cross_company_share)
        & result["fdr_q"].le(0.10)
    )
    result.loc[insufficient,"status"]="INSUFFICIENT"
    result.loc[candidate,"status"]="CANDIDATE"
    result.loc[candidate & result['accounting_basis'].eq('STANDALONE_QUARTER'),'eligibility']='support-only'
    result["score"]=result["spearman"].abs()*result["cross_company_sign_share"]
    return result.sort_values(["status","score"],ascending=[True,False]).reset_index(drop=True)
