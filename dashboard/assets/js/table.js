// Close-approaches table: server-side search, filter, sort and pagination via api/approaches.
// The CSV/Excel links download every page of the same filtered, sorted list.

import { api } from './api.js';
import { el, fmtInt, fmt2, fmt1, fmtKm, fmtDate, fmtTime, fmtDiameter, hazardBadge, addDays } from './format.js';

const PER_PAGE = 15;
const DEFAULT_ORDER = { date: 'asc', distance: 'asc', velocity: 'desc', size: 'desc', name: 'asc' };

export function setupTable({ today, onPick, onError }) {
  const state = { q: '', hazardous: 'all', scope: 'upcoming', sort: 'date', order: 'asc', page: 1 };
  const body = document.getElementById('t-body');
  const count = document.getElementById('t-count');
  const pageInfo = document.getElementById('t-page');
  const prev = document.getElementById('t-prev');
  const next = document.getElementById('t-next');
  const downloads = [['t-csv', 'api/approaches.csv'], ['t-xlsx', 'api/approaches.xlsx']];
  let controller = null;
  let searchTimer = null;

  function scopeRange() {
    if (state.scope === 'upcoming') return { start: today, end: null };
    if (state.scope === 'past30') return { start: addDays(today, -30), end: addDays(today, -1) };
    return { start: null, end: null };
  }

  function skeleton() {
    body.replaceChildren(...Array.from({ length: 6 }, () =>
      el('tr', {}, Array.from({ length: 6 }, (_, i) =>
        el('td', { class: i >= 3 && i <= 4 ? 'col-optional' : null }, el('span', { class: 'skeleton' }))))));
  }

  function row(a) {
    const open = () => onPick(a.neo_id);
    return el('tr', {
      class: 'clickable',
      onclick: (e) => { if (!e.target.closest('button')) open(); },
    },
      el('td', {}, el('button', { class: 'name-btn', type: 'button', text: a.name, onclick: open,
                                  'aria-label': `Open details for ${a.name}` })),
      el('td', {}, fmtDate(a.approach_date), el('span', { class: 'secondary', text: fmtTime(a.approach_datetime) || ' ' })),
      el('td', { class: 'num' }, `${fmt2(a.miss_distance_lunar)} LD`, el('span', { class: 'secondary', text: fmtKm(a.miss_distance_km) })),
      el('td', { class: 'num col-optional' }, `${fmt1(a.relative_velocity_kps)} km/s`,
         el('span', { class: 'secondary', text: `${fmtInt(a.relative_velocity_kph)} km/h` })),
      el('td', { class: 'num col-optional', text: fmtDiameter(a.est_diameter_min_m, a.est_diameter_max_m) }),
      el('td', {}, hazardBadge(a.is_potentially_hazardous)),
    );
  }

  function updateSortHeaders() {
    for (const th of document.querySelectorAll('#t-table th[data-sort]')) {
      const active = th.dataset.sort === state.sort;
      if (active) th.setAttribute('aria-sort', state.order === 'asc' ? 'ascending' : 'descending');
      else th.removeAttribute('aria-sort');
      th.querySelector('.arrow').textContent = active ? (state.order === 'asc' ? '↑' : '↓') : '↕';
    }
  }

  function updateDownloads(filters) {
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(filters)) if (v !== null && v !== '') params.set(k, v);
    for (const [id, path] of downloads) document.getElementById(id).href = `${path}?${params}`;
  }

  async function load() {
    controller?.abort();
    controller = new AbortController();
    updateSortHeaders();
    skeleton();
    const { start, end } = scopeRange();
    const filters = { start, end, hazardous: state.hazardous, q: state.q, sort: state.sort, order: state.order };
    updateDownloads(filters);
    try {
      const d = await api('approaches', { ...filters, page: state.page, per_page: PER_PAGE },
                          { signal: controller.signal });
      body.replaceChildren(...(d.items.length
        ? d.items.map(row)
        : [el('tr', {}, el('td', { colspan: 6, class: 'empty', text: 'No close approaches match these filters.' }))]));
      count.textContent = `${fmtInt(d.total)} approach${d.total === 1 ? '' : 'es'}`;
      const from = d.total ? (d.page - 1) * d.per_page + 1 : 0;
      const to = Math.min(d.total, d.page * d.per_page);
      pageInfo.textContent = d.total ? `${fmtInt(from)}–${fmtInt(to)} of ${fmtInt(d.total)} · page ${d.page} of ${d.total_pages}` : '';
      prev.disabled = d.page <= 1;
      next.disabled = d.page >= d.total_pages;
    } catch (err) {
      if (err.name === 'AbortError') return;
      body.replaceChildren(el('tr', {}, el('td', { colspan: 6, class: 'empty', text: err.message })));
      count.textContent = '';
      pageInfo.textContent = '';
      onError?.(err);
    }
  }

  document.getElementById('t-search').addEventListener('input', (e) => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => { state.q = e.target.value.trim(); state.page = 1; load(); }, 250);
  });

  const hazardGroup = document.getElementById('t-hazard');
  hazardGroup.addEventListener('click', (e) => {
    const b = e.target.closest('button');
    if (!b) return;
    hazardGroup.querySelectorAll('button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
    state.hazardous = b.dataset.v;
    state.page = 1;
    load();
  });

  document.getElementById('t-scope').addEventListener('change', (e) => {
    state.scope = e.target.value;
    // Past approaches read best newest-first.
    if (state.sort === 'date') state.order = state.scope === 'upcoming' ? 'asc' : 'desc';
    state.page = 1;
    load();
  });

  for (const th of document.querySelectorAll('#t-table th[data-sort]')) {
    th.querySelector('button').addEventListener('click', () => {
      const key = th.dataset.sort;
      if (state.sort === key) state.order = state.order === 'asc' ? 'desc' : 'asc';
      else { state.sort = key; state.order = DEFAULT_ORDER[key]; }
      state.page = 1;
      load();
    });
  }

  prev.addEventListener('click', () => { state.page -= 1; load(); });
  next.addEventListener('click', () => { state.page += 1; load(); });

  load();
  return { reload: load };
}
