// The four trend charts (Chart.js 4.4.1, vendored in assets/vendor/chartjs, loaded as a global).
// Colours: series-1 = not hazardous, series-2 = potentially hazardous (validated pair).
// Marks follow fixed specs: 4px rounded bar ends, 2px surface gaps, >=8px dots with a surface ring.

import { el, fmtInt, fmt1, fmt2, fmtDate, fmtShortDate, fmtMonth, parseDay, isoDay, LD_KM } from './format.js';
import { reducedMotion } from './ui.js';

const css = getComputedStyle(document.documentElement);
const token = (name) => css.getPropertyValue(name).trim();
const C = {
  s1: token('--series-1'),
  s2: token('--series-2'),
  surface: token('--chart-surface'),
  grid: token('--grid'),
  axis: token('--axis'),
  muted: token('--text-muted'),
  secondary: token('--text-secondary'),
  primary: token('--text-primary'),
};

const charts = {};

function setDefaults() {
  const Chart = window.Chart;
  Chart.defaults.color = C.muted;
  Chart.defaults.font.family = token('--font-ui');
  Chart.defaults.font.size = 11;
  Chart.defaults.borderColor = C.grid;
  Chart.defaults.maintainAspectRatio = false;
  Chart.defaults.plugins.legend.display = false;   // HTML legends instead
  Chart.defaults.animation = reducedMotion.matches ? false : { duration: 900, easing: 'easeOutQuart' };
  Object.assign(Chart.defaults.plugins.tooltip, {
    backgroundColor: 'rgba(10, 14, 28, 0.95)',
    borderColor: 'rgba(255, 255, 255, 0.18)',
    borderWidth: 1,
    padding: 10,
    cornerRadius: 10,
    titleColor: C.primary,
    bodyColor: C.secondary,
    titleFont: { weight: '600', size: 12 },
    bodyFont: { size: 12 },
    usePointStyle: true,
    boxPadding: 5,
  });
}

const axis = (extra = {}) => ({
  grid: { color: C.grid, drawTicks: false },
  border: { color: C.axis },
  ticks: { color: C.muted, padding: 8 },
  ...extra,
});

function replace(id, config) {
  charts[id]?.destroy();
  charts[id] = new window.Chart(document.getElementById(id), config);
}

function legend(target, items) {
  const box = document.getElementById(target);
  box.replaceChildren(...items.map(([cls, label, value]) =>
    el('span', {}, el('span', { class: `dot ${cls}` }), label, value != null ? el('strong', { text: value }) : null)));
}

function dataTable(target, headers, rows) {
  const table = el('table', { class: 'data-table' },
    el('thead', {}, el('tr', {}, headers.map((h, i) => el('th', { class: i ? 'num' : null, text: h })))),
    el('tbody', {}, rows.map((r) => el('tr', {}, r.map((c, i) => el('td', { class: i ? 'num' : null, text: c }))))));
  document.getElementById(target).replaceChildren(table);
}

// Stacked bars: bottom segment square, top segment with a 4px rounded end and a 2px surface gap.
const bottomBar = (color) => ({ backgroundColor: color, borderWidth: 0, borderRadius: 0, borderSkipped: false });
const topBar = (color) => ({
  backgroundColor: color, borderColor: C.surface, borderSkipped: false,
  borderWidth: { top: 0, left: 0, right: 0, bottom: 2 },
  borderRadius: { topLeft: 4, topRight: 4, bottomLeft: 0, bottomRight: 0 },
});

/** "Today" hairline on the daily chart. */
const todayMarker = {
  id: 'todayMarker',
  afterDatasetsDraw(chart, _args, opts) {
    if (opts.index == null || opts.index < 0) return;
    const x = chart.scales.x.getPixelForValue(opts.index);
    const { top, bottom } = chart.chartArea;
    const ctx = chart.ctx;
    ctx.save();
    ctx.strokeStyle = 'rgba(255,255,255,0.45)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x, top + 14);
    ctx.lineTo(x, bottom);
    ctx.stroke();
    ctx.fillStyle = C.secondary;
    ctx.font = `600 11px ${token('--font-ui')}`;
    ctx.textAlign = 'center';
    ctx.fillText('Today', x, top + 8);
    ctx.restore();
  },
};

