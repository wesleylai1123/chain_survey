import {
  AGGREGATIONS, BASE_TRANSFORM, CATEGORIES, COLORS, DEFAULT_IDS, FREQUENCIES, MAX_SERIES, TRANSFORMS,
  analysisPayload, asNumber, chartPayload, initialSettings, isFraction, latestPoint, measure, sampleCsv,
  sampleFields, seriesName, sourceName, timingText, warningText, yearsEarlier,
} from './model.js';
import { drawPlot, lagsSpec, observePlots, rollingSpec, scatterSpec, trendSpec, zoomPlot } from './plots.js';
import { byId, element, icon, icons, request, setOptions, status, textButton } from './ui.js';

const catalogItems = byId('catalog-items');
const search = byId('catalog-search');
const category = byId('catalog-category');
const start = byId('start-date');
const end = byId('end-date');
const selected = byId('selected-series');
const mainPlot = byId('main-plot');
const chartStatus = byId('chart-status');
const form = byId('analysis-form');
const lag = byId('lag');
const windowSize = byId('window');
const strict = byId('strict');
const pairSelect = { x: byId('pair-x'), y: byId('pair-y') };
const pairTransform = { x: byId('pair-x-transform'), y: byId('pair-y-transform') };
const chartZoom = { out: byId('zoom-out'), in: byId('zoom-in'), reset: byId('zoom-reset') };
const tabs = [...document.querySelectorAll('[role="tab"]')];
const details = {
  rolling: { plot: byId('rolling-plot'), status: byId('rolling-status') },
  scatter: { plot: byId('scatter-plot'), status: byId('scatter-status') },
  lags: { plot: byId('lag-plot'), status: byId('lags-status') },
  samples: { status: byId('samples-status') },
};
const catalog = new Map();
const compactNumber = new Intl.NumberFormat('zh-Hant-TW', { maximumFractionDigits: 2 });
const percentage = new Intl.NumberFormat('zh-Hant-TW', { style: 'percent', maximumFractionDigits: 8, useGrouping: false });
const literalTransforms = Object.entries(TRANSFORMS);
const coefficient = value => {
  const number = asNumber(value);
  return number === null ? '—' : (Object.is(number, -0) ? 0 : number).toFixed(3);
};
const signed = number => number > 0 ? '+' + number : String(number);
const isoDay = /^\d{4}-\d{2}-\d{2}$/;
let settings = initialSettings([], BASE_TRANSFORM);
let catalogReady = false;
let catalogError = '';
let chartRequest;
let pairRequest;
let pairResult;
let pairStatus = '正在載入資料庫…';
let activeDetail = 'rolling';
let detailRevision = 0;
let samplePage = 0;
let toastTimer;

function notify(message) {
  const toast = byId('toast');
  clearTimeout(toastTimer);
  status(toast, message);
  toastTimer = setTimeout(() => status(toast, ''), 4000);
}

const colorFor = id => COLORS[Math.max(0, settings.series.findIndex(item => item.id === id)) % COLORS.length];

