import { asNumber, measure, seriesName } from './model.js';

const ink = '#202a33';
const muted = '#566372';
const grid = '#e9ece7';
const blue = '#2448aa';
const orange = '#c96829';
const font = '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang TC", "Microsoft JhengHei", sans-serif';
const config = { displayModeBar: false, displaylogo: false, responsive: false, scrollZoom: false };
const lastSizes = new WeakMap();

function safeText(value) {
  return String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
}

function axis(overrides = {}) {
  return {
    gridcolor: grid, zerolinecolor: '#cbd3cd', linecolor: '#dbe0d9',
    tickfont: { size: 10, color: muted }, automargin: true, showline: true,
    ...overrides,
  };
}

function timeAxis(overrides) {
  return axis({ type: 'date', hoverformat: '%Y-%m-%d', ...overrides });
}

const dateTickCount = width => width ? Math.max(3, Math.min(9, Math.round(width / 76))) : 7;

function valueAxis(metric, overrides) {
  return axis({
    tickformat: metric.axisFormat,
    ticksuffix: metric.kind === 'percent' ? '%' : '',
    ...overrides,
  });
}

function layout(overrides) {
  return {
    autosize: true,
    paper_bgcolor: '#fffefa',
    plot_bgcolor: '#fffefa',
    font: { family: font, size: 12, color: ink },
    margin: { l: 48, r: 24, t: 10, b: 33, pad: 0 },
    hoverlabel: { bgcolor: '#fffefa', bordercolor: '#d0d8d3', font: { family: font, size: 11 }, namelength: -1 },
    hovermode: 'closest',
    showlegend: false,
    ...overrides,
  };
}

function unitTitle(unit) {
  return unit ? { text: safeText(unit), font: { size: 10, color: muted }, standoff: 7 } : undefined;
}

export async function drawPlot(node, { traces, chartLayout }) {
  if (!globalThis.Plotly?.react) throw new Error('本機 Plotly 圖表套件無法載入。');
  await globalThis.Plotly.react(node, traces, chartLayout, config);
}

export function observePlots(nodes) {
  if (!globalThis.ResizeObserver) return;
  const observer = new ResizeObserver(entries => {
    for (const { target, contentRect } of entries) {
      const plot = target.querySelector('.plot');
      if (!(contentRect.width && contentRect.height && plot?.layout && plot.classList.contains('is-ready'))) continue;
      const size = [contentRect.width, contentRect.height].join('×');
      if (lastSizes.get(plot) === size) continue;
      lastSizes.set(plot, size);
      const plotly = globalThis.Plotly;
      plotly.Plots.resize(plot).then(() => {
        const count = dateTickCount(contentRect.width);
        if (plot.layout.xaxis?.type === 'date' && plot.layout.xaxis.nticks !== count) {
          return plotly.relayout(plot, { 'xaxis.nticks': count });
        }
      }).catch(() => {});
    }
  });
  for (const node of nodes) observer.observe(node.parentElement);
}

export async function zoomPlot(plot, action) {
  if (!plot.layout) return;
  const changes = {};
  if (action === 'reset') {
    for (const key of Object.keys(plot.layout)) {
      if (/^[xy]axis\d*$/.test(key)) changes[key + '.autorange'] = true;
    }
  } else {
    const range = plot._fullLayout?.xaxis?.range?.map(value => Date.parse(String(value).replace(' ', 'T')));
    if (!range || range.some(date => !Number.isFinite(date))) return;
    const midpoint = (range[0] + range[1]) / 2;
    const halfWidth = (range[1] - range[0]) / 2 * (action === 'in' ? .65 : 1.5);
    changes['xaxis.range'] = [midpoint - halfWidth, midpoint + halfWidth].map(value => new Date(value).toISOString());
    changes['xaxis.autorange'] = false;
  }
  await globalThis.Plotly.relayout(plot, changes);
}

