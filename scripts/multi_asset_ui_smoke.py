"""Render real service outputs using visibly labeled synthetic TEST ONLY inputs."""
from __future__ import annotations

import copy
import argparse
import hashlib
import json
from pathlib import Path
import sys
from PIL import ImageGrab

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'tests'))
from app.multi_asset_lab import MultiAssetLab
from core.multi_asset.service import run_research, validate_result
from multi_asset_fixture import make_request


def capture(app, path):
    app.update_idletasks()
    app.update()
    app.lift()
    app.after(250, app.quit)
    app.mainloop()
    if sys.platform == 'win32':
        ImageGrab.grab(window=app.winfo_id()).save(path)
    else:
        bounds = (app.winfo_rootx(), app.winfo_rooty(), app.winfo_rootx()+app.winfo_width(), app.winfo_rooty()+app.winfo_height())
        ImageGrab.grab(bbox=bounds).save(path)
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f'No screenshot: {path}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frozen', action='store_true', help='Render verified synthetic result fixtures without private engine checkout')
    args = parser.parse_args()
    def evaluate(request, name):
        if not args.frozen:
            return run_research(request)
        fixture = ROOT/'tests/fixtures/multi_asset'/f'{name}.result.json'
        result = json.loads(fixture.read_text(encoding='utf-8'))
        raw = (json.dumps(request, ensure_ascii=False, sort_keys=True, allow_nan=False)+'\n').encode('utf-8')
        return validate_result(result, request, hashlib.sha256(raw).hexdigest())
    output = ROOT/'artifacts'
    output.mkdir(exist_ok=True)
    app = MultiAssetLab()
    app.title('chain_survey · SYNTHETIC TEST ONLY · 非市場績效')
    capture(app, output/'multi-asset-empty.png')
    request = make_request()
    (output/'multi-asset-test-only-request.json').write_text(json.dumps(request, indent=2), encoding='utf-8')
    app.set_request(request, {'notice': 'SYNTHETIC TEST ONLY'})
    result = evaluate(request, 'accumulation')
    app.render_result(result)
    app.status.set('SYNTHETIC TEST ONLY · 此處價格、配息與曝險皆為離線測試資料，非市場績效。')
    assert len(app.tables['comparison'].get_children()) == 5
    assert app.tables['rolling'].get_children()
    for index, name in [(0, 'compare'), (3, 'correlation'), (4, 'exposure'), (5, 'evidence')]:
        app.book.select(index)
        capture(app, output/f'multi-asset-{name}.png')
    (output/'multi-asset-test-only-result.json').write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf-8')
    request['objective'] = 'income'
    app.set_request(request, {'notice': 'SYNTHETIC TEST ONLY'})
    app.render_result(evaluate(request, 'income'))
    app.status.set('SYNTHETIC TEST ONLY · Income：可支用現金與資產成長分開呈現。')
    app.book.select(1)
    capture(app, output/'multi-asset-income.png')
    request['observations'][0]['value'] = None
    request['cash_flow_assumptions']['withholding_tax_rate'] = None
    request['holdings'] = []
    app.set_request(request, {'notice': 'SYNTHETIC TEST ONLY — MISSING INPUTS'})
    missing = evaluate(request, 'missing')
    app.render_result(missing)
    assert missing['instruments'][0]['metrics']['total_return'] is None
    assert missing['instruments'][0]['metrics']['net_paid_cash'] is None
    app.status.set('SYNTHETIC TEST ONLY · 缺少價格、稅率與持股；不推估未知數據。')
    app.book.select(0)
    capture(app, output/'multi-asset-missing.png')
    app.book.select(6)
    capture(app, output/'multi-asset-quality.png')
    app.destroy()
    print('MULTI_ASSET_UI_SMOKE_OK assets=5 objectives=2 missing=visible')


if __name__ == '__main__':
    main()