/** Fill every day in [start, end]; days with no rows stay null (shown as a gap, not as zero). */
function dailySeries(daily, start, end) {
  const byDay = new Map(daily.map((d) => [d.approach_date, d]));
  const days = [];
  for (let d = parseDay(start); d <= parseDay(end); d.setDate(d.getDate() + 1)) days.push(isoDay(d));
  return days.map((day) => {
    const row = byDay.get(day);
    return { day, total: row ? row.approach_count : null, haz: row ? row.hazardous_count : null };
  });
}

/** Group days into weeks starting on Monday. */
function weeklySeries(days) {
  const weeks = new Map();
  for (const d of days) {
    const date = parseDay(d.day);
    date.setDate(date.getDate() - ((date.getDay() + 6) % 7));
    const key = isoDay(date);
    const w = weeks.get(key) || { day: key, total: 0, haz: 0, missing: 0, days: 0 };
    w.days += 1;   // days of this week inside the range (first/last week can be partial)
    if (d.total == null) w.missing += 1;
    else { w.total += d.total; w.haz += d.haz; }
    weeks.set(key, w);
  }
  return [...weeks.values()];
}

function renderDaily(trends, range, today) {
  const start = range.start || trends.daily[0]?.approach_date;
  const end = range.end || trends.daily.at(-1)?.approach_date;
  if (!start || !end) return;
  const days = dailySeries(trends.daily, start, end);
  const weekly = range.kind === 'all';
  const points = weekly ? weeklySeries(days) : days;
  const missing = days.filter((d) => d.total == null).length;
  const total = days.reduce((s, d) => s + (d.total || 0), 0);
  const haz = days.reduce((s, d) => s + (d.haz || 0), 0);

  document.getElementById('daily-title').textContent = weekly ? 'Close approaches per week' : 'Close approaches per day';
  document.getElementById('daily-sub').textContent =
    `${fmtDate(start)} – ${fmtDate(end)}` +
    (missing ? ` · ${missing} day${missing > 1 ? 's' : ''} with no approaches recorded (gaps in the NeoWs feed; see pipeline checks)` : '');
  legend('daily-legend', [['s1', 'Not hazardous', fmtInt(total - haz)], ['s2', 'Potentially hazardous', fmtInt(haz)]]);

  const todayIndex = weekly ? -1 : points.findIndex((p) => p.day === today);
  replace('chart-daily', {
    type: 'bar',
    data: {
      labels: points.map((p) => p.day),
      datasets: [
        { label: 'Not hazardous', data: points.map((p) => (p.total == null ? null : p.total - p.haz)), ...bottomBar(C.s1), stack: 's' },
        { label: 'Potentially hazardous', data: points.map((p) => (p.total == null ? null : p.haz)), ...topBar(C.s2), stack: 's' },
      ],
    },
    options: {
      interaction: { mode: 'index', intersect: false },
      datasets: { bar: { categoryPercentage: 0.86, barPercentage: 0.9, maxBarThickness: 24 } },
      scales: {
        x: axis({
          stacked: true, grid: { display: false },
          ticks: {
            color: C.muted, autoSkip: true, maxRotation: 0, maxTicksLimit: weekly ? 7 : 8,
            callback(v) { const d = this.getLabelForValue(v); return weekly ? fmtMonth(d) : fmtShortDate(d); },
          },
        }),
        y: axis({ stacked: true, beginAtZero: true, ticks: { color: C.muted, precision: 0, maxTicksLimit: 5 } }),
      },
      plugins: {
        todayMarker: { index: todayIndex },
        tooltip: {
          callbacks: {
            title: (items) => (weekly ? `Week of ${fmtDate(items[0].label)}` : fmtDate(items[0].label)),
            label: (item) => (item.raw == null ? null : ` ${item.dataset.label}: ${fmtInt(item.raw)}`),
            footer: (items) => {
              const p = points[items[0].dataIndex];
              if (p.total == null) return 'No approaches recorded for this day';
              return [`Total: ${fmtInt(p.total)}`,
                p.days && p.days < 7 ? `Partial week: ${p.days} of 7 days in range` : null,
                p.missing ? `${p.missing} day(s) without data` : null].filter(Boolean).join('\n');
            },
          },
        },
      },
    },
    plugins: [todayMarker],
  });

  dataTable('daily-table', [weekly ? 'Week of' : 'Day', 'Not hazardous', 'Hazardous', 'Total'],
    points.map((p) => [fmtDate(p.day), p.total == null ? 'no data' : fmtInt(p.total - p.haz),
                       p.total == null ? '–' : fmtInt(p.haz), p.total == null ? '–' : fmtInt(p.total)]));
}

