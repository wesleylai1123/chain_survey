"""Read-only presentation of ABFCompanySurveyV1; no statistical estimation."""
from __future__ import annotations

from html import escape
import json
import math
from urllib.parse import urlsplit


METRIC_LABELS = {
    'pcb_revenue_yoy': 'PCB 產業營收年增率',
    'rigid_pcb_export_yoy': '硬板出口年增率',
    'pcb_material_revenue_yoy': 'PCB 材料營收年增率',
    'ccl_export_yoy': '銅箔基板出口年增率',
    'ccl_import_yoy': '銅箔基板進口年增率',
    'abf_orders_backlog': 'ABF 訂單／積壓訂單',
    'abf_customer_inventory': 'ABF 客戶庫存',
    'abf_utilization': 'ABF 實際稼動率',
    'abf_pricing': 'ABF 定價', 'abf_asp': 'ABF 平均售價', 'abf_product_mix': 'ABF 營收占比',
    'abf_revenue_qoq': 'ABF 營收季增率', 'abf_revenue_yoy': 'ABF 營收年增率',
    'company_revenue': '公司整體營收', 'company_gross_profit': '公司整體毛利',
    'company_gross_margin_reported': '公司整體毛利率（公告）',
    'company_gross_margin_derived': '公司整體毛利率（依公告金額計算）',
    'company_operating_income': '公司整體營業利益',
    'company_net_nonoperating_income': '公司整體業外淨收益',
    'company_pretax_income': '公司整體稅前利益',
    'company_basic_eps': '公司整體基本 EPS', 'company_diluted_eps': '公司整體稀釋 EPS',
    'nonoperating_share_of_pretax_income': '業外淨收益／稅前利益',
    'application_revenue_mix': '公司應用別營收占比', 'segment_revenue': '部門營收',
    'product_development_guidance': 'ABF 產品開發展望',
    'application_demand_driver': '應用需求說明', 'downside_signal': '下行情境營運訊息',
}

STATUS_LABELS = {'DISCLOSED': '直接揭露', 'DERIVED': '依揭露計算', 'ESTIMATED': '估計',
    'INFERRED': '推論', 'UNKNOWN': '未知', 'PIT_UNAVAILABLE': '歷史公開時間未驗證',
    'UNAVAILABLE': '資料無法取得', 'NOT_CALIBRATED': '尚未校準',
    'eligible': '可用', 'support-only': '僅供佐證', 'reject': '未通過'}


def metric_label(metric: str) -> str:
    return METRIC_LABELS.get(metric, metric)


def number(value, digits: int = 2) -> str:
    if value is None:
        return '—'
    try:
        return f'{float(value):,.{digits}f}' if math.isfinite(float(value)) else '—'
    except (TypeError, ValueError):
        return str(value)


def unit_label(unit: str | None) -> str:
    return {'percent': '%', 'percentage_points': '百分點', 'ratio': '比率',
            'TWD': '新台幣元', 'TWD_per_share': '元／股'}.get(unit, unit or '—')


def fact_value(fact: dict) -> str:
    if fact.get('value') is None:
        return '文字揭露'
    return f"{number(fact['value'])} {unit_label(fact.get('unit'))}"


def _observed_numeric(fact: dict) -> bool:
    return (fact.get('value') is not None and not fact.get('is_forward_looking', False)
            and fact.get('evidence_status') in {'DISCLOSED', 'DERIVED'})


def latest_gross_margin_fact(company: dict) -> dict | None:
    facts = [f for f in company.get('primary_facts', []) if f.get('metric_id') in {
        'company_gross_margin_reported', 'company_gross_margin_derived'} and _observed_numeric(f)
             and f.get('source_scope') == 'COMPANY_TOTAL']
    return max(facts, key=lambda f: (f.get('observation_date', ''),
               f.get('metric_id') == 'company_gross_margin_reported')) if facts else None


