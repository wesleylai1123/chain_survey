"""Render and exercise the audited ABF view with real and unavailable inputs."""
import json
from pathlib import Path
import sys
import tkinter as tk

import pandas as pd
from PIL import ImageGrab

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))
from app.abf_semantics_view import build_semantics_tab
from core.abf_transform_validation import compare_abf_transforms


def capture(root,path):
    root.update_idletasks()
    root.update()
    root.lift()
    root.update()
    # Allow the native compositor to present the mapped window before capture.
    root.after(350,root.quit)
    root.mainloop()
    bounds=(root.winfo_rootx(),root.winfo_rooty(),root.winfo_rootx()+root.winfo_width(),root.winfo_rooty()+root.winfo_height())
    ImageGrab.grab(bbox=bounds).save(path)
    if not path.exists() or not path.stat().st_size:
        raise RuntimeError('Screenshot missing')


def main():
    out=ROOT/'artifacts'
    report=json.loads((out/'abf_semantics_validation.json').read_text(encoding='utf-8'))
    root=tk.Tk()
    root.title('chain_survey · ABF Semantics & Stability')
    root.geometry('1580x900+0+0')
    view=tk.Frame(root,bg='#F3F6FA')
    view.pack(fill='both',expand=True)
    tree=build_semantics_tab(view,pd.DataFrame(report['comparisons']),report['details'])
    assert len(tree.get_children())==60
    tree.selection_set(tree.get_children()[-1])
    tree.event_generate('<<TreeviewSelect>>')
    capture(root,out/'abf-semantics-present.png')
    view.destroy()
    table,details=compare_abf_transforms(pd.DataFrame(),as_of=report['as_of'],iterations=19)
    view=tk.Frame(root,bg='#F3F6FA')
    view.pack(fill='both',expand=True)
    tree=build_semantics_tab(view,table,details)
    assert len(tree.get_children())==60
    assert set(table.data_status)=={'UNAVAILABLE'}
    capture(root,out/'abf-semantics-unavailable.png')
    root.destroy()
    print('ABF_SEMANTICS_UI_SMOKE_OK present=60 unavailable=60')


if __name__=='__main__':
    main()
