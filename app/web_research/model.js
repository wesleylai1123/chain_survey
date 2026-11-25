export const DEFAULT_IDS = ['pcb_revenue_yoy', 'abf_company_revenue_yoy::3037.TW'];
export const FREQUENCIES = { D: '日', M: '月', Q: '季' };
export const AGGREGATIONS = { last: '期末值', mean: '平均', sum: '加總' };
export const TRANSFORMS = { level: '原值', diff: '期差', return: '期變動率', yoy: '年增率' };
export const BASE_TRANSFORM = 'level';
export const MAX_SERIES = 12;
export const CATEGORIES = {
  'Industry / Macro': '產業與總體', 'Company Revenue': '公司營收', 'Company Financials': '公司財報',
  Market: '市場行情', Currency: '匯率', Imported: 'CSV 匯入',
};
export const COLORS = ['#087f65', '#c96829', '#355ac9', '#8e52a1', '#b54269', '#2c7795'];
export const sampleFields = [
  ['x_date', 'X 觀測日期'], ['y_date', 'Y 觀測日期'],
  ['x', 'X 數值'], ['y', 'Y 數值'], ['x_available', 'X 可用時間'],
  ['y_available', 'Y 可用時間'], ['x_timing', 'X 時間依據'], ['y_timing', 'Y 時間依據'],
  ['x_available_from', 'X 最早可用時間'], ['x_available_until', 'X 最晚可用時間'],
  ['y_available_from', 'Y 最早可用時間'], ['y_available_until', 'Y 最晚可用時間'],
  ['x_source_url', 'X 來源網址'], ['y_source_url', 'Y 來源網址'],
  ['x_source', 'X 資料來源'], ['x_filename', 'X 檔名'], ['x_column', 'X 欄名'], ['x_content_hash', 'X 內容雜湊'],
  ['y_source', 'Y 資料來源'], ['y_filename', 'Y 檔名'], ['y_column', 'Y 欄名'], ['y_content_hash', 'Y 內容雜湊'],
];

export function initialSettings(catalog, baseTransform) {
  const existing = new Set(catalog.map(({ id }) => id));
  const ids = [...new Set([...DEFAULT_IDS.filter(id => existing.has(id)), ...existing])].slice(0, 2);
  return {
    series: ids.map(id => ({ id, transform: baseTransform })),
    frequency: 'M', aggregation: 'last', start: '', end: '',
    x: ids[0] ?? '', y: ids[1] ?? '', xTransform: '', yTransform: '', lag: 1, window: 12, strict: false,
  };
}

export function chartPayload({ series, frequency, aggregation, start, end }) {
  return { series, frequency, aggregation, start: start || null, end: end || null };
}

export function analysisPayload(settings, baseTransform) {
  const { frequency, aggregation, start, end } = chartPayload(settings);
  const { x, y, xTransform, yTransform, lag, window, strict, series } = settings;
  const transformFor = id => series.find(item => item.id === id)?.transform ?? baseTransform;
  return {
    x, y, frequency, aggregation, x_transform: xTransform || transformFor(x), y_transform: yTransform || transformFor(y),
    start, end, lag, window, strict,
  };
}