function displayCatalog() {
  const active = document.activeElement?.dataset.catalogId;
  const scroll = catalogItems.scrollTop;
  const query = search.value.trim().toLocaleLowerCase();
  const rows = [...catalog.values()].filter(item => {
    const searchable = [item.id, item.name, seriesName(item), item.source, sourceName(item), item.category, CATEGORIES[item.category]];
    return (!category.value || item.category === category.value) && searchable.join(' ').toLocaleLowerCase().includes(query);
  });
  catalogItems.replaceChildren();
  catalogItems.setAttribute('aria-busy', String(!catalogReady && !catalogError));
  byId('catalog-count').textContent = catalogReady ? query || category.value ? rows.length + ' / ' + catalog.size : catalog.size : '—';
  byId('workspace-summary').textContent = catalogReady ? '本機歷史資料 · ' + catalog.size + ' 條序列' : '本機歷史資料';

  if (!rows.length) {
    const message = !catalogReady ? catalogError || '正在載入資料庫…'
      : catalog.size ? '找不到符合的序列。' : '資料庫尚無序列。可匯入 CSV。';
    const empty = element('p', message, 'library-message');
    empty.setAttribute('role', 'status');
    catalogItems.append(empty);
    if (catalogError) {
      const retry = textButton('重新載入', 'button library-retry');
      retry.addEventListener('click', () => void loadCatalog());
      catalogItems.append(retry);
    }
    return;
  }

  const fragment = document.createDocumentFragment();
  let focusTarget;
  for (const item of rows) {
    const name = seriesName(item);
    const source = sourceName(item);
    const point = latestPoint(item);
    const value = asNumber(point.value);
    const formatted = value === null ? '—' : compactNumber.format(value);
    const unit = item.unit === '%' ? '%' : '';
    const enabled = settings.series.some(series => series.id === item.id);
    const button = textButton(undefined, 'library-item');
    button.dataset.catalogId = item.id;
    button.setAttribute('aria-pressed', String(enabled));
    button.style.setProperty('--series-color', colorFor(item.id));
    const meta = [source, CATEGORIES[item.category] ?? item.category, FREQUENCIES[item.frequency] ? FREQUENCIES[item.frequency] + '頻' : item.frequency, item.unit, point.date, point.value, item.source_url];
    button.title = [name, ...meta.filter(part => part != null && part !== '')].join('\n');
    const title = element('span', undefined, 'library-item-name');
    title.append(icon(enabled ? 'check' : 'plus'), element('span', name, 'item-title'));
    button.append(title, element('span', formatted + (value === null ? '' : unit), 'item-value'),
      element('span', source, 'item-source'), element('span', point.date || '—', 'item-date'));
    button.addEventListener('click', () => toggleSeries(item.id));
    if (active === item.id) focusTarget = button;
    fragment.append(button);
  }
  catalogItems.append(fragment);
  catalogItems.scrollTop = scroll;
  focusTarget?.focus({ preventScroll: true });
  icons();
}

function updateCatalogOptions() {
  const previous = category.value;
  const categories = new Set([...catalog.values()].map(item => item.category).filter(Boolean));
  const ordered = [...Object.keys(CATEGORIES).filter(key => categories.delete(key)), ...categories];
  setOptions(category, [['', '全部分類'], ...ordered.map(key => [key, CATEGORIES[key] ?? key])]);
  category.value = ordered.includes(previous) ? previous : '';
  const entries = [['', '選擇序列'], ...[...catalog.values()].map(item => [item.id, seriesName(item)])];
  for (const select of Object.values(pairSelect)) setOptions(select, entries);
}

function setCatalog(items) {
  const incoming = new Map(items.map(item => [item.id, item]));
  const first = !catalogReady;
  catalog.clear();
  for (const id of DEFAULT_IDS) if (incoming.has(id)) catalog.set(id, incoming.get(id));
  for (const [id, item] of incoming) catalog.set(id, item);
  catalogReady = true;
  catalogError = '';
  const defaults = initialSettings([...catalog.values()], BASE_TRANSFORM);
  if (first) {
    settings = defaults;
  } else {
    settings.series = settings.series.filter(item => catalog.has(item.id));
    if (!catalog.has(settings.x)) settings.x = defaults.x;
    if (!catalog.has(settings.y)) settings.y = [defaults.y, defaults.x].find(id => id !== settings.x) ?? '';
  }
  updateCatalogOptions();
  syncControls();
  displayCatalog();
  displaySeries();
  void updateChart();
  void updateAnalysis();
}

async function loadCatalog(imported) {
  catalogError = '';
  if (!catalogReady) displayCatalog();
  try {
    const data = await request('/api/catalog');
    setCatalog(data.series);
  } catch (error) {
    catalogError = error.message;
    if (imported?.length) {
      const merged = new Map(catalog);
      for (const item of imported) merged.set(item.id, item);
      setCatalog([...merged.values()]);
      notify('已匯入序列，資料庫重新載入失敗。');
    } else if (!catalogReady) {
      displayCatalog();
      showChartState('資料庫載入失敗。', 'error');
      showPairState('資料庫載入失敗。', true);
    }
  }
}

function toggleSeries(id) {
  if (settings.series.some(item => item.id === id)) {
    settings.series = settings.series.filter(item => item.id !== id);
  } else {
    if (settings.series.length >= MAX_SERIES) {
      notify('單一圖表最多疊加 12 條序列。');
      return;
    }
    settings.series = [...settings.series, { id, transform: BASE_TRANSFORM }];
  }
  displayCatalog();
  displaySeries();
  syncControls();
  void updateChart();
  void updateAnalysis();
}

