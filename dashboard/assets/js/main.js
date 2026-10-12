// Dashboard entry point: loads data from the PHP API and wires up every section.

import { api } from './api.js';
import { el, fmtInt, fmt1, fmt2, fmtKm, fmtDate, fmtDiameter, sizeValue, addDays, isoDay, timeAgo, runStatus, statusEl } from './format.js';
import { countUp, setupReveal, setupCardGlow, showBanner, hideBanner, reducedMotion } from './ui.js';
import { renderCharts } from './charts.js';
import { setupTable } from './table.js';
import { openAsteroid } from './modal.js';
import { renderHealth, renderRunChip } from './health.js';

let today = isoDay(new Date());   // replaced by the database's CURDATE() once the summary loads
let space = null;
let table = null;
let range = 'around';

const pick = (neoId) => openAsteroid(neoId, today);

// ---------------------------------------------------------------- 3D background

async function startBackground() {
  try {
    const probe = document.createElement('canvas');
    if (!(probe.getContext('webgl2') || probe.getContext('webgl'))) throw new Error('WebGL not available');
    const { startSpace } = await import('./space.js');
    space = startSpace({
      canvas: document.getElementById('space'),
      stage: document.getElementById('hero-stage'),
      label: document.getElementById('scene-label'),
      reducedMotion: reducedMotion.matches,
      onReady: () => document.documentElement.classList.add('space-ready'),
    });
  } catch (err) {
    // Keep the CSS gradient background (e.g. offline: three.js comes from cdn.jsdelivr.net).
    console.warn('3D background unavailable:', err.message);
  }
}

// ---------------------------------------------------------------- summary: hero + tiles

function renderSummary(s) {
  const t = s.totals, w = s.this_week, c = s.closest_this_week, big = s.largest, run = s.last_run;

  document.getElementById('hero-pill').textContent = `Live from MySQL · ${fmtInt(t.approaches)} approaches stored, ${fmtDate(t.first_date)} – ${fmtDate(t.last_date)}`;
  countUp(document.getElementById('hero-week'), w.asteroids, fmtInt, 1600);
  const lead = document.getElementById('hero-lead');
  lead.replaceChildren(
    el('strong', { text: fmtInt(w.hazardous) }), ` of them ${w.hazardous === 1 ? 'is' : 'are'} potentially hazardous. `,
    c ? 'The closest, ' : '', c ? el('strong', { text: c.name }) : '', c ? ', passes at ' : '',
    c ? el('strong', { text: `${fmt2(c.miss_distance_lunar)} lunar distances` }) : '',
    c ? ` (${fmtKm(c.miss_distance_km)}) on ${fmtDate(c.approach_date)}.` : 'No close approaches stored for the next 7 days.');

  countUp(document.getElementById('c-week'), w.asteroids, fmtInt);
  document.getElementById('c-week-sub').replaceChildren(
    el('strong', { text: fmtInt(w.approaches) }), ` close approaches · ${fmtDate(today)} – ${fmtDate(addDays(today, 6))}`);

  const closestCard = document.getElementById('c-closest-card');
  const closest = document.getElementById('c-closest');
  if (c) {
    closest.replaceChildren(el('span', { text: '0' }), el('span', { class: 'unit', text: 'LD' }));
    countUp(closest.firstChild, c.miss_distance_lunar, fmt2);
    document.getElementById('c-closest-sub').replaceChildren(el('strong', { text: c.name }), ` · ${fmtDate(c.approach_date)} · ${fmtKm(c.miss_distance_km)}`);
    closestCard.disabled = false;
    closestCard.onclick = () => pick(c.neo_id);
    closestCard.setAttribute('aria-label', `Closest approach this week: ${c.name}, ${fmt2(c.miss_distance_lunar)} lunar distances. Open details.`);
  }

  const largestCard = document.getElementById('c-largest-card');
  if (big) {
    const v = sizeValue(big.est_diameter_max_m);
    const box = document.getElementById('c-largest');
    box.replaceChildren(el('span', { text: '0' }), el('span', { class: 'unit', text: v.unit }));
    countUp(box.firstChild, v.value, v.decimals ? fmt1 : fmtInt);
    document.getElementById('c-largest-sub').replaceChildren(
      el('strong', { text: big.name }), ` · up to ${fmtDiameter(big.est_diameter_min_m, big.est_diameter_max_m).split('–')[1]} across`);
    largestCard.disabled = false;
    largestCard.onclick = () => pick(big.neo_id);
    largestCard.setAttribute('aria-label', `Largest tracked object: ${big.name}. Open details.`);
  }

  countUp(document.getElementById('c-haz'), t.hazardous_asteroids, fmtInt);
  document.getElementById('c-haz-sub').replaceChildren(
    el('strong', { text: fmtInt(w.hazardous) }), ` pass this week · of ${fmtInt(t.asteroids)} asteroids tracked`);

  const runBox = document.getElementById('c-run');
  if (run) {
    runBox.replaceChildren(statusEl(runStatus(run)));
    const passed = run.quality_checks - run.quality_failures;
    document.getElementById('c-run-sub').replaceChildren(
      `Run #${run.run_id} · ${timeAgo(run.finished_at)} · `, el('strong', { text: `${passed}/${run.quality_checks}` }), ' quality checks passed');
  } else {
    runBox.textContent = 'No runs yet';
  }
  renderRunChip(run);
}

// ---------------------------------------------------------------- charts

function rangeParams(kind) {
  if (kind === 'around') return { kind, start: addDays(today, -30), end: addDays(today, 30) };
  if (kind === 'past90') return { kind, start: addDays(today, -90), end: today };
  return { kind, start: null, end: null };
}

async function loadCharts() {
  const r = rangeParams(range);
  try {
    const trends = await api('trends.php', { start: r.start, end: r.end });
    renderCharts(trends, r, today, pick);
  } catch (err) {
    showBanner(`Charts: ${err.message}`, loadAll);
  }
}

document.getElementById('range').addEventListener('click', (e) => {
  const b = e.target.closest('button');
  if (!b || b.dataset.range === range) return;
  range = b.dataset.range;
  document.querySelectorAll('#range button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
  loadCharts();
});

// ---------------------------------------------------------------- load everything

async function loadAll() {
  hideBanner();
  let summary;
  try {
    summary = await api('summary.php');
  } catch (err) {
    // Never show made-up numbers: keep the placeholders and explain what's wrong.
    showBanner(err.message, loadAll);
    renderRunChip(null, true);
    document.getElementById('hero-lead').textContent = "Can't load data right now. The numbers appear as soon as the database is reachable.";
    return;
  }
  today = summary.totals.today;
  renderSummary(summary);

  if (!table) table = setupTable({ today, onPick: pick, onError: (err) => showBanner(err.message, loadAll) });
  else table.reload();

  loadCharts();

  api('runs.php', { limit: 10 })
    .then((d) => renderHealth(d.runs))
    .catch((err) => showBanner(`Pipeline history: ${err.message}`, loadAll));

  // This week's real approaches become the rocks around the 3D Earth.
  api('approaches.php', { start: today, end: addDays(today, 6), per_page: 100, sort: 'distance' })
    .then(async (d) => { await spaceReady; space?.setAsteroids(d.items, pick); })
    .catch(() => { /* the scene still works without rocks */ });
}

setupReveal();
setupCardGlow();
// The 3D scene (three.js from the CDN) and the data load in parallel.
const spaceReady = startBackground();
loadAll();