export function asNumber(value) {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (typeof value !== 'string' || !value.trim()) return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

export function latestPoint({ latest, last }) {
  if (latest && typeof latest === 'object') {
    return { date: latest.date ?? latest.period ?? last, value: latest.value };
  }
  return { date: last, value: latest };
}

const dateHeaders = ['date', 'datetime', 'timestamp', 'period', 'month', '日期', '時間', '年月', '期間'];
const availableHeaders = ['available', 'available_at', 'availability', 'published_at', 'release_date', '可用日期', '發布日期', '公布日期'];

export function previewValue(row, header, index) {
  return Array.isArray(row) ? row[index] : row?.[header];
}

export function previewMappings(headers, rows) {
  const name = header => header.trim().toLowerCase();
  const date = headers.find(header => dateHeaders.includes(name(header))) ?? headers[0];
  const available = headers.find(header => header !== date && availableHeaders.includes(name(header))) ?? '';
  const candidates = headers.filter(header => header !== date && header !== available);
  const columns = candidates.filter(header => rows.some(row =>
    asNumber(previewValue(row, header, headers.indexOf(header))) !== null));
  return { date, available, columns: columns.length ? columns : candidates.length === 1 ? candidates : [] };
}

function csvCell(value, numeric = false) {
  let cell = String(value ?? '');
  const isNumber = numeric && /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(cell);
  if (!isNumber && /^(?:[\t\r\n]|[\s\u0000-\u001f]*[=+\-@＝＋－＠])/.test(cell)) cell = "'" + cell;
  return /[",\n\r]/.test(cell) ? '"' + cell.replaceAll('"', '""') + '"' : cell;
}

export function sampleCsv(samples) {
  const keys = sampleFields.map(([key]) => key);
  const rows = samples.map(sample => keys.map(key => csvCell(sample[key], key === 'x' || key === 'y')).join(','));
  return ['\uFEFF' + keys.join(','), ...rows].join('\r\n') + '\r\n';
}

export function yearsEarlier(isoDate, years) {
  const [year, month, day] = isoDate.split('-').map(Number);
  const earlierYear = year - years;
  const maxDay = new Date(Date.UTC(earlierYear, month, 0)).getUTCDate();
  return [earlierYear, month, Math.min(day, maxDay)].map(value => String(value).padStart(2, '0')).join('-');
}

export const isFraction = transform => transform === 'return' || transform === 'yoy';

export function measure(unit, transform) {
  if (isFraction(transform)) return { unit: '%', kind: 'fraction', format: '.2%', axisFormat: '.1%' };
  if (unit === '%' && transform === 'diff') {
    return { unit: '百分點', kind: 'points', format: ',.2~f', suffix: ' 個百分點' };
  }
  if (unit === '%') return { unit, kind: 'percent', format: ',.2~f', suffix: '%' };
  return { unit: unit || '', kind: 'number', format: ',.6~g' };
}

export function seriesName(series) {
  const names = {
    cbc_usd_twd: '美元／新台幣銀行間收盤匯率',
    twse_0050_close: '元大台灣 50（0050）收盤價',
  };
  const company = /^(quarterly_revenue|quarterly_gross_profit)::(.+)$/.exec(series.id);
  if (company) return `${company[2]} · 單季${company[1] === 'quarterly_revenue' ? '營收' : '毛利'}`;
  return names[series.id] ?? series.name ?? series.id;
}

export function sourceName(series) {
  const sources = {
    'TWSE official historical snapshot': '證交所官方歷史快照',
    'CBC official historical snapshot': '中央銀行官方歷史快照',
    'TWSE/MOPS disclosures (audited historical evidence)': '證交所／公開資訊觀測站歷史揭露',
  };
  if (!series.source) return '來源未標示';
  return series.category === 'Imported' ? series.source : sources[series.source] ?? series.source;
}

export function warningText(warning) {
  const frequency = /^([XY]) has a coarser native frequency\./.exec(warning);
  if (frequency) return `${frequency[1]} 的原始頻率低於所選頻率，無法升頻配對。`;
  if (warning.startsWith('Downsampled observations')) return '降頻後，可用時間最早為該期結束時（UTC）。';
  if (warning === 'No aligned samples at the selected lag.') return '此期差沒有可對齊的樣本。';
  const timing = /^(Selected lag|Lag scan) (excluded|includes) (.+)\.$/.exec(warning);
  if (!timing) return warning;
  const reason = {
    'pairs with missing availability timestamps': '缺少可用時間的配對',
    'pairs with proxy, acquisition-only or other unverified timing': '僅有代理、擷取或未驗證時間的配對',
    'pairs where the X timestamp is after the Y timestamp': 'X 晚於 Y 才可用的配對',
    'pairs whose overlapping release windows leave the X and Y order uncertain': '可用時間區間重疊、無法確認 X 與 Y 先後順序的配對',
  }[timing[3]];
  if (!reason) return warning;
  return `${timing[1] === 'Selected lag' ? '所選期差' : '期差掃描'}${timing[2] === 'excluded' ? '排除' : '包含'}${reason}。`;
}

export function timingText(timing) {
  const labels = {
    page_publication_date: '頁面發布日期',
    actual_release_time: '實際公布時間',
    actual_publication_time: '實際發布時間',
    audit_acquisition: '稽核取得時間',
    capture_time_proxy: '擷取時間（代理）',
  };
  return String(timing).split(' | ').map(part => labels[part] ?? part).join(' ／ ');
}
