"""Audited Company × Product comparison view shared by the ABF lab and smoke tests."""
import tkinter as tk
from tkinter import ttk

import pandas as pd


def build_semantics_tab(parent, table: pd.DataFrame, details: dict):
    bg,text,muted='#F3F6FA','#172033','#667085'
    intro=tk.Frame(parent,bg=bg,padx=18,pady=16)
    intro.pack(fill='x')
    tk.Label(intro,text='ABF · Company × Product evidence',bg=bg,fg=text,font=('Segoe UI',16,'bold')).pack(anchor='w')
    tk.Label(intro,text='LEVEL = recorded YoY rate (%)   ·   CHANGE = month-to-month difference of YoY (percentage points)',
        bg=bg,fg=text,font=('Segoe UI',10)).pack(anchor='w',pady=(5,2))
    tk.Label(intro,text='Industry PCB and consolidated company revenue are proxies for ABF. Eligible requires statistical, source, PIT and product-scope evidence.',
        bg=bg,fg=muted,font=('Segoe UI',10),wraplength=1400,justify='left').pack(anchor='w')
    tk.Label(intro,text='Leading → company revenue · Coincident → current revenue · Lagging hypothesis → GM / EPS. Driver state → sensitivity estimate → structural model.',
        bg=bg,fg=muted,font=('Segoe UI',10),wraplength=1400,justify='left').pack(anchor='w',pady=(3,0))
    if table.empty:
        tk.Label(parent,text='UNAVAILABLE · No research input is connected. No actual values or calibrated betas are shown.',bg=bg,fg='#B45309').pack(anchor='w',padx=18)
        return None
    counts=table['eligibility'].value_counts()
    tk.Label(intro,text='   '.join(f'{k}: {int(counts.get(k,0))}' for k in ('eligible','support-only','reject')),
        bg=bg,fg='#B45309',font=('Segoe UI',11,'bold')).pack(anchor='w',pady=(10,0))
    filters=tk.Frame(parent,bg=bg,padx=18)
    filters.pack(fill='x')
    scenario=tk.StringVar(value='DOWNSIDE')
    company=tk.StringVar(value='All companies')
    ttk.Label(filters,text='Independent case').pack(side='left')
    case_box=ttk.Combobox(filters,textvariable=scenario,values=['DOWNSIDE','UPSIDE'],state='readonly',width=14)
    case_box.pack(side='left',padx=8)
    company_box=ttk.Combobox(filters,textvariable=company,values=['All companies']+sorted(table.company.unique()),state='readonly',width=16)
    company_box.pack(side='left',padx=8)
    content=tk.Frame(parent,bg=bg,padx=18,pady=12)
    content.pack(fill='both',expand=True)
    cols=('company','metric','transforms','n','rho','oos','agreement','fdr','data','eligibility')
    tree=ttk.Treeview(content,columns=cols,show='headings',height=10)
    headings=('Company × ABF','Source metric','Feature → Target','N','ρ','OOS sign','Company sign','FDR q','Data state','Classification')
    widths=(120,220,150,50,65,90,100,70,130,110)
    for c,h,w in zip(cols,headings,widths):
        tree.heading(c,text=h)
        tree.column(c,width=w,anchor='center',stretch=c in {'metric','data'})
    scroll=ttk.Scrollbar(content,orient='vertical',command=tree.yview)
    tree.configure(yscrollcommand=scroll.set)
    tree.pack(side='left',fill='both',expand=True)
    scroll.pack(side='right',fill='y')
    detail=tk.Text(parent,height=10,wrap='word',font=('Segoe UI',10),bg='white',fg=text,padx=16,pady=10)
    detail.pack(fill='x',padx=18,pady=(0,16))

    def show_detail(_event=None):
        selected=tree.selection()
        if not selected:
            return
        d=details[selected[0]]
        failures=', '.join(d['reasons']) or 'All evidence gates pass'
        body=(f"{d['company']} × ABF · {d['scenario']} · {d['eligibility']} · Evidence: {d['evidence_status']}\n"
              f"Source scope: INDUSTRY_AGGREGATE → COMPANY_TOTAL · Accounting: {d['accounting_basis']} · Return basis: {d['return_basis']}\n"
              f"Data: {d['data_status']} · Exact release times for all samples: {d['pit_exact']} · Leading {d['lag_months']} month vs {d['target_metric']}\n"
              f"Bootstrap 95%: [{d['bootstrap_ci_low']}, {d['bootstrap_ci_high']}] · permutation p: {d['permutation_p']} · FDR family: {d['fdr_family_size']}\n"
              f"OOS: {len(d['oos_folds'])} fixed chronological folds; training labels purged by availability. No holdout winner selection.\n"
              f"Reasons: {failures}\nSources: {' | '.join(d['source_urls']) or 'UNAVAILABLE'}\n"
              'Every sample retains observation_date / release_date / available_at / signal_generated_at and dependency IDs in the JSON artifact.')
        detail.configure(state='normal')
        detail.delete('1.0','end')
        detail.insert('1.0',body)
        detail.configure(state='disabled')

    def refresh(_event=None):
        tree.delete(*tree.get_children())
        selected=table[table.scenario.eq(scenario.get())]
        if company.get()!='All companies':
            selected=selected[selected.company.eq(company.get())]
        for _,r in selected.iterrows():
            number=lambda v: '—' if pd.isna(v) else f'{float(v):.2f}'
            tree.insert('','end',iid=r.comparison_id,values=(r.company,r.metric_id,f'{r.feature_transform} → {r.target_transform}',
                r.sample_size,number(r.spearman),number(r.oos_sign_stability),number(r.company_sign_agreement),number(r.fdr_q),r.data_status,r.eligibility))
        if tree.get_children():
            tree.selection_set(tree.get_children()[0])
            show_detail()
    tree.bind('<<TreeviewSelect>>',show_detail)
    case_box.bind('<<ComboboxSelected>>',refresh)
    company_box.bind('<<ComboboxSelected>>',refresh)
    refresh()
    return tree