function displaySeries() {
  const nodes = settings.series.map(({ id, transform }) => {
    const name = seriesName(catalog.get(id));
    const row = element('div', undefined, 'series-control');
    row.style.setProperty('--series-color', colorFor(id));
    const dot = element('span', undefined, 'series-dot');
    dot.setAttribute('aria-hidden', 'true');
    const title = element('span', name, 'series-name');
    title.title = name;
    const select = element('select');
    select.setAttribute('aria-label', name + '的疊圖轉換');
    setOptions(select, literalTransforms);
    select.value = transform;
    select.addEventListener('change', () => {
      settings.series = settings.series.map(item => item.id === id ? { id, transform: select.value } : item);
      syncPairTransforms();
      void updateChart();
      void updateAnalysis();
    });
    const remove = textButton(undefined, 'icon-button series-remove');
    remove.setAttribute('aria-label', '從圖表移除 ' + name);
    remove.title = '從圖表移除 ' + name;
    remove.append(icon('x'));
    remove.addEventListener('click', () => {
      const index = settings.series.findIndex(item => item.id === id);
      toggleSeries(id);
      const next = selected.children[Math.min(index, selected.children.length - 1)]?.querySelector('button');
      (next ?? search).focus({ preventScroll: true });
    });
    row.append(dot, title, select, remove);
    return row;
  });
  selected.replaceChildren(...nodes);
  icons();
}

function latestDate() {
  return settings.series.map(({ id }) => catalog.get(id)?.last).filter(date => isoDay.test(date)).sort().at(-1)
    ?? [...catalog.values()].map(item => item.last).filter(date => isoDay.test(date)).sort().at(-1);
}

function syncPairTransforms() {
  for (const side of ['x', 'y']) {
    const transform = settings.series.find(item => item.id === settings[side])?.transform;
    const label = transform ? '沿用疊圖 · ' + TRANSFORMS[transform] : '預設 · 原值';
    const select = pairTransform[side];
    if (!select.options.length) setOptions(select, [['', label], ...literalTransforms]);
    select.options[0].textContent = label;
    select.value = settings[side + 'Transform'];
    select.disabled = !settings[side];
  }
}

function syncControls() {
  const latest = latestDate();
  for (const button of document.querySelectorAll('[data-frequency]')) {
    button.setAttribute('aria-pressed', String(button.dataset.frequency === settings.frequency));
  }
  for (const button of document.querySelectorAll('[data-years]')) {
    const years = button.dataset.years;
    const all = years === 'all';
    button.disabled = !all && !latest;
    const active = all ? !settings.start && !settings.end
      : Boolean(latest && settings.end === latest && settings.start === yearsEarlier(latest, Number(years)));
    button.setAttribute('aria-pressed', String(active));
  }
  byId('aggregation').value = settings.aggregation;
  start.value = settings.start;
  end.value = settings.end;
  byId('clear-dates').hidden = !settings.start && !settings.end;
  byId('lag-unit').textContent = '（' + FREQUENCIES[settings.frequency] + '）';
  for (const side of ['x', 'y']) {
    pairSelect[side].value = settings[side];
    pairSelect[side].disabled = !catalog.size;
  }
  lag.value = settings.lag;
  windowSize.value = settings.window;
  strict.checked = settings.strict;
  syncPairTransforms();
}

function showChartState(message, state = '') {
  mainPlot.parentElement.setAttribute('aria-busy', String(state === 'loading'));
  mainPlot.classList.toggle('is-ready', !message);
  for (const button of Object.values(chartZoom)) button.disabled = Boolean(message);
  chartStatus.replaceChildren();
  chartStatus.classList.toggle('is-error', state === 'error');
  chartStatus.hidden = !message;
  if (state === 'loading') chartStatus.append(icon('loader-circle', 'spinner'));
  if (message) chartStatus.append(element('span', message));
  if (state === 'error' && catalogReady && !(settings.start && settings.end && settings.start > settings.end)) {
    const retry = textButton('重試', 'button button-quiet');
    retry.addEventListener('click', () => void updateChart());
    chartStatus.append(retry);
  }
  icons();
}

const invalidRange = () => settings.start && settings.end && settings.start > settings.end;