export function trendSpec(series, colorFor, payload, width) {
  const axes = new Map();
  const active = series.filter(item => item.points.some(point => asNumber(point.value) !== null));
  for (const item of active) {
    const metric = measure(item.unit, item.transform);
    const key = metric.kind + '|' + metric.unit;
    if (!axes.has(key)) axes.set(key, { ...metric, index: axes.size + 1 });
  }
  const chartLayout = layout({
    margin: { l: 59, r: axes.size > 1 ? 58 : 19, t: 11, b: 32 },
    xaxis: timeAxis({ nticks: dateTickCount(width), showspikes: true }),
    hovermode: 'x unified',
    dragmode: 'zoom',
    uirevision: JSON.stringify(payload),
  });

  for (const metric of axes.values()) {
    const { index } = metric;
    const title = unitTitle(metric.unit);
    if (index === 1) {
      chartLayout.yaxis = valueAxis(metric, { title, nticks: 7 });
    } else {
      chartLayout['yaxis' + index] = valueAxis(metric, {
        overlaying: 'y', side: 'right', title: index === 2 ? title : undefined, showgrid: false, zeroline: false, nticks: 7,
        ...(index > 2 ? { anchor: 'free', autoshift: true, position: 1 } : {}),
      });
    }
  }

  const traces = active.map((item, index) => {
    const metric = measure(item.unit, item.transform);
    const { index: axisIndex } = axes.get(metric.kind + '|' + metric.unit);
    const color = colorFor(item.id);
    const points = item.points;
    const finiteCount = points.filter(point => asNumber(point.value) !== null).length;
    return {
      type: 'scatter',
      uid: item.id,
      x: points.map(point => point.date),
      y: points.map(point => asNumber(point.value)),
      yaxis: axisIndex === 1 ? 'y' : 'y' + axisIndex,
      mode: finiteCount < 36 || points.some(point => point.value == null) ? 'lines+markers' : 'lines',
      name: safeText(seriesName(item)),
      line: { color, width: 2.1, dash: ['solid', 'dash', 'dot'][Math.floor(index / 6) % 3] },
      marker: { color, size: 4 },
      connectgaps: false,
      hovertemplate: '%{y:' + metric.format + '}' + (metric.suffix ?? (metric.kind === 'number' && metric.unit ? ' ' + safeText(metric.unit) : '')) + '<extra>%{fullData.name}</extra>',
    };
  });
  return { traces, chartLayout };
}

const correlationAxis = () => axis({ range: [-1.06, 1.06], dtick: .5, tickformat: '.1f' });
const methods = [['pearson', 'Pearson', blue], ['spearman', 'Spearman', orange]];

export function rollingSpec(rolling, width) {
  const traces = methods.map(([key, name, color]) => ({
    type: 'scatter', mode: 'lines+markers', x: rolling.map(row => row.date),
    y: rolling.map(row => asNumber(row[key])), name,
    connectgaps: false, line: { color, width: 2, dash: key === 'spearman' ? 'dash' : 'solid' },
    marker: { color, size: 4 }, hovertemplate: '%{y:.4f}<extra>%{fullData.name}</extra>',
  }));
  return {
    traces,
    chartLayout: layout({ hovermode: 'x unified', xaxis: timeAxis({ nticks: dateTickCount(width) }), yaxis: correlationAxis() }),
  };
}

export function lagsSpec(lags, selected) {
  const traces = methods.map(([key, name, color]) => ({
    type: 'bar', x: lags.map(row => row.lag), y: lags.map(row => asNumber(row[key])), name,
    marker: {
      color, opacity: lags.map(row => row.lag === selected ? 1 : .66),
    },
    customdata: lags.map(row => row.n),
    hovertemplate: '%{y:.4f}<br>樣本 %{customdata}<extra>%{fullData.name}</extra>',
  }));
  return {
    traces,
    chartLayout: layout({
      hovermode: 'x unified', barmode: 'group', bargap: .21,
      xaxis: axis({ type: 'linear', dtick: 1, tickformat: '+d', showgrid: false }),
      yaxis: correlationAxis(),
    }),
  };
}

export function scatterSpec(samples, xMeta, yMeta, xTransform, yTransform) {
  const measurements = [measure(xMeta.unit, xTransform), measure(yMeta.unit, yTransform)];
  const titles = ['X', 'Y'].map((side, index) => {
    const metric = measurements[index];
    return side + ' ' + seriesName(index === 0 ? xMeta : yMeta) + (metric.unit ? '（' + metric.unit + '）' : '');
  });
  const formatted = ['x', 'y'].map((side, index) => {
    const metric = measurements[index];
    return '%{' + side + ':' + metric.format + '}' + (metric.suffix ?? '');
  });
  return {
    traces: [{
      type: 'scatter', mode: 'markers', name: '對齊樣本',
      x: samples.map(row => row.x), y: samples.map(row => row.y),
      customdata: samples.map(row => [row.x_date, row.y_date]),
      marker: { color: blue, opacity: .74, size: 8, line: { width: 1, color: '#fffefa' } },
      hovertemplate: 'X ' + formatted[0] + ' · %{customdata[0]}<br>Y ' + formatted[1] + ' · %{customdata[1]}<extra></extra>',
    }],
    chartLayout: layout({
      margin: { l: 62, r: 16, t: 10, b: 53 },
      xaxis: valueAxis(measurements[0], { title: unitTitle(titles[0]), nticks: 7 }),
      yaxis: valueAxis(measurements[1], { title: unitTitle(titles[1]), nticks: 6 }),
    }),
  };
}
