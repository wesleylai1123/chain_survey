"""Exercise company/scenario/transform controls and capture only the app window."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tkinter as tk

import pandas as pd
from PIL import ImageGrab

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from app.abf_company_survey_view import CompanySurveyView
from core.abf_company_survey import build_company_survey


def select_tab(view, title):
    view.book.select(next(tab for tab in view.book.tabs() if view.book.tab(tab,'text')==title))


def capture(root, path):
    root.update_idletasks()
    root.update()
    root.lift()
    root.after(350,root.quit)
    root.mainloop()
    if sys.platform=='win32':
        ImageGrab.grab(window=root.winfo_id()).save(path)
    else:
        bounds=(root.winfo_rootx(),root.winfo_rooty(),
                root.winfo_rootx()+root.winfo_width(),root.winfo_rooty()+root.winfo_height())
        ImageGrab.grab(bbox=bounds).save(path)
    if not path.exists() or not path.stat().st_size:
        raise RuntimeError(f'Missing app screenshot: {path}')


def assert_selection(view, company, scenario, ft, tt):
    view.company_var.set(company)
    view.scenario_var.set(scenario)
    view.metric_var.set('pcb_revenue_yoy')
    view.feature_var.set(ft)
    view.target_var.set(tt)
    view.render()
    detail=view.selected_detail
    assert detail['company']==company and detail['product']=='ABF'
    assert (detail['scenario'],detail['feature_transform'],detail['target_transform'])==(scenario,ft,tt)
    expected=[[row['x'],row['y']] for row in detail['sample_rows']]
    collections=view.scatter_ax.collections
    # The second collection highlights a subset of the full audited sample.
    assert (collections[0].get_offsets().tolist() if collections else [])==expected
    oos=[row for row in detail['sample_rows'] if any(
        fold.get('first_test_period','~')<=row['period']<=fold.get('last_test_period','')
        for fold in detail['oos_folds'])]
    assert len(collections)==(1+bool(oos) if expected else 0)
    if oos:
        assert collections[1].get_offsets().tolist()==[[row['x'],row['y']] for row in oos]
    assert view.selected_company['financial_bridge']['beta'] is None
    assert all(f['company']==company for f in view.selected_company['primary_facts'])
    return detail


def main():
    out=ROOT/'artifacts'
    report=json.loads((out/'abf_company_survey.json').read_text(encoding='utf-8'))
    assert {c['company'] for c in report['companies']}=={'3037.TW','3189.TW','8046.TW'}
    root=tk.Tk()
    root.title('chain_survey · ABF 公司研究')
    root.geometry('1600x980+0+0')
    view=CompanySurveyView(root,report)
    view.pack(fill='both',expand=True)
    exercised=[]
    margin_exercised=[]
    for company in report['companies']:
        ticker=company['company']
        for scenario in ('UPSIDE','DOWNSIDE'):
            for ft,tt in (('LEVEL','LEVEL'),('LEVEL','CHANGE'),('CHANGE','LEVEL'),('CHANGE','CHANGE')):
                detail=assert_selection(view,ticker,scenario,ft,tt)
                exercised.append(detail['comparison_id'])
        assert_selection(view,ticker,'UPSIDE','LEVEL','LEVEL')
        select_tab(view,'趨勢與相關')
        capture(root,out/f'abf-company-survey-{ticker[:4]}.png')
        for scenario in ('UPSIDE','DOWNSIDE'):
            view.scenario_var.set(scenario)
            for feature in ('monthly_revenue_3m_yoy','revenue_yoy'):
                for target in ('gross_margin_qoq','gross_margin_yoy_delta'):
                    for lag in (0,1,2):
                        view.margin_feature_var.set(feature);view.margin_target_var.set(target);view.margin_lag_var.set(lag)
                        view.render()
                        detail=view.selected_margin_detail
                        assert detail and detail['company']==ticker and detail['scenario']==scenario
                        assert detail['forecast_beta'] is None
                        expected=[[s['x'],s['y']] for s in detail['sample_rows']]
                        collections=view.margin_ax.collections
                        assert (collections[0].get_offsets().tolist() if collections else [])==expected
                        assert len(collections)<=2
                        if not any(f['valid'] for f in detail['oos_folds']):assert len(collections)<=1
                        margin_exercised.append(detail['comparison_id'])
        view.margin_feature_var.set('revenue_yoy');view.margin_target_var.set('gross_margin_qoq');view.margin_lag_var.set(0)
        view.scenario_var.set('DOWNSIDE');view.render()
        select_tab(view,'財務脈絡')
        view.finance_book.select(next(t for t in view.finance_book.tabs() if view.finance_book.tab(t,'text')=='Revenue→GM驗證'))
        capture(root,out/f'abf-company-survey-margin-{ticker[:4]}.png')
    assert_selection(view,'3037.TW','DOWNSIDE','LEVEL','LEVEL')
    capture(root,out/'abf-company-survey-downside.png')
    assert_selection(view,'3037.TW','UPSIDE','CHANGE','CHANGE')
    capture(root,out/'abf-company-survey-change.png')
    select_tab(view,'研究總覽')
    capture(root,out/'abf-company-survey-summary.png')
    select_tab(view,'財務脈絡')
    capture(root,out/'abf-company-survey-financial.png')
    view.destroy()
    missing=build_company_survey({},pd.DataFrame(),[],as_of=report['as_of'])
    view=CompanySurveyView(root,missing)
    view.pack(fill='both',expand=True)
    detail=assert_selection(view,'3037.TW','DOWNSIDE','CHANGE','CHANGE')
    assert detail['data_status']=='UNAVAILABLE' and not detail['sample_rows']
    assert view.selected_margin_detail is None and not view.margin_ax.collections
    select_tab(view,'趨勢與相關')
    capture(root,out/'abf-company-survey-unavailable.png')
    root.destroy()
    result=dict(status='PASS',selection_count=len(exercised),comparison_ids=exercised,
                margin_selection_count=len(margin_exercised),margin_comparison_ids=margin_exercised,
                unavailable_exercised=True,
                screenshot_scope='TARGET_WINDOW_HANDLE' if sys.platform=='win32' else 'ISOLATED_DISPLAY_BOUNDS')
    (out/'abf-company-survey-ui-smoke.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('ABF_COMPANY_SURVEY_UI_SMOKE_OK',len(exercised),'selections; unavailable exercised')


if __name__=='__main__':
    main()