async function updateChart() {
  chartRequest?.abort();
  byId('chart-coverage').textContent = '';
  start.setAttribute('aria-invalid', String(Boolean(invalidRange())));
  end.setAttribute('aria-invalid', String(Boolean(invalidRange())));
  if (invalidRange()) return showChartState('起始日期須早於或等於結束日期。', 'error');
  if (!settings.series.length) return showChartState('從資料庫選取序列，即可在這裡疊圖。');
  const controller = new AbortController();
  chartRequest = controller;
  const payload = chartPayload(settings);
  showChartState('正在載入序列…', 'loading');
  try {
    const data = await request('/api/chart', { body: payload, signal: controller.signal });
    if (controller.signal.aborted) return;
    const spec = trendSpec(data.series, colorFor, payload, mainPlot.clientWidth);
    const count = spec.traces.length;
    const coarser = data.series.some(item => ['D', 'M', 'Q'].indexOf(item.frequency) > ['D', 'M', 'Q'].indexOf(payload.frequency));
    if (!count) return showChartState(coarser ? '所選頻率可能高於序列原始頻率。請改用較低頻率或更換序列。' : '此日期、頻率與轉換組合沒有資料。');
    await drawPlot(mainPlot, spec);
    if (controller.signal.aborted) return;
    const ranges = spec.traces.map(trace => trace.x.filter((_, index) => trace.y[index] !== null));
    const first = ranges.map(dates => dates[0]).sort()[0];
    const last = ranges.map(dates => dates.at(-1)).sort().at(-1);
    byId('chart-coverage').textContent = first + ' 至 ' + last + ' · ' + count + ' 條序列' +
      (count < payload.series.length ? '（' + (payload.series.length - count) + ' 條無資料）' : '') +
      ' · ' + FREQUENCIES[payload.frequency] + '頻 / ' + AGGREGATIONS[payload.aggregation];
    showChartState('');
  } catch (error) {
    if (!controller.signal.aborted) showChartState(error.message, 'error');
  }
}

function showPairState(message, error = false, loading = false) {
  pairResult = null;
  pairStatus = message;
  byId('analysis-results').setAttribute('aria-busy', String(loading));
  byId('run-analysis').disabled = loading || !catalog.size;
  for (const id of ['stat-pearson', 'stat-spearman', 'stat-n']) byId(id).textContent = '—';
  for (const id of ['result-context', 'details-context']) byId(id).textContent = '';
  const warnings = byId('analysis-warnings');
  warnings.replaceChildren();
  warnings.hidden = true;
  status(byId('analysis-status'), message, error);
  void displayDetail();
}

async function updateAnalysis({ readInputs = false } = {}) {
  pairRequest?.abort();
  if (readInputs || !form.checkValidity()) {
    const lagValid = lag.validity.valid && Number.isInteger(lag.valueAsNumber);
    const windowValid = windowSize.validity.valid && Number.isInteger(windowSize.valueAsNumber);
    if (!lagValid || !windowValid) return showPairState(!lagValid ? '請輸入 −60 至 +60 的整數期差。' : '請輸入 3 至 200 期的滾動視窗。', true);
    settings.lag = lag.valueAsNumber;
    settings.window = windowSize.valueAsNumber;
  }
  if (invalidRange()) return showPairState('請先修正日期範圍。', true);
  if (!settings.x || !settings.y || settings.x === settings.y) return showPairState('請選擇兩條不同的序列。');
  const controller = new AbortController();
  pairRequest = controller;
  const payload = analysisPayload(settings, BASE_TRANSFORM);
  showPairState('正在計算相關性…', false, true);
  try {
    const result = await request('/api/analyze', { body: payload, signal: controller.signal });
    if (controller.signal.aborted) return;
    pairResult = { ...result, payload };
    samplePage = 0;
    byId('analysis-results').setAttribute('aria-busy', 'false');
    byId('run-analysis').disabled = false;
    byId('stat-pearson').textContent = coefficient(result.pearson);
    byId('stat-spearman').textContent = coefficient(result.spearman);
    byId('stat-n').textContent = result.n;
    const context = payload.lag ? signed(payload.lag) + ' ' + FREQUENCIES[payload.frequency] : '同期';
    byId('result-context').textContent = context;
    byId('details-context').textContent = context + ' · ' + result.n + ' 組樣本';
    status(byId('analysis-status'), result.n && result.pearson == null && result.spearman == null ? '樣本不足或數值無變異，無法計算係數。' : '');
    const warnings = byId('analysis-warnings');
    warnings.replaceChildren(...result.warnings.map(message => element('li', warningText(message))));
    warnings.hidden = !result.warnings.length;
    void displayDetail();
  } catch (error) {
    if (!controller.signal.aborted) showPairState(error.message, true);
  }
}