function renderDonut(trends) {
  const non = trends.hazardous_split.find((h) => !h.is_potentially_hazardous)?.approach_count || 0;
  const haz = trends.hazardous_split.find((h) => h.is_potentially_hazardous)?.approach_count || 0;
  const total = non + haz;
  const pct = (n) => (total ? `${fmt1((n / total) * 100)}%` : '–');
  document.getElementById('donut-total').textContent = fmtInt(total);
  legend('donut-legend', [['s1', 'Not hazardous', pct(non)], ['s2', 'Hazardous', pct(haz)]]);
  replace('chart-donut', {
    type: 'doughnut',
    data: {
      labels: ['Not hazardous', 'Potentially hazardous'],
      datasets: [{ data: [non, haz], backgroundColor: [C.s1, C.s2], borderWidth: 0, spacing: 3, borderRadius: 6, hoverOffset: 6 }],
    },
    options: {
      cutout: '74%',
      layout: { padding: 8 },
      plugins: { tooltip: { callbacks: { label: (i) => ` ${i.label}: ${fmtInt(i.raw)} (${pct(i.raw)})` } } },
    },
  });
  dataTable('donut-table', ['Group', 'Approaches', 'Share'], [
    ['Not hazardous', fmtInt(non), pct(non)], ['Potentially hazardous', fmtInt(haz), pct(haz)]]);
}

function renderSizes(trends) {
  const bins = trends.size_histogram;
  const totalHaz = bins.reduce((s, b) => s + b.hazardous, 0);
  const total = bins.reduce((s, b) => s + b.count, 0);
  legend('size-legend', [['s1', 'Not hazardous', fmtInt(total - totalHaz)], ['s2', 'Potentially hazardous', fmtInt(totalHaz)]]);
  // This chart counts asteroids, the others count approaches; explain any difference.
  const c = trends.counts;
  const notes = [];
  if (c.approaches > c.asteroids) {
    const n = c.approaches - c.asteroids;
    notes.push(`${fmtInt(c.asteroids)} asteroids make ${fmtInt(c.approaches)} approaches (${fmtInt(n)} extra pass${n > 1 ? 'es' : ''} by asteroids seen more than once)`);
  }
  if (c.asteroids_without_size > 0) notes.push(`${fmtInt(c.asteroids_without_size)} without a size estimate`);
  document.getElementById('size-sub').textContent =
    'Asteroids by maximum estimated diameter' + (notes.length ? ` · ${notes.join(' · ')}` : '');
  replace('chart-size', {
    type: 'bar',
    data: {
      labels: bins.map((b) => b.label),
      datasets: [
        { label: 'Not hazardous', data: bins.map((b) => b.count - b.hazardous), ...bottomBar(C.s1), stack: 's' },
        { label: 'Potentially hazardous', data: bins.map((b) => b.hazardous), ...topBar(C.s2), stack: 's' },
      ],
    },
    options: {
      interaction: { mode: 'index', intersect: false },
      datasets: { bar: { maxBarThickness: 24 } },
      scales: {
        x: axis({ stacked: true, grid: { display: false }, ticks: { color: C.muted, maxRotation: 0, autoSkip: false, font: { size: 10 } } }),
        y: axis({ stacked: true, beginAtZero: true, ticks: { color: C.muted, precision: 0, maxTicksLimit: 5 } }),
      },
      plugins: {
        tooltip: {
          callbacks: {
            title: (items) => `Max diameter ${items[0].label}`,
            label: (i) => ` ${i.dataset.label}: ${fmtInt(i.raw)}`,
            footer: (items) => `Total: ${fmtInt(bins[items[0].dataIndex].count)} asteroids`,
          },
        },
      },
    },
  });
  dataTable('size-table', ['Max diameter', 'Not hazardous', 'Hazardous', 'Total'],
    bins.map((b) => [b.label, fmtInt(b.count - b.hazardous), fmtInt(b.hazardous), fmtInt(b.count)]));
}

