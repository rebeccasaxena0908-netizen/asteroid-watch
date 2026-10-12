// Asteroid detail dialog (api/asteroid.php).

import { api } from './api.js';
import {
  el, icon, fmtInt, fmt1, fmt2, fmtKm, fmtAu, fmtDate, fmtTime, fmtDiameter, hazardBadge, safeJplUrl, LD_KM,
} from './format.js';

const dialog = document.getElementById('asteroid-modal');
const bodyEl = document.getElementById('m-body');
let requestId = 0;

dialog.addEventListener('click', (e) => { if (e.target === dialog) dialog.close(); });   // click on backdrop

const SVG_NS = 'http://www.w3.org/2000/svg';
function svg(tag, attrs = {}, text) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (text != null) node.textContent = text;
  return node;
}

function closeButton() {
  return el('button', { class: 'icon-btn', type: 'button', 'aria-label': 'Close', onclick: () => dialog.close() }, icon('close'));
}

function stat(label, value, unit, sub) {
  return el('div', { class: 'stat' },
    el('div', { class: 'l', text: label }),
    el('div', { class: 'v' }, value, unit ? el('span', { class: 'unit', text: unit }) : null),
    sub ? el('div', { class: 's', text: sub }) : null);
}

/** Log scale from 0.05 to 500 LD with Earth, the Moon (1 LD) and this approach. */
function moonScale(ld) {
  const W = 380, H = 70, x0 = 24, x1 = W - 16;
  const min = Math.log10(0.05), max = Math.log10(500);
  const x = (v) => x0 + ((Math.log10(Math.min(Math.max(v, 0.05), 500)) - min) / (max - min)) * (x1 - x0);
  const s = svg('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': `Miss distance ${fmt2(ld)} lunar distances on a log scale` });
  s.append(svg('line', { x1: x0, x2: x1, y1: 34, y2: 34, stroke: 'rgba(255,255,255,0.18)', 'stroke-width': 1 }));
  for (const t of [0.1, 1, 10, 100]) {
    s.append(svg('line', { x1: x(t), x2: x(t), y1: 30, y2: 38, stroke: 'rgba(255,255,255,0.3)' }));
    s.append(svg('text', { x: x(t), y: 56, 'text-anchor': 'middle', fill: '#8a93b2', 'font-size': 11 }, `${t} LD`));
  }
  s.append(svg('circle', { cx: x0 - 8, cy: 34, r: 7, fill: '#3987e5' }));
  s.append(svg('text', { x: x0 - 8, y: 16, 'text-anchor': 'start', fill: '#b9c0d9', 'font-size': 11 }, 'Earth'));
  s.append(svg('circle', { cx: x(1), cy: 34, r: 4, fill: '#c9ccd6' }));
  s.append(svg('text', { x: x(1), y: 18, 'text-anchor': 'middle', fill: '#b9c0d9', 'font-size': 11 }, 'Moon'));
  s.append(svg('circle', { cx: x(ld), cy: 34, r: 6, fill: '#fff', stroke: '#141a2e', 'stroke-width': 2 }));
  s.append(svg('text', { x: Math.min(x(ld), W - 30), y: 18, 'text-anchor': 'middle', fill: '#eef1fb', 'font-size': 11, 'font-weight': 600 }, 'This pass'));
  return s;
}