function selectLag(value) {
  if (!Number.isInteger(value) || value < -60 || value > 60) return;
  lag.value = value;
  void updateAnalysis({ readInputs: true });
  lag.focus({ preventScroll: true });
}

function renderLagRows(lags, selectedLag) {
  const nodes = lags.map(row => {
    const tr = element('tr');
    if (row.lag === selectedLag) tr.className = 'active-lag';
    const first = element('td');
    const button = textButton(signed(row.lag), 'lag-select');
    button.setAttribute('aria-label', '套用期差 ' + signed(row.lag));
    button.addEventListener('click', () => selectLag(row.lag));
    first.append(button);
    tr.append(first, element('td', coefficient(row.pearson)), element('td', coefficient(row.spearman)), element('td', row.n));
    return tr;
  });
  byId('lag-rows').replaceChildren(...nodes);
  byId('lag-table-wrap').hidden = !nodes.length;
}

function sampleCell(key, sample, payload) {
  const td = element('td');
  const value = sample[key];
  if (key.endsWith('_available') && sample[key + '_from'] && sample[key + '_until']) {
    const from = sample[key + '_from'];
    const until = sample[key + '_until'];
    td.className = 'availability-range';
    td.append(element('span', from), element('span', '至 ' + until));
    return td;
  }
  if (value == null || value === '') {
    td.textContent = key.endsWith('_available') ? '未記錄' : '—';
    return td;
  }
  if (key.endsWith('_source_url') || key.endsWith('_content_hash')) {
    const span = element('span', value, 'provenance-url');
    span.title = value;
    td.append(span);
    return td;
  }
  const fraction = (key === 'x' || key === 'y') && isFraction(payload[key + '_transform']);
  td.textContent = fraction ? percentage.format(value) : key.endsWith('_timing') ? timingText(value) : value;
  if (fraction || key.endsWith('_timing')) td.title = String(value);
  return td;
}

function displaySamples(result) {
  const { samples, payload } = result;
  const pageSize = 100;
  const pageCount = Math.ceil(samples.length / pageSize);
  const caption = byId('samples-caption');
  byId('export-samples').disabled = !samples.length;
  byId('sample-table-wrap').hidden = !samples.length;
  status(details.samples.status, samples.length ? '' : '此期差沒有可對齊的樣本。');
  const activeFields = sampleFields.filter(([key], index) => index < 6 ||
    (!/_available_(from|until)$/.test(key) && samples.some(row => row[key] != null && row[key] !== '')));
  const xMeta = catalog.get(payload.x);
  const yMeta = catalog.get(payload.y);
  const head = element('tr');
  for (const [key, label] of activeFields) {
    const side = key === 'x' ? xMeta : key === 'y' ? yMeta : null;
    const unit = side ? measure(side.unit, payload[key + '_transform']).unit : '';
    const th = element('th', label + (unit ? '（' + unit + '）' : ''));
    if (side) th.title = seriesName(side);
    th.scope = 'col';
    head.append(th);
  }
  byId('sample-head').replaceChildren(head);
  const offset = samplePage * pageSize;
  const nodes = samples.slice(offset, offset + pageSize).map(sample => {
    const tr = element('tr');
    tr.append(...activeFields.map(([key]) => sampleCell(key, sample, payload)));
    return tr;
  });
  byId('sample-rows').replaceChildren(...nodes);
  caption.replaceChildren(element('span', seriesName(xMeta) + ' × ' + seriesName(yMeta) + ' · ' + samples.length + ' 組'));
  if (pageCount > 1) {
    const previous = textButton('上一頁', 'button button-quiet');
    const next = textButton('下一頁', 'button button-quiet');
    previous.disabled = samplePage === 0;
    next.disabled = samplePage >= pageCount - 1;
    for (const [button, step] of [[previous, -1], [next, 1]]) {
      button.addEventListener('click', () => {
        samplePage += step;
        displaySamples(result);
        byId('sample-table-wrap').scrollTop = 0;
        (caption.querySelector(step < 0 ? 'button' : 'button:last-child') ?? caption).focus();
      });
    }
    caption.append(previous, element('span', (samplePage + 1) + ' / ' + pageCount), next);
  }
}