def company_brief(company: dict) -> list[dict]:
    """Manager-readable facts; every sentence carries its reviewed fact IDs."""
    facts = company.get('primary_facts', [])
    lines = []

    def matches(metric):
        return sorted([f for f in facts if f.get('metric_id') == metric],
                      key=lambda f: f.get('observation_date', ''))

    def add(text, refs):
        if refs:
            lines.append(dict(statement=text, fact_ids=[f['fact_id'] for f in refs]))

    def statement(fact):
        return fact.get('statement_zh') or fact.get('statement') or ''

    def direct_abf(metric):
        return [f for f in matches(metric) if _observed_numeric(f)
                and f.get('evidence_status') == 'DISCLOSED' and f.get('product') == 'ABF'
                and f.get('source_scope') == 'COMPANY_PRODUCT' and f.get('is_proxy') is False]

    mix = direct_abf('abf_product_mix')
    if mix:
        add('ABF 營收占比直接揭露：' + ' → '.join(number(f['value'], 0)+'%' for f in mix)
            + '（'+ ' → '.join(f['observation_date'][:10] for f in mix)+'）；為公司營收結構。', mix)
    yoy, qoq = direct_abf('abf_revenue_yoy'), direct_abf('abf_revenue_qoq')
    if yoy or qoq:
        add('ABF 營收成長直接揭露：' + '、'.join(
            [f"年增 {number(yoy[-1]['value'], 0)}%"] if yoy else [])
            + ('、' if yoy and qoq else '') + (f"季增 {number(qoq[-1]['value'], 0)}%" if qoq else '')
            + '；保留公告成長率，未用四捨五入占比反推。', [*(yoy[-1:] if yoy else []), *(qoq[-1:] if qoq else [])])
    gm = latest_gross_margin_fact(company)
    if gm:
        add(f"{gm['observation_date'][:10]} 公司整體毛利率 {number(gm['value'])}%；公司範圍，尚無 ABF 產品毛利率。", [gm])
    nonop = [f for f in matches('nonoperating_share_of_pretax_income') if _observed_numeric(f)
             and f.get('source_scope') == 'COMPANY_TOTAL']
    if nonop:
        qualifier = '依揭露計算' if nonop[-1]['evidence_status'] == 'DERIVED' else '直接揭露'
        add(f"獲利品質：業外淨收益占稅前利益 {number(nonop[-1]['value'])}%（{qualifier}）；EPS 無法單獨代表 ABF 本業改善。", nonop[-1:])
    for fact in matches('segment_revenue'):
        if not _observed_numeric(fact):
            continue
        product = fact.get('source_product') or fact.get('product') or '未提供產品範圍'
        add(f"部門營收 {fact_value(fact)}（{product}）：{statement(fact)}", [fact])
    for fact in matches('application_revenue_mix'):
        if not _observed_numeric(fact):
            continue
        add(f"公司應用別營收占比 {fact_value(fact)}：{statement(fact)}", [fact])
    for metric, prefix in (
            ('product_development_guidance', '前瞻展望（不作為實際稼動率輸入）：'),
            ('application_demand_driver', '公司需求說明：'),
            ('downside_signal', '下行觀察：')):
        for fact in matches(metric):
            if statement(fact):
                add(prefix + statement(fact), [fact])
    return lines


def scatter_points(detail: dict) -> list[dict]:
    folds = detail.get('oos_folds', [])
    return [dict(row, is_oos=any(f.get('first_test_period', '~') <= row.get('period', '')
            <= f.get('last_test_period', '') for f in folds)) for row in detail.get('sample_rows', [])]


def trend_series(company: dict, metric: str) -> list[dict]:
    grouped = {}
    own = f"abf_company_revenue_yoy::{company['company']}"
    for row in company.get('trend', {}).get('observations', []):
        if row.get('transform') != 'LEVEL' or row.get('metric_id') not in {metric, own}:
            continue
        key = (row['company'], row['metric_id'])
        grouped.setdefault(key, []).append(dict(period=row['period'], value=row.get('signal_value'),
            observation_id=row.get('observation_id'), source_urls=row.get('source_urls', [])))
    return [dict(company=key[0], metric_id=key[1], points=sorted(points, key=lambda p: p['period']))
            for key, points in grouped.items()]


def monthly_segments(points: list[dict], *, cadence: int = 1) -> list[list[dict]]:
    """Connect only finite observations at the declared calendar cadence."""
    segments, current, previous = [], [], None
    for point in sorted(points, key=lambda p: p['period']):
        year, month = map(int, point['period'][:7].split('-'))
        ordinal = year * 12 + month - 1
        value = point.get('value')
        usable = isinstance(value, (int, float)) and math.isfinite(value)
        if not usable or previous is None or ordinal - previous != cadence:
            if current:
                segments.append(current)
            current = []
        if usable:
            current.append(point)
        previous = ordinal if usable else None
    if current:
        segments.append(current)
    return segments


def detail_text(detail: dict) -> str:
    gates = detail.get('gates', {})
    text = [f"{detail.get('comparison_id', '')}",
        f"資格 {detail.get('eligibility', 'reject')} · 資料 {detail.get('data_status', 'UNAVAILABLE')} · {detail.get('evidence_status', 'UNKNOWN')}",
        f"ρ {number(detail.get('spearman'), 3)} · N {detail.get('sample_size', 0)} · bootstrap CI [{number(detail.get('bootstrap_ci_low'), 3)}, {number(detail.get('bootstrap_ci_high'), 3)}]",
        f"Permutation p {number(detail.get('permutation_p'), 4)} · FDR q {number(detail.get('fdr_q'), 4)}",
        f"OOS ρ {number(detail.get('oos_spearman'), 3)} · OOS 符號穩定度 {number(detail.get('oos_sign_stability'), 3)} · 跨公司同向比例 {number(detail.get('company_sign_agreement'), 3)}",
        f"PIT 精確 {detail.get('pit_exact', False)} · 來源鏈完整 {detail.get('source_lineage_complete', False)} · 代理值 {detail.get('is_proxy', True)}",
        f"產業範圍 {detail.get('source_scope')} → 公司整體 {detail.get('target_scope')}；候選領先 {detail.get('lag_months', 1)} 個月",
        '門檻：' + ('；'.join(f'{k}={"通過" if v else "未通過"}' for k, v in gates.items()) or 'UNAVAILABLE'),
        '原因：' + ', '.join(detail.get('reasons', [])), '\n固定時序 OOS（不依測試結果重選轉換）：']
    for fold in detail.get('oos_folds', []):
        text.append(f"{fold.get('first_test_period')} → {fold.get('last_test_period')} · train {fold.get('train_size')} / test {fold.get('test_size')} · ρ {number(fold.get('test_spearman'), 3)}")
    text.append('\n逐點稽核：期間、原始 x/y、來源 IDs、觀察／發布／可取得／訊號生成日期')
    for row in detail.get('sample_rows', []):
        text.append(f"\n{row['period']}  x={row.get('x')}  y={row.get('y')}\n"
                    + json.dumps({k: v for k, v in row.items() if k not in {'period', 'x', 'y'}}, ensure_ascii=False, indent=2))
    return '\n'.join(text)