/** Orbit shape and size vs Earth's orbit. a from Kepler's third law: a(AU) = P(years)^(2/3). */
function orbitSketch(orbit) {
  const P = orbit.orbital_period_days, e = orbit.eccentricity;
  if (!(P > 0) || e == null || e >= 1) return null;
  const a = (P / 365.25) ** (2 / 3);
  const b = a * Math.sqrt(1 - e * e);
  const q = a * (1 - e), Q = a * (1 + e);
  const W = 380, H = 230, cx = W / 2, cy = H / 2 - 8;
  // Fit both the asteroid's ellipse and Earth's orbit (radius 1 AU around the Sun) in the box.
  const scale = Math.min(
    (H / 2 - 30) / Math.max(b, 1.05),
    (W / 2 - 16) / (a * (1 + e / 2)),
    (W / 2 - 16) / (1 + (a * e) / 2),
  );
  const s = svg('svg', { class: 'orbit-svg', viewBox: `0 0 ${W} ${H}`, role: 'img',
    'aria-label': `Orbit sketch: perihelion ${fmt2(q)} AU, aphelion ${fmt2(Q)} AU, Earth's orbit 1 AU` });
  // Sun at one focus: ellipse centre is shifted by c = a*e.
  const sunX = cx - (a * e * scale) / 2;
  const centreX = sunX + a * e * scale;
  s.append(svg('circle', { cx: sunX, cy, r: scale, fill: 'none', stroke: '#3987e5', 'stroke-opacity': 0.6, 'stroke-width': 1.5, 'stroke-dasharray': '4 5' }));
  s.append(svg('ellipse', { cx: centreX, cy, rx: a * scale, ry: b * scale, fill: 'none', stroke: '#eef1fb', 'stroke-width': 2 }));
  s.append(svg('circle', { cx: sunX, cy, r: 6, fill: '#fab219' }));
  s.append(svg('text', { x: sunX, y: cy + 22, 'text-anchor': 'middle', fill: '#b9c0d9', 'font-size': 11 }, 'Sun'));
  s.append(svg('circle', { cx: sunX + scale, cy, r: 4, fill: '#3987e5' }));
  s.append(svg('text', { x: sunX, y: cy - scale - 7, 'text-anchor': 'middle', fill: '#b9c0d9', 'font-size': 11 }, "Earth's orbit (1 AU)"));
  s.append(svg('text', { x: W / 2, y: H - 6, 'text-anchor': 'middle', fill: '#8a93b2', 'font-size': 11 },
    `perihelion ${fmt2(q)} AU · aphelion ${fmt2(Q)} AU · a = ${fmt2(a)} AU`));
  return s;
}

function pickApproach(approaches, today) {
  const upcoming = approaches.filter((a) => a.approach_date >= today);
  return upcoming[0] || approaches.at(-1) || null;
}