async function displayDetail() {
  const key = activeDetail;
  const current = ++detailRevision;
  const { plot, status: label } = details[key];
  if (!pairResult) {
    plot?.classList.remove('is-ready');
    if (key === 'samples') {
      byId('sample-table-wrap').hidden = true;
      byId('export-samples').disabled = true;
      byId('samples-caption').textContent = '分析使用的對齊樣本';
    }
    if (key === 'lags') byId('lag-table-wrap').hidden = true;
    status(label, pairStatus);
    return;
  }
  const result = pairResult;
  const { payload } = result;
  if (key === 'samples') return displaySamples(result);
  let spec;
  let empty;
  const hasCoefficient = rows => rows.some(row => asNumber(row.pearson) !== null || asNumber(row.spearman) !== null);
  if (key === 'scatter') {
    const xMeta = catalog.get(payload.x);
    const yMeta = catalog.get(payload.y);
    byId('scatter-caption').textContent = seriesName(xMeta) + ' × ' + seriesName(yMeta) + ' · ' + result.samples.length + ' 組';
    if (result.samples.length) spec = scatterSpec(result.samples, xMeta, yMeta, payload.x_transform, payload.y_transform);
    empty = '此期差沒有可繪製的對齊樣本。';
  } else if (key === 'rolling') {
    byId('rolling-caption').textContent = payload.window + ' 組樣本滾動視窗 · 以 Y 觀測期標示';
    if (hasCoefficient(result.rolling)) spec = rollingSpec(result.rolling, plot.clientWidth);
    empty = '目前樣本不足或視窗內數值無變異。';
  } else {
    renderLagRows(result.lags, payload.lag);
    if (hasCoefficient(result.lags)) spec = lagsSpec(result.lags, payload.lag);
    empty = '掃描範圍內沒有可計算的相關係數。';
  }
  plot.classList.remove('is-ready');
  status(label, spec ? '正在繪製圖表…' : empty);
  if (!spec) return;
  try {
    await drawPlot(plot, spec);
    if (current !== detailRevision) return;
    plot.classList.add('is-ready');
    status(label, '');
    if (key === 'lags' && !plot.dataset.clickBound) {
      plot.on('plotly_click', event => selectLag(Number(event.points[0]?.x)));
      plot.dataset.clickBound = 'true';
    }
  } catch (error) {
    if (current === detailRevision) status(label, error.message, true);
  }
}

function restoreGroup(group) {
  if (!catalogReady) throw new Error('請先載入資料庫，再套用群組。');
  if (!group || !Array.isArray(group.series)) throw new Error('群組設定格式不正確。');
  const defaults = initialSettings([...catalog.values()], BASE_TRANSFORM);
  const series = new Map();
  for (const item of group.series) {
    if (catalog.has(item?.id)) series.set(item.id, { id: item.id, transform: Object.hasOwn(TRANSFORMS, item.transform) ? item.transform : BASE_TRANSFORM });
  }
  settings = {
    series: [...series.values()].slice(0, MAX_SERIES),
    frequency: Object.hasOwn(FREQUENCIES, group.frequency) ? group.frequency : defaults.frequency,
    aggregation: Object.hasOwn(AGGREGATIONS, group.aggregation) ? group.aggregation : defaults.aggregation,
    start: isoDay.test(group.start) ? group.start : '',
    end: isoDay.test(group.end) ? group.end : '',
    x: catalog.has(group.x) ? group.x : defaults.x,
    y: catalog.has(group.y) ? group.y : defaults.y,
    xTransform: Object.hasOwn(TRANSFORMS, group.xTransform) ? group.xTransform : '',
    yTransform: Object.hasOwn(TRANSFORMS, group.yTransform) ? group.yTransform : '',
    lag: Number.isInteger(group.lag) && group.lag >= -60 && group.lag <= 60 ? group.lag : defaults.lag,
    window: Number.isInteger(group.window) && group.window >= 3 && group.window <= 200 ? group.window : defaults.window,
    strict: group.strict === true,
  };
  syncControls();
  displayCatalog();
  displaySeries();
  void updateChart();
  void updateAnalysis();
  return group.series.length - series.size;
}