def _safe_json(value) -> str:
    return (json.dumps(value, ensure_ascii=False, allow_nan=False).replace('&', '\\u0026')
            .replace('<', '\\u003c').replace('>', '\\u003e').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029'))


def source_link(fact: dict) -> str | None:
    for url in [*fact.get('source_urls', []), fact.get('source_url')]:
        try:
            parsed = urlsplit(url) if isinstance(url, str) else None
            if parsed and parsed.scheme in {'http', 'https'} and parsed.netloc:
                return url.split('#')[0]+f"#page={int(fact['page'])}" if fact.get('page') else url
        except (ValueError, TypeError):
            continue
    return None


def render_company_survey(report: dict) -> str:
    """Return one offline HTML file; dynamic text and JSON are injection-safe."""
    copy = {'metrics': METRIC_LABELS, 'statuses': STATUS_LABELS, 'companies': {c['company']: {
        'brief': company_brief(c), 'gross_margin': latest_gross_margin_fact(c),
        'fact_links': {f['fact_id']: source_link(f) for f in c.get('primary_facts', [])}}
        for c in report['companies']}}
    overview, margins = [], []
    for company in report['companies']:
        gm = latest_gross_margin_fact(company)
        overview.append('<button class="overview-card" data-company="'+escape(company['company'], quote=True)+'">'
            +'<span>'+escape(company['name'])+' <small>'+escape(company['stock_id'])+'</small></span>'
            +'<strong>'+(number(gm['value'])+'%' if gm else '—')+'</strong>'
            +'<small>公司整體毛利率 · '+escape(gm['observation_date'][:10] if gm else 'UNAVAILABLE')+'</small>'
            +'<small>'+escape(gm['fact_id'] if gm else '缺少經核對的一手公司財務事實')+'</small></button>')
        url = source_link(gm) if gm else None
        citation = ('<a href="'+escape(url, quote=True)+'" target="_blank" rel="noopener noreferrer">'
                    +escape(gm['fact_id'])+' · p.'+escape(str(gm.get('page', '—')))+'</a>') if url else 'UNAVAILABLE'
        margins.append('<tr><td>'+escape(company['name'])+' '+escape(company['stock_id'])+'</td><td>'
            +(number(gm['value'])+'%' if gm else '—')+'</td><td>COMPANY_TOTAL · 公司整體</td><td>'
            +escape(gm['observation_date'][:10] if gm else 'UNAVAILABLE')+'</td><td>'+citation+'</td></tr>')
    margin_table = '<table id="gross-margin-overview"><thead><tr><th>公司</th><th>毛利率</th><th>範圍</th><th>觀察期末</th><th>一手證據</th></tr></thead><tbody>'+''.join(margins)+'</tbody></table>'
    return (_HTML.replace('__OVERVIEW__', ''.join(overview))
            .replace('__MARGIN_OVERVIEW__', margin_table)
            .replace('__COPY__', _safe_json(copy)).replace('__REPORT__', _safe_json(report)))


_HTML = r'''<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ABF 公司研究 · 欣興／景碩／南電</title>
<style>
:root{--ink:#17283e;--muted:#64758b;--blue:#2563b4;--teal:#087f8c;--border:#dce4ed;--paper:#fff;--bg:#f1f5f9;--amber:#9a5c12}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.65 "Microsoft JhengHei","Noto Sans TC",system-ui,sans-serif}header{background:#10283f;color:white;padding:28px max(24px,calc((100vw - 1440px)/2));border-bottom:4px solid #4bafbc}header p{color:#b7cbdc;margin:4px 0}h1{font-size:28px;letter-spacing:.04em;margin:0}h2{font-size:19px;margin:0 0 12px}h3{font-size:16px;margin:0 0 8px}main{max-width:1488px;margin:auto;padding:24px}.eyebrow{font-size:12px;color:#9acfd6;letter-spacing:.14em}.muted,small{color:var(--muted)}small{display:block;font-size:12px}.overview{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:20px}.overview-card{font:inherit;text-align:left;cursor:pointer;border:1px solid var(--border);border-radius:12px;background:white;padding:18px 22px;border-top:4px solid var(--teal)}.overview-card span{font-weight:700;font-size:18px}.overview-card span small{display:inline}.overview-card strong{display:block;font-size:32px;line-height:1.5}.overview-card small:last-child{overflow-wrap:anywhere}.controls{display:flex;flex-wrap:wrap;gap:12px;padding:16px 20px;background:white;border:1px solid var(--border);border-radius:12px;margin-bottom:20px;position:sticky;top:0;z-index:2;box-shadow:0 3px 12px #10283f08}label{font-size:12px;color:var(--muted);display:grid;gap:4px}select{font:14px "Microsoft JhengHei",system-ui;background:#f8fafc;color:var(--ink);border:1px solid #bac9d9;border-radius:6px;padding:8px;max-width:320px}.card{background:white;border:1px solid var(--border);border-radius:12px;padding:22px;margin-bottom:20px;min-width:0}.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}.grid .card{margin-bottom:20px}.badge{display:inline-block;border-radius:4px;background:#fff3da;color:var(--amber);font-size:12px;padding:3px 8px;margin:0 5px 6px 0}.badge.neutral{background:#eaf1f8;color:#415a77}.brief{border-left:3px solid var(--teal);padding-left:16px}.brief p{margin:8px 0}.cite{font-size:11px;overflow-wrap:anywhere;color:var(--muted)}a{color:#225e9c;text-underline-offset:2px}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px}.stat{background:#f2f6fa;padding:10px;border-radius:7px}.stat b{display:block;font-size:20px}.stat small{font-size:11px}svg{width:100%;height:auto;display:block;min-height:210px}svg text{font:11px "Microsoft JhengHei",system-ui;fill:#64758b}.legend{display:flex;gap:18px;flex-wrap:wrap;color:var(--muted);font-size:12px}.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px}.chart-note{font-size:12px;color:var(--muted);min-height:42px}.table-wrap{overflow:auto}table{border-collapse:collapse;width:100%;font-size:13px;text-align:left}th,td{padding:10px;border-bottom:1px solid var(--border);vertical-align:top}th{background:#f5f8fb;color:#4a6078;white-space:nowrap}td small{max-width:430px;overflow-wrap:anywhere}details{border-top:1px solid var(--border);padding:12px 0}summary{cursor:pointer;font-weight:600}pre{font:12px/1.6 Consolas,monospace;background:#f4f7fa;border-radius:6px;padding:14px;overflow:auto;max-height:420px;white-space:pre-wrap;overflow-wrap:anywhere}.bridge{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.bridge>div{background:#f8fafc;padding:16px;border:1px dashed #c9d4e0;border-radius:8px}.empty{padding:45px 16px;color:var(--muted);text-align:center}.gates{font-size:12px;line-height:2}.fail{color:#ac3939}.pass{color:#21725a}.notice{font-size:13px;color:#785123;background:#fff8e8;padding:12px 16px;border-radius:8px;margin-bottom:14px}.research-list{padding-left:20px}.research-list li{margin:9px 0}.sources{overflow-wrap:anywhere;font-size:12px}footer{color:var(--muted);font-size:12px;padding:0 0 24px}.active{border-color:var(--blue);box-shadow:0 0 0 1px var(--blue)}@media(max-width:900px){.grid{grid-template-columns:1fr}.overview{gap:8px}.overview-card{padding:12px}.overview-card strong{font-size:25px}.stats{grid-template-columns:repeat(2,1fr)}main{padding:14px}.card{padding:16px}.controls{position:static}.bridge{grid-template-columns:1fr}}@media(max-width:600px){.overview{grid-template-columns:1fr}.overview-card strong{display:inline;margin-left:20px}.overview-card small:last-child{display:none}.overview-card small{font-size:11px}h1{font-size:23px}select{max-width:280px}header{padding:22px}.card{border-radius:8px}}
</style></head><body>
<header><div class="eyebrow">CHAIN SURVEY · COMPANY × ABF</div><h1>ABF 公司研究</h1><p>欣興・景碩・南電｜一手營運事實、相關性驗證與財務傳導</p><small id="report-date" style="color:#b7cbdc"></small></header>
<main><div class="overview">__OVERVIEW__</div><section class="card"><h2>三家公司公告毛利率對照</h2><p class="muted">公司整體毛利率；各公司的來源與觀察期末獨立標示，無 ABF 產品毛利率歸因。</p><div class="table-wrap">__MARGIN_OVERVIEW__</div></section>
<div class="controls" aria-label="研究條件">
<label>研究公司<select id="company-select"></select></label>
<label>獨立情境<select id="scenario-select"><option value="UPSIDE">UPSIDE · 上行</option><option value="DOWNSIDE">DOWNSIDE · 下行</option></select></label>
<label>產業指標<select id="metric-select"></select></label>
<label>指標轉換<select id="feature-select"><option value="LEVEL">LEVEL · 原始年增率</option><option value="CHANGE">CHANGE · 年增率月差</option></select></label>
<label>公司轉換<select id="target-select"><option value="LEVEL">LEVEL · 原始年增率</option><option value="CHANGE">CHANGE · 年增率月差</option></select></label></div>
<section class="card" id="assessment"><h2 id="company-title"></h2><div id="scenario-status"></div><div id="brief" class="brief"></div><p class="muted" id="assessment-note"></p></section>
<div class="grid"><section class="card"><h2>月度營運趨勢</h2><p class="chart-note">LEVEL 保留原始年增率（%）；缺月斷線，未插值。公司營收為公司整體代理值。</p><svg id="trend-chart" viewBox="0 0 620 300" role="img" aria-label="月度年增率趨勢"></svg><div id="trend-legend" class="legend"></div></section>
<section class="card"><h2>稽核樣本相關性</h2><p class="chart-note" id="scatter-note"></p><div id="scatter-stats" class="stats"></div><svg id="scatter-chart" viewBox="0 0 620 300" role="img" aria-label="固定情境稽核散點圖"></svg><div class="legend"><span><i class="dot" style="background:#96aabd"></i>完整樣本（灰）</span><span><i class="dot" style="background:#d98b29"></i>固定時序 OOS（橙色覆蓋）</span></div></section></div>
<section class="card"><h2>驗證資格與逐點來源</h2><p class="muted">所有預先宣告的指標與 2 × 2 轉換均可選；不依 OOS 結果挑選勝出模型。相關性不代表因果。</p><div id="validation-meta"></div><div id="gates" class="gates"></div><details><summary>OOS 分段、原始 x/y、來源 ID 與四個訊號日期</summary><div id="oos-table" class="table-wrap"></div><pre id="sample-detail"></pre></details></section>
<section class="card"><h2>經核對的一手營運與財務事實</h2><p class="muted">DISCLOSED = 直接揭露；DERIVED = 依來源計算。發布時間為 null 時顯示 PIT_UNAVAILABLE；前瞻展望與實績分開。本次取得／快照取得為目前封存紀錄的取得時間，歷史首次取得時間未驗證。</p><div id="facts" class="table-wrap"></div></section>
<section class="card"><h2>公司整體財務脈絡</h2><p class="notice">範圍：COMPANY_TOTAL · 全公司產品。歷史資料會計口徑 UNKNOWN，尚未驗證各列是否為獨立單季；此圖不代表 ABF 產品獲利。本次取得／快照取得為目前封存紀錄的取得時間，歷史首次取得時間未驗證。</p><svg id="finance-chart" viewBox="0 0 1200 270" role="img" aria-label="公司整體毛利率與營收年增率"></svg><div class="legend"><span><i class="dot" style="background:#087f8c"></i>公司毛利率（%）· COMPANY_TOTAL 代理</span><span><i class="dot" style="background:#2563b4"></i>公司營收年增率（%）· COMPANY_TOTAL 代理</span></div><details><summary>財務數值、會計口徑與可取得時間</summary><div id="finance-table" class="table-wrap"></div></details></section>
<section class="card"><h2>Driver → Revenue → GM → EPS</h2><p class="notice">NOT_CALIBRATED · 尚未校準；β = null。需先驗證 ABF 產品歸因、獨立單季口徑、精確 PIT 與各公司樣本外穩定性。</p><div id="bridge" class="bridge"></div></section>
<section class="card"><h2>營運傳導假說（尚未驗證）</h2><p class="notice">INFERRED · UNVALIDATED_HYPOTHESIS。此為待驗證的傳導機制，尚未建立因果或財務係數。</p><div id="mechanisms"></div></section>
<div class="grid"><section class="card"><h2>優先補足的研究資料</h2><div id="missing"></div><h3>下一步研究問題</h3><ol id="questions" class="research-list"></ol></section><section class="card"><h2>失效與撤回條件</h2><ol id="invalidations" class="research-list"></ol><details><summary>全部引用來源與證據 ID</summary><div id="sources" class="sources"></div></details></section></div>
<footer id="provenance"></footer></main>
<script id="company-survey-data" type="application/json">__REPORT__</script>
<script id="company-view-copy" type="application/json">__COPY__</script>
<script>
'use strict';
const report=JSON.parse(document.getElementById('company-survey-data').textContent), copy=JSON.parse(document.getElementById('company-view-copy').textContent);
const $=id=>document.getElementById(id), esc=v=>String(v??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=(v,d=3)=>v===null||v===undefined?'—':Number(v).toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d});
const label=m=>copy.metrics[m]||m, unit=u=>u==='percent'?'%':u==='percentage_points'?'百分點':u||'—';
const safeUrl=u=>{try{const p=new URL(u);return ['http:','https:'].includes(p.protocol)?p.href:null}catch{return null}};
function link(u,text){u=safeUrl(u);return u?'<a href="'+esc(u)+'" target="_blank" rel="noopener noreferrer">'+esc(text)+'</a>':esc(text)}
function table(headers,rows){return '<table><thead><tr>'+headers.map(h=>'<th>'+esc(h)+'</th>').join('')+'</tr></thead><tbody>'+rows.map(r=>'<tr>'+r.map(v=>'<td>'+v+'</td>').join('')+'</tr>').join('')+'</tbody></table>'}
function option(select,values,text){select.replaceChildren(...values.map(v=>{const o=document.createElement('option');o.value=v;o.textContent=text(v);return o}))}
function el(tag,attrs={},text){const n=document.createElementNS('http://www.w3.org/2000/svg',tag);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,v));if(text!==undefined)n.textContent=text;return n}
function bounds(vals){let lo=Math.min(...vals),hi=Math.max(...vals);const pad=(hi-lo||Math.abs(lo)*.1||1)*.12;return [lo-pad,hi+pad]}
function chart(svg,series,{scatter=false,xlabel='',ylabel='%',time=false,cadence=1}={}){
 svg.replaceChildren();const w=svg.viewBox.baseVal.width,h=svg.viewBox.baseVal.height,L=60,R=20,T=18,B=48;
 const all=series.flatMap(s=>s.points).filter(p=>p.x!==null&&p.y!==null&&Number.isFinite(p.x)&&Number.isFinite(p.y));
 if(!all.length){svg.append(el('text',{x:w/2,y:h/2,'text-anchor':'middle'},'UNAVAILABLE · 缺少可用觀察值'));return}
 const [xmin,xmax]=bounds(all.map(p=>p.x)),[ymin,ymax]=bounds(all.map(p=>p.y));const X=x=>L+(x-xmin)/(xmax-xmin)*(w-L-R),Y=y=>h-B-(y-ymin)/(ymax-ymin)*(h-T-B);
 for(let i=0;i<=4;i++){const y=ymin+(ymax-ymin)*i/4;svg.append(el('line',{x1:L,x2:w-R,y1:Y(y),y2:Y(y),stroke:'#e3eaf1'}),el('text',{x:L-9,y:Y(y)+4,'text-anchor':'end'},fmt(y,1)));const x=xmin+(xmax-xmin)*i/4;svg.append(el('text',{x:X(x),y:h-B+20,'text-anchor':'middle'},time?monthText(Math.round(x)):fmt(x,1)))}
 svg.append(el('line',{x1:L,x2:w-R,y1:h-B,y2:h-B,stroke:'#a6b7c8'}),el('text',{x:w/2,y:h-6,'text-anchor':'middle'},xlabel),el('text',{x:9,y:15},ylabel));
 for(const s of series){const points=s.points.filter(p=>p.x!==null&&p.y!==null&&Number.isFinite(p.x)&&Number.isFinite(p.y));if(!scatter){let previous=null;for(const p of points){if(previous&&(!time||p.x-previous.x===cadence))svg.append(el('line',{x1:X(previous.x),y1:Y(previous.y),x2:X(p.x),y2:Y(p.y),stroke:s.color,'stroke-width':2}));previous=p}}
 for(const p of points){const c=el('circle',{cx:X(p.x),cy:Y(p.y),r:p.is_oos?5:3.4,fill:p.is_oos?'#d98b29':s.color,opacity:.9,'data-period':p.period||'','data-x':p.rawx??p.x,'data-y':p.y,'data-oos':!!p.is_oos,'data-observation-id':p.id||''});c.append(el('title',{},p.tooltip||''));svg.append(c)}}
}
function monthNumber(p){const [y,m]=String(p).slice(0,7).split('-').map(Number);return y*12+m-1}function monthText(n){return Math.floor(n/12)+'-'+String(n%12+1).padStart(2,'0')}
function selectedCompany(){return report.companies.find(c=>c.company===$('company-select').value)}
function currentDetail(c){return Object.values(c.details).find(d=>d.scenario===$('scenario-select').value&&d.metric_id===$('metric-select').value&&d.feature_transform===$('feature-select').value&&d.target_transform===$('target-select').value)}
function render(){
 const c=selectedCompany(), ui=copy.companies[c.company], d=currentDetail(c);window.companySurveySelection={company:c,detail:d};
 document.querySelectorAll('.overview-card').forEach(n=>n.classList.toggle('active',n.dataset.company===c.company));
 $('company-title').textContent=c.name+' '+c.stock_id+' · ABF 研究判讀';
 $('brief').innerHTML=ui.brief.length?ui.brief.map(b=>'<p>'+esc(b.statement)+'<small class="cite">'+b.fact_ids.map(id=>link(ui.fact_links[id],id)).join(' · ')+'</small></p>').join(''):'<p>UNAVAILABLE · 缺少經核對的一手公司事實。</p>';
 $('scenario-status').innerHTML=['UPSIDE','DOWNSIDE'].map(s=>{const n=c.scenarios[s].eligibility_counts;return '<span class="badge">'+s+' · 可用 '+n.eligible+' / 佐證 '+n['support-only']+' / 未通過 '+n.reject+'</span>'}).join('')+'<span class="badge neutral">PIT 歷史公開時間未完整驗證</span>';
 $('assessment-note').textContent='公司整體與產業代理指標不足以識別 ABF 產品營收或毛利。財務傳導尚未校準；請合併檢視一手揭露、OOS 與各項門檻。';
 const obs=c.trend.observations.filter(o=>o.transform==='LEVEL'&&(o.metric_id===$('metric-select').value||o.metric_id==='abf_company_revenue_yoy::'+c.company));
 const groups=new Map();for(const o of obs){if(!groups.has(o.metric_id))groups.set(o.metric_id,{color:o.company==='INDUSTRY'?'#2563b4':'#087f8c',name:o.company==='INDUSTRY'?label(o.metric_id)+' · INDUSTRY_AGGREGATE 代理':c.name+'營收年增率 · COMPANY_TOTAL 代理',points:[]});groups.get(o.metric_id).points.push({x:monthNumber(o.period),y:o.signal_value,period:o.period,id:o.observation_id,tooltip:o.period+' | '+o.signal_value+'% | '+o.observation_id+' | '+(o.source_urls||[]).join(' ')})}for(const s of groups.values())s.points.sort((a,b)=>a.x-b.x);
 chart($('trend-chart'),[...groups.values()],{xlabel:'觀察月份（未位移）',ylabel:'年增率 %',time:true});$('trend-legend').innerHTML=[...groups.values()].map(s=>'<span><i class="dot" style="background:'+s.color+'"></i>'+esc(s.name)+'</span>').join('');
 const pts=(d?.sample_rows||[]).map(p=>({x:p.x,rawx:p.x,y:p.y,period:p.period,is_oos:(d.oos_folds||[]).some(f=>f.first_test_period<=p.period&&p.period<=f.last_test_period),tooltip:p.period+' | x='+p.x+' y='+p.y+' | '+(p.dependency_ids||[]).join(' | ')}));
 $('scatter-note').textContent=d?label(d.metric_id)+'（'+d.feature_transform+'） → '+c.name+'公司整體營收（'+d.target_transform+'）；候選領先 '+d.lag_months+' 個月，ABF 代理。':'UNAVAILABLE · 缺少選定比較';
 $('scatter-stats').innerHTML=[['Spearman ρ',fmt(d?.spearman)],['樣本 N',d?.sample_size??0],['Bootstrap CI','['+fmt(d?.bootstrap_ci_low,2)+', '+fmt(d?.bootstrap_ci_high,2)+']'],['FDR q',fmt(d?.fdr_q,4)]].map(([k,v])=>'<div class="stat"><small>'+esc(k)+'</small><b>'+esc(v)+'</b></div>').join('');
 chart($('scatter-chart'),[{color:'#96aabd',points:pts}],{scatter:true,xlabel:label(d?.metric_id||'')+' ('+unit(d?.feature_unit)+')',ylabel:'公司 '+unit(d?.target_unit)});
 $('validation-meta').innerHTML=table(['資格／資料狀態','不確定性','穩定性','來源與 PIT'],[[esc((d?.eligibility||'reject')+' / '+(d?.data_status||'UNAVAILABLE')),'p = '+fmt(d?.permutation_p,4)+'<br>q = '+fmt(d?.fdr_q,4),'OOS ρ = '+fmt(d?.oos_spearman)+'<br>OOS 符號 = '+fmt(d?.oos_sign_stability)+'<br>跨公司同向 = '+fmt(d?.company_sign_agreement),'PIT exact = '+esc(d?.pit_exact??false)+'<br>來源完整 = '+esc(d?.source_lineage_complete??false)+'<br>代理值 = '+esc(d?.is_proxy??true)]]);
 $('gates').innerHTML=Object.entries(d?.gates||{}).map(([k,v])=>'<span class="'+(v?'pass':'fail')+'">'+esc(k)+' '+(v?'✓':'✕')+'</span>').join('　')+'<br>'+esc((d?.reasons||[]).join(' · '));
 $('oos-table').innerHTML=table(['測試起月','測試迄月','訓練／測試 N','OOS ρ'],(d?.oos_folds||[]).map(f=>[esc(f.first_test_period),esc(f.last_test_period),esc(f.train_size+' / '+f.test_size),fmt(f.test_spearman)]));
 $('sample-detail').textContent=JSON.stringify({comparison_id:d?.comparison_id,source_scope:d?.source_scope,target_scope:d?.target_scope,sample_rows:d?.sample_rows||[],oos_folds:d?.oos_folds||[]},null,2);
 $('facts').innerHTML=c.primary_facts.length?table(['事實與數值','範圍／證據狀態','來源與四個訊號日期'],c.primary_facts.map(f=>['<b>'+esc(label(f.metric_id))+'</b><br>'+esc(f.value===null?'文字揭露':fmt(f.value,2)+' '+(f.unit||''))+'<small>'+esc(f.statement)+'</small>','<span class="badge neutral">'+esc(f.source_scope)+'</span><br>'+esc((copy.statuses[f.evidence_status]||f.evidence_status)+' · '+f.evidence_status)+'<br>'+esc(f.is_forward_looking?'前瞻展望，非實績':'觀察／歷史數值')+'<small>'+esc(f.data_status)+'</small>',link(ui.fact_links[f.fact_id],f.document+' · p.'+f.page)+'<small>'+esc(f.fact_id)+'<br>觀察 '+esc(f.observation_date)+'<br>發布 '+esc(f.release_date??'null · 未驗證')+'<br>可取得 '+esc(f.available_at)+'<br>訊號生成 '+esc(f.signal_generated_at)+'<br>本次取得／快照取得 '+esc(f.acquired_at)+'</small><details><summary>完整揭露與計算依賴</summary><pre>'+esc(JSON.stringify(f,null,2))+'</pre></details>'])):'<div class="empty">UNAVAILABLE · 缺少經核對的一手事實</div>';
 const fin=c.financial_context.rows;chart($('finance-chart'),[{color:'#087f8c',points:fin.map(f=>({x:monthNumber(f.report_date),period:f.report_date,id:f.evidence_id,y:f.gross_margin===null?null:f.gross_margin*100,tooltip:f.report_date+' · GM '+fmt(f.gross_margin*100,2)+'% · COMPANY_TOTAL · '+f.accounting_basis}))},{color:'#2563b4',points:fin.map(f=>({x:monthNumber(f.report_date),period:f.report_date,id:f.evidence_id,y:f.revenue_yoy===null?null:f.revenue_yoy*100,tooltip:f.report_date+' · 營收 YoY '+fmt(f.revenue_yoy*100,2)+'% · '+f.evidence_id}))}],{xlabel:'報告期末（公司整體；口徑 UNKNOWN）',ylabel:'%',time:true,cadence:3});
 $('finance-table').innerHTML=fin.length?table(['報告期','營收（新台幣元）','營收 YoY','毛利率','EPS（元／股）','口徑與時間'],fin.map(f=>[esc(f.report_date),fmt(f.revenue,0),f.revenue_yoy===null?'—':fmt(f.revenue_yoy*100,2)+'%',f.gross_margin===null?'—':fmt(f.gross_margin*100,2)+'%',fmt(f.eps,2),esc(f.accounting_basis)+'<small>'+esc(f.data_status)+' · 數值供應商 '+esc(f.fundamental_source)+'<br>觀察 '+esc(f.observation_date)+'<br>發布 '+esc(f.release_date??'null · 未驗證')+'<br>可取得 '+esc(f.available_at)+'<br>訊號生成 '+esc(f.signal_generated_at)+'<br>本次取得／快照取得 '+esc(f.acquired_at)+'<br>'+esc(f.evidence_id)+'<br>'+(f.source_urls||[]).map(u=>link(u,u)).join('<br>')+'</small>'])):'<p>UNAVAILABLE · 缺少財務歷史</p>';
 $('bridge').innerHTML=c.financial_bridge.stages.map(s=>'<div><h3>'+esc(s.stage)+'</h3><span class="badge">'+esc(s.status)+'</span><p>β = null<br>尚未校準</p></div>').join('');
 $('mechanisms').innerHTML=(c.operating_mechanism||[]).map(m=>'<p>'+esc(m.statement_zh||m.statement)+'<small>'+esc(m.evidence_status)+' · '+esc(m.status)+'<br>證據 ID：'+(m.evidence_ids||[]).map(id=>link(ui.fact_links[id],id)).join(' · ')+'</small></p>').join('');
 $('missing').innerHTML=table(['ABF 產品輸入','狀態／已核對值'],c.missing_inputs.map(m=>[esc(label(m.metric_id)),esc(m.value===null?'缺少 · '+m.data_status:fmt(m.value,2)+' '+(m.unit||'')+' · '+m.data_status)+'<small>'+esc((m.evidence_ids||[]).join(' · '))+'</small>']));
 const questions=['公司產品層級的訂單、客戶庫存、實際稼動率、售價與產品組合，是否有可持續追蹤的一手揭露？','上下行情境是否各自通過固定時序 OOS、信賴區間、多重比較與跨公司檢驗？','可否取得獨立單季、精確公開時間的 ABF 營收與毛利，建立財務傳導？'];
 $('questions').innerHTML=c.research_questions.map((q,i)=>'<li>'+esc(questions[i]||q.question)+'<small>'+esc(q.evidence_status)+'</small></li>').join('');
 const conditions=['來源修訂若改變相關方向、OOS 穩定性或不確定性門檻，需撤回原判讀。','欠缺產品歸因與精確 PIT 時，不將產業或公司整體相關性轉成 ABF 預測。','若無法核對會計口徑、發布時間或取得來源鏈，撤回財務歸因。'];
 $('invalidations').innerHTML=c.invalidation_conditions.map((r,i)=>'<li>'+esc(conditions[i]||r.condition)+'</li>').join('');
 $('sources').innerHTML=c.sources.map(s=>'<p>'+link(s.source_url,s.source_url)+'<small>'+esc(s.evidence_ids.join(' · '))+'</small></p>').join('');
}
option($('company-select'),report.companies.map(c=>c.company),v=>{const c=report.companies.find(x=>x.company===v);return c.name+' '+c.stock_id});
function syncMetrics(){const previous=$('metric-select').value,options=selectedCompany().scenarios[$('scenario-select').value].options;option($('metric-select'),[...new Set(options.map(o=>o.metric_id))],label);if([...$('metric-select').options].some(o=>o.value===previous))$('metric-select').value=previous}
$('company-select').addEventListener('change',()=>{syncMetrics();render()});$('scenario-select').addEventListener('change',()=>{syncMetrics();render()});['metric-select','feature-select','target-select'].forEach(id=>$(id).addEventListener('change',render));
document.querySelectorAll('.overview-card').forEach(b=>b.addEventListener('click',()=>{$('company-select').value=b.dataset.company;syncMetrics();render()}));
$('report-date').textContent='研究知識截止 '+report.as_of+' · 報告生成 '+report.generated_at;
$('provenance').textContent='ABFCompanySurveyV1 · '+report.owner+' · 統計權威 '+report.policy.statistical_authority+' · 版本 '+(report.code_revision||report.audit_metadata.code_revision||'未提供')+' · 所有圖表使用封存證據，無外部連線。';
syncMetrics();render();
</script></body></html>'''