function render(d, today) {
  const a = d.asteroid;
  const main = pickApproach(d.approaches, today);
  const jpl = safeJplUrl(a.nasa_jpl_url);
  const isNext = main && main.approach_date >= today;

  const head = el('div', { class: 'modal-head' },
    el('div', {},
      el('span', { class: 'eyebrow', text: `NEO ${a.neo_id}` }),
      el('h2', { id: 'm-title', text: a.name }),
      el('div', { class: 'modal-badges' },
        hazardBadge(a.is_potentially_hazardous),
        a.is_sentry_object ? el('span', { class: 'badge quiet', text: 'On the Sentry impact-monitoring list' }) : null,
        d.orbit?.orbit_class ? el('span', { class: 'badge quiet', text: `Orbit class ${d.orbit.orbit_class}` }) : null)),
    closeButton());

  const stats = el('div', { class: 'stat-grid' },
    stat('Estimated diameter', fmtDiameter(a.est_diameter_min_m, a.est_diameter_max_m), null,
         a.absolute_magnitude_h != null ? `absolute magnitude H ${fmt1(a.absolute_magnitude_h)}` : null),
    main ? stat(isNext ? 'Next close approach' : 'Last close approach', fmtDate(main.approach_date), null,
                fmtTime(main.approach_datetime) ? `${fmtTime(main.approach_datetime)} · ${main.orbiting_body}` : main.orbiting_body) : stat('Close approach', '–'),
    main ? stat('Miss distance', fmt2(main.miss_distance_lunar), 'LD', `${fmtKm(main.miss_distance_km)} · ${fmtAu(main.miss_distance_au)}`) : stat('Miss distance', '–'),
    main ? stat('Relative speed', fmt1(main.relative_velocity_kps), 'km/s', `${fmtInt(main.relative_velocity_kph)} km/h`) : stat('Relative speed', '–'));

  const distancePanel = el('div', { class: 'panel' },
    el('h3', { text: 'How close is that?' }),
    main ? el('p', {}, main.miss_distance_lunar < 1
      ? `${fmt2(main.miss_distance_lunar)} lunar distances: closer than the Moon (${fmtInt(main.miss_distance_km)} km).`
      : `${fmt1(main.miss_distance_lunar)} times the Earth–Moon distance (${fmtInt(LD_KM)} km).`) : el('p', { text: 'No approach stored.' }),
    main ? el('div', { class: 'moon-scale' }, moonScale(main.miss_distance_lunar)) : null);

  const orbitPanel = el('div', { class: 'panel' }, el('h3', { text: 'Orbit around the Sun' }));
  if (d.orbit) {
    const o = d.orbit;
    orbitPanel.append(
      el('p', { text: o.orbit_class_description || o.orbit_class || '' }),
      el('p', { text: `Period ${fmtInt(o.orbital_period_days)} days (${fmt2(o.orbital_period_days / 365.25)} years) · eccentricity ${fmt2(o.eccentricity)} · inclination ${fmt1(o.inclination_deg)}°` }));
    const sketch = orbitSketch(o);
    if (sketch) orbitPanel.append(sketch, el('p', { text: 'Shape and size from the period and eccentricity; the real orientation of the orbit is not shown.' }));
  } else {
    orbitPanel.append(el('p', { text: 'Orbital data not fetched yet. The pipeline fetches up to 100 orbits per run, hazardous asteroids first.' }));
  }

  const rows = d.approaches.map((ap) => el('tr', {},
    el('td', {}, fmtDate(ap.approach_date), el('span', { class: 'secondary', text: fmtTime(ap.approach_datetime) || ' ' })),
    el('td', { class: 'num', text: `${fmt2(ap.miss_distance_lunar)} LD` }),
    el('td', { class: 'num', text: fmtKm(ap.miss_distance_km) }),
    el('td', { class: 'num col-optional', text: fmtAu(ap.miss_distance_au) }),
    el('td', { class: 'num', text: `${fmt1(ap.relative_velocity_kps)} km/s` })));
  const approachesPanel = el('div', { class: 'panel', style: 'margin-top:16px' },
    el('h3', { text: `Stored close approaches (${d.approaches.length})` }),
    el('div', { class: 'table-scroll' }, el('table', { class: 'data-table' },
      el('thead', {}, el('tr', {},
        el('th', { text: 'Date' }), el('th', { class: 'num', text: 'LD' }), el('th', { class: 'num', text: 'km' }),
        el('th', { class: 'num col-optional', text: 'AU' }), el('th', { class: 'num', text: 'Speed' }))),
      el('tbody', {}, rows))));

  const notes = [];
  if (d.old_ids.length) notes.push(`NASA also lists this asteroid under old ID${d.old_ids.length > 1 ? 's' : ''} ${d.old_ids.join(', ')}; those approaches are stored here.`);
  if (d.resolved_from) notes.push(`You opened old ID ${d.resolved_from}, which now maps to ${a.neo_id}.`);

  const foot = el('div', { class: 'modal-foot' },
    el('span', { class: 'note', text: notes.join(' ') || 'Values from NASA NeoWs, as loaded by the pipeline.' }),
    jpl ? el('a', { class: 'btn small', href: jpl, target: '_blank', rel: 'noopener' }, 'Open in NASA JPL', icon('external')) : null);

  bodyEl.replaceChildren(head, stats, el('div', { class: 'modal-cols' }, distancePanel, orbitPanel), approachesPanel, foot);
}

export async function openAsteroid(neoId, today) {
  const id = ++requestId;
  bodyEl.replaceChildren(
    el('div', { class: 'modal-head' }, el('div', {}, el('span', { class: 'skeleton', style: 'width:220px;height:1.6em' })), closeButton()),
    el('div', { class: 'stat-grid' }, Array.from({ length: 4 }, () => el('div', { class: 'stat' }, el('span', { class: 'skeleton' })))));
  if (!dialog.open) dialog.showModal();
  try {
    const d = await api('asteroid.php', { id: neoId });
    if (id === requestId) render(d, today);
  } catch (err) {
    if (id === requestId) {
      bodyEl.replaceChildren(el('div', { class: 'modal-head' }, el('h2', { id: 'm-title', text: 'Could not load this asteroid' }), closeButton()),
        el('p', { class: 'section-sub', text: err.message }));
    }
  }
}