function updateSharedControls() {
  syncControls();
  void updateChart();
  void updateAnalysis();
}

function setTab(tab) {
  activeDetail = tab.id.replace('tab-', '');
  for (const button of tabs) {
    const active = button === tab;
    button.tabIndex = active ? 0 : -1;
    button.setAttribute('aria-selected', String(active));
    byId(button.getAttribute('aria-controls')).hidden = !active;
  }
  void displayDetail();
}

function startApp() {
  icons();
  observePlots([mainPlot, ...Object.values(details).flatMap(detail => detail.plot ? [detail.plot] : [])]);
  syncControls();
  search.addEventListener('input', displayCatalog);
  category.addEventListener('change', displayCatalog);
  byId('frequency').addEventListener('click', event => {
    const frequency = event.target.closest('[data-frequency]')?.dataset.frequency;
    if (!frequency || frequency === settings.frequency) return;
    settings.frequency = frequency;
    updateSharedControls();
  });
  byId('aggregation').addEventListener('change', event => {
    settings.aggregation = event.target.value;
    updateSharedControls();
  });
  for (const input of [start, end]) input.addEventListener('change', () => {
    settings.start = start.value;
    settings.end = end.value;
    updateSharedControls();
  });
  function setDates(years) {
    const latest = latestDate();
    if (years !== 'all' && !latest) return;
    settings.start = years === 'all' ? '' : yearsEarlier(latest, Number(years));
    settings.end = years === 'all' ? '' : latest;
    updateSharedControls();
  }
  byId('date-presets').addEventListener('click', event => {
    const years = event.target.closest('[data-years]')?.dataset.years;
    if (years) setDates(years);
  });
  byId('clear-dates').addEventListener('click', () => {
    setDates('all');
    start.focus();
  });
  for (const [action, button] of Object.entries(chartZoom)) {
    button.addEventListener('click', () => zoomPlot(mainPlot, action).catch(() => notify('圖表縮放失敗。')));
  }
  for (const side of ['x', 'y']) {
    pairSelect[side].addEventListener('change', () => {
      settings[side] = pairSelect[side].value;
      syncPairTransforms();
      void updateAnalysis({ readInputs: true });
    });
    pairTransform[side].addEventListener('change', () => {
      settings[side + 'Transform'] = pairTransform[side].value;
      void updateAnalysis({ readInputs: true });
    });
  }
  for (const input of [lag, windowSize]) input.addEventListener('change', () => void updateAnalysis({ readInputs: true }));
  strict.addEventListener('change', () => {
    settings.strict = strict.checked;
    void updateAnalysis({ readInputs: true });
  });
  form.addEventListener('submit', event => {
    event.preventDefault();
    void updateAnalysis({ readInputs: true });
  });
  for (const tab of tabs) {
    tab.addEventListener('click', () => setTab(tab));
    tab.addEventListener('keydown', event => {
      const index = tabs.indexOf(tab);
      const next = {
        ArrowLeft: tabs[(index - 1 + tabs.length) % tabs.length],
        ArrowRight: tabs[(index + 1) % tabs.length],
        Home: tabs[0], End: tabs.at(-1),
      }[event.key];
      if (!next) return;
      event.preventDefault();
      setTab(next);
      next.focus();
    });
  }
  byId('export-samples').addEventListener('click', () => {
    if (!pairResult?.samples.length) return;
    const url = URL.createObjectURL(new Blob([sampleCsv(pairResult.samples)], { type: 'text/csv;charset=utf-8' }));
    const link = element('a');
    link.href = url;
    link.download = '研究樣本_' + pairResult.payload.frequency + '_lag' + pairResult.payload.lag + '.csv';
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  byId('run-analysis').disabled = true;
  void loadCatalog();
  import('./dialogs.js').then(({ setupDialogs }) => setupDialogs({
    getSettings: () => structuredClone(settings), restoreGroup, notify,
    onImport: items => void loadCatalog(items),
  })).catch(() => {
    for (const id of ['open-import', 'open-groups', 'save-group']) {
      byId(id).addEventListener('click', () => notify('本機對話框模組無法載入。'));
    }
  });
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', startApp, { once: true });
else startApp();
