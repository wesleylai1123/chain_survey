"""Render verified REAL official snapshots; no live network in CI."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.multi_asset_lab import MultiAssetLab
from core.multi_asset.official_capture import load_capture
from core.multi_asset.service import run_research, validate_result
from scripts.multi_asset_ui_smoke import capture


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=ROOT/'tests/fixtures/taiwan_official/capture/manifest.json')
    parser.add_argument('--live-engine', action='store_true', help='Recompute through the local private service; does not fetch data')
    args = parser.parse_args()
    request, lineage = load_capture(args.manifest)
    if args.live_engine:
        result = run_research(request)
    else:
        result = json.loads((args.manifest.parent/'result.json').read_text(encoding='utf-8'))
        raw = (json.dumps(request, ensure_ascii=False, sort_keys=True, allow_nan=False)+'\n').encode('utf-8')
        validate_result(result, request, hashlib.sha256(raw).hexdigest())
    output = ROOT/'artifacts'
    output.mkdir(exist_ok=True)
    app = MultiAssetLab()
    app.title('chain_survey · REAL OFFICIAL SNAPSHOT · UNADJUSTED')
    app.set_request(request, lineage)
    app.render_result(result)
    app.book.select(app.official)
    assert app.tables['official'].get_children()
    assert '未調整' in app.source_banner.get()
    assert 'TEST ONLY' not in app.status.get()
    capture(app, output/'taiwan-official-data.png')
    app.book.select(0)
    assert all(r['metrics']['total_return'] is None for r in result['instruments'] if r['asset_type']=='etf')
    capture(app, output/'taiwan-official-adjustment-limits.png')
    app.book.select(6)
    capture(app, output/'taiwan-official-provenance.png')
    # Missing source facts remain missing in the actual raw-data view, without filling.
    missing = copy.deepcopy(request)
    first = next(r for r in missing['observations'] if r['instrument_id']=='0050.TW')
    first['value'] = None
    app.set_request(missing, dict(lineage, notice='REAL SNAPSHOT WITH INTENTIONAL MISSING-VALUE TEST MUTATION'))
    app.status.set('缺值測試：真實快照的一筆報價刻意移除；不補值。')
    app.book.select(app.official)
    assert any('未知' in app.tables['official'].item(item, 'values') for item in app.tables['official'].get_children())
    capture(app, output/'taiwan-official-missing.png')
    app.destroy()
    print(f'TAIWAN_OFFICIAL_UI_SMOKE_OK dates={len(request["period_grid"])} sources={lineage["source_count"]} raw_total_return=unavailable')


if __name__ == '__main__':
    main()