function renderScatter(trends, onPick) {
  const toPoint = (p) => ({ x: p.miss_distance_lunar, y: p.relative_velocity_kps, p });
  const pts = trends.velocity_vs_distance.filter((p) => p.miss_distance_lunar > 0 && p.relative_velocity_kps != null);
  const non = pts.filter((p) => !p.is_potentially_hazardous).map(toPoint);
  const haz = pts.filter((p) => p.is_potentially_hazardous).map(toPoint);
  legend('scatter-legend', [['s1', 'Not hazardous', fmtInt(non.length)], ['s2', 'Potentially hazardous', fmtInt(haz.length)]]);
  const dot = (color) => ({
    backgroundColor: color, borderColor: C.surface, borderWidth: 1.5,
    pointRadius: 4, pointHoverRadius: 6, pointHitRadius: 6, pointHoverBorderWidth: 2,
  });
  replace('chart-scatter', {
    type: 'scatter',
    data: { datasets: [{ label: 'Not hazardous', data: non, ...dot(C.s1) }, { label: 'Potentially hazardous', data: haz, ...dot(C.s2) }] },
    options: {
      parsing: false,
      interaction: { mode: 'nearest', intersect: true },
      onClick: (_e, items, chart) => {
        const hit = items[0];
        if (hit) onPick(chart.data.datasets[hit.datasetIndex].data[hit.index].p.neo_id);
      },
      onHover: (e, items) => { e.native.target.style.cursor = items.length ? 'pointer' : 'default'; },
      scales: {
        x: axis({
          type: 'logarithmic',
          title: { display: true, text: 'Miss distance (lunar distances, log scale)', color: C.muted },
          // Label only powers of ten (log ticks are floats, so compare with a tolerance).
          ticks: { color: C.muted, callback: (v) => (Math.abs(Math.log10(v) - Math.round(Math.log10(v))) < 1e-6 ? `${+v.toPrecision(1)} LD` : null) },
        }),
        y: axis({ beginAtZero: true, title: { display: true, text: 'Speed (km/s)', color: C.muted }, ticks: { color: C.muted, maxTicksLimit: 6 } }),
      },
      plugins: {
        tooltip: {
          callbacks: {
            title: (items) => items[0].raw.p.name,
            label: (i) => [` ${fmtDate(i.raw.p.approach_date)}`, ` ${fmt2(i.raw.x)} LD · ${fmtInt(i.raw.x * LD_KM)} km`, ` ${fmt1(i.raw.y)} km/s`],
            footer: () => 'Click to open',
          },
        },
      },
    },
  });
  const sample = [...pts].sort((a, b) => a.miss_distance_lunar - b.miss_distance_lunar).slice(0, 50);
  dataTable('scatter-table', ['Asteroid (50 closest)', 'Date', 'Miss distance (LD)', 'Speed (km/s)'],
    sample.map((p) => [p.name, fmtDate(p.approach_date), fmt2(p.miss_distance_lunar), fmt1(p.relative_velocity_kps)]));
}

export function renderCharts(trends, range, today, onPick) {
  if (!window.Chart) {
    for (const id of ['chart-daily', 'chart-donut', 'chart-size', 'chart-scatter']) {
      document.getElementById(id).parentElement.replaceChildren(
        el('div', { class: 'empty', text: 'Charts could not start (Chart.js failed to load). The data tables below still work.' }));
    }
  }
  if (window.Chart && !renderCharts.ready) {
    setDefaults();
    renderCharts.ready = true;
  }
  const draw = (fn) => { try { if (window.Chart) fn(); } catch (err) { console.error(err); } };
  draw(() => renderDaily(trends, range, today));
  draw(() => renderDonut(trends));
  draw(() => renderSizes(trends));
  draw(() => renderScatter(trends, onPick));
  if (!window.Chart) {
    // still fill the data tables
    try { renderDailyTablesOnly(trends); } catch { /* ignore */ }
  }
}

function renderDailyTablesOnly(trends) {
  dataTable('daily-table', ['Day', 'Approaches', 'Hazardous'],
    trends.daily.map((d) => [fmtDate(d.approach_date), fmtInt(d.approach_count), fmtInt(d.hazardous_count)]));
  dataTable('size-table', ['Max diameter', 'Asteroids', 'Hazardous'],
    trends.size_histogram.map((b) => [b.label, fmtInt(b.count), fmtInt(b.hazardous)]));
}
