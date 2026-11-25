"""Render verified Taiwan ETF valuation and index data without fetching market data."""
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

DEFAULT_MANIFEST = ROOT/'tests/fixtures/taiwan_etf_context/capture/manifest.json'
LEGACY_MANIFEST = ROOT/'tests/fixtures/taiwan_official/capture/manifest.json'
NAV_DATE = '2026-11-20'


def rows(tree):
    return [tree.item(item, 'values') for item in tree.get_children()]


def assert_real_context(app):
    nav = {row[0]: row[1:7] for row in rows(app.etf_context.nav)}
    assert nav == {
        '0050.TW': (NAV_DATE, '84.67', 'TWD', '84.45', '-0.26%', '可用'),
        '00981A.TW': (NAV_DATE, '18.81', 'TWD', '18.58', '-1.22%', '可用'),
    }, nav
    references = rows(app.etf_context.reference)
    assert len(references) == 2
    for row, identity in zip(references, ('TWSE.TAI50.TR', 'TWSE.TAIEX.TR')):
        assert identity in row[0]
        assert row[1:7] == ('2026-11-02', NAV_DATE, '15/15', 'TWD', '含息報酬指數', '可用'), row


def capture_edge_cases(app, request, lineage, output):
    missing = copy.deepcopy(request)
    removed = {('0050.TW', NAV_DATE), ('TWSE.TAI50.TR', '2026-11-13')}
    missing['observations'] = [r for r in missing['observations'] if (r['instrument_id'], r['period']) not in removed]
    app.set_request(missing, lineage)
    app.title('chain_survey · 缺值測試（刻意移除資料）')
    app.status.set('缺值測試：移除 0050 的一筆同日收盤價與臺灣50報酬指數的一筆比較資料。')
    assert app.result is None and not rows(app.tables['comparison']) and not app.ax.lines
    nav = {row[0]: row for row in rows(app.etf_context.nav)}
    assert nav['0050.TW'][1:7] == (NAV_DATE, '84.67', 'TWD', '—', '—', '缺少同日收盤價')
    assert nav['00981A.TW'][5] == '-1.22%'
    tai50, taiex = rows(app.etf_context.reference)
    assert tai50[1:4] == ('2026-11-02', NAV_DATE, '14/15') and tai50[6] == '僅涵蓋部分研究日期'
    assert taiex[3] == '15/15'
    capture(app, output/'taiwan-etf-context-missing.png')

    shortened = copy.deepcopy(request)
    shortened['period_grid'] = [day for day in shortened['period_grid'] if day < NAV_DATE]
    for key in ('observations', 'fx_rates'):
        shortened[key] = [r for r in shortened[key] if r['period'] < NAV_DATE]
    app.set_request(shortened, lineage)
    app.title('chain_survey · 期間外淨值測試（刻意縮短研究期間）')
    app.status.set('期間外淨值測試：研究迄日縮短至 2026-11-19，保留來源的原始淨值日期與數值。')
    for row, value in zip(rows(app.etf_context.nav), ('84.67', '18.81'), strict=True):
        assert row[1:7] == (NAV_DATE, value, 'TWD', '—', '—', '淨值日期在研究期間外'), row
    for row in rows(app.etf_context.reference):
        assert row[1:4] == ('2026-11-02', NAV_DATE, '14/14'), row
    capture(app, output/'taiwan-etf-context-outside-window.png')

    app.set_request(*load_capture(LEGACY_MANIFEST))
    app.title('chain_survey · 舊版官方快照')
    assert len(app.request['instruments']) == 3
    assert not rows(app.etf_context.nav) and not rows(app.etf_context.reference)
    assert '這份資料檔未包含' in app.etf_context.banner.get()
    capture(app, output/'taiwan-etf-context-legacy-empty.png')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=DEFAULT_MANIFEST,
                        help='Replay a verified capture (the default also exercises missing/legacy states)')
    parser.add_argument('--live-engine', action='store_true',
                        help='Recompute through the local metrics service with the same frozen inputs')
    args = parser.parse_args()
    request, lineage = load_capture(args.manifest)
    if 'etf_context' not in request['adapter_lineage']:
        parser.error('Select an official manifest captured with --include-etf-context')
    if args.live_engine:
        result = run_research(request)
    else:
        result = json.loads((args.manifest.parent/'result.json').read_bytes())
    input_sha256 = hashlib.sha256((args.manifest.parent/'request.json').read_bytes()).hexdigest()
    validate_result(result, request, input_sha256)

    output = ROOT/'artifacts'
    output.mkdir(exist_ok=True)
    exercise_frozen_cases = args.manifest.resolve() == DEFAULT_MANIFEST
    app = MultiAssetLab()
    try:
        app.title('chain_survey · 真實官方快照')
        app.set_request(request, lineage)
        app.render_result(result)
        app.book.select(app.etf_context)
        assert 'TEST ONLY' not in app.status.get() and 'TEST ONLY' not in app.etf_context.banner.get()
        refs = {item['instrument_id'] for item in request['instruments'] if item['asset_type'] == 'benchmark'}
        ref_symbols = {item['symbol'] for item in request['instruments'] if item['asset_type'] == 'benchmark'}
        assert refs.isdisjoint(row[2] for row in rows(app.tables['official']))
        assert ref_symbols.isdisjoint(line.get_label() for line in app.official.ax.lines)
        if exercise_frozen_cases:
            assert_real_context(app)
        capture(app, output/'taiwan-etf-context-populated.png')

        assert {row[0] for row in rows(app.tables['comparison'])} == {
            item['instrument_id'] for item in request['instruments']
        }
        assert all(item['metrics']['total_return'] is None for item in result['instruments'] if item['asset_type'] == 'etf')
        app.book.select(0)
        capture(app, output/'taiwan-etf-context-comparison.png')
        if exercise_frozen_cases:
            app.book.select(app.etf_context)
            capture_edge_cases(app, request, lineage, output)
    finally:
        app.destroy()
    print(f'TAIWAN_ETF_CONTEXT_UI_SMOKE_OK assets={len(request["instruments"])} '
          f'dates={len(request["period_grid"])} sources={lineage["source_count"]}')


if __name__ == '__main__':
    main()
