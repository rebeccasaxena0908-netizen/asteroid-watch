// Formatting helpers and a tiny DOM builder.
// Data from the database is only ever inserted with textContent (never innerHTML), so names
// coming from NASA can't inject markup.

// International digit grouping (384,400), consistent with the K/M abbreviations used for big numbers.
const nf0 = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 1 });
const nf2 = new Intl.NumberFormat('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const compact = new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 2 });

export const LD_KM = 384400;

export const fmtInt = (n) => (n == null ? '–' : nf0.format(n));
export const fmt1 = (n) => (n == null ? '–' : nf1.format(n));
export const fmt2 = (n) => (n == null ? '–' : nf2.format(n));
export const fmtCompact = (n) => (n == null ? '–' : compact.format(n));

export function fmtKm(km) {
  if (km == null) return '–';
  return km >= 1e6 ? `${compact.format(km)} km` : `${nf0.format(km)} km`;
}

export function fmtAu(au) {
  return au == null ? '–' : `${au.toFixed(au < 0.01 ? 5 : 4)} AU`;
}

/** Diameter range in m (or km for big objects): "120–270 m". */
export function fmtDiameter(minM, maxM) {
  if (minM == null || maxM == null) return '–';
  if (maxM >= 1000) return `${nf1.format(minM / 1000)}–${nf1.format(maxM / 1000)} km`;
  return `${nf0.format(minM)}–${nf0.format(maxM)} m`;
}

/** Largest dimension as {value, unit} for the stat tile. */
export function sizeValue(maxM) {
  if (maxM == null) return { value: null, unit: '' };
  return maxM >= 1000 ? { value: maxM / 1000, unit: 'km', decimals: 1 } : { value: maxM, unit: 'm', decimals: 0 };
}

const dateFmt = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
const shortDate = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short' });
const monthFmt = new Intl.DateTimeFormat('en-GB', { month: 'short', year: '2-digit' });

/** "2026-10-16" -> Date at local midnight (avoids UTC shifting the day). */
export function parseDay(iso) {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  return new Date(y, m - 1, d);
}
export const fmtDate = (iso) => (iso ? dateFmt.format(parseDay(iso)) : '–');
export const fmtShortDate = (iso) => (iso ? shortDate.format(parseDay(iso)) : '–');
export const fmtMonth = (iso) => monthFmt.format(parseDay(iso));
export const fmtTime = (dt) => (dt && dt.length >= 16 ? dt.slice(11, 16) : '');

export function isoDay(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}
export function addDays(iso, days) {
  const d = parseDay(iso);
  d.setDate(d.getDate() + days);
  return isoDay(d);
}

/** "2026-10-12 21:58:10" (server local time) -> "12 min ago". */
export function timeAgo(dt, now = new Date()) {
  if (!dt) return '–';
  const then = new Date(dt.replace(' ', 'T'));
  const s = Math.round((now - then) / 1000);
  if (s < 60) return 'just now';
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 36) return `${h} h ago`;
  return `${Math.round(h / 24)} days ago`;
}
export function hoursSince(dt, now = new Date()) {
  return dt ? (now - new Date(dt.replace(' ', 'T'))) / 3.6e6 : Infinity;
}

export function fmtDuration(seconds) {
  if (seconds == null) return '–';
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

/**
 * el('td', { class: 'num', text: '12' }, child, ...)
 * Attributes: class, text (textContent), dataset object, on<Event> handlers, anything else -> setAttribute.
 */
export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === 'class') node.className = v;
    else if (k === 'text') node.textContent = v;
    else if (k === 'dataset') Object.assign(node.dataset, v);
    else if (k.startsWith('on') && typeof v === 'function') node.addEventListener(k.slice(2).toLowerCase(), v);
    else node.setAttribute(k, v === true ? '' : v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

/** Inline SVG icon from a fixed set of paths (no user data involved). */
const ICONS = {
  check: '<path d="M20 6 9 17l-5-5"/>',
  cross: '<path d="M18 6 6 18M6 6l12 12"/>',
  alert: '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/>',
  circleCheck: '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
  circleAlert: '<circle cx="12" cy="12" r="9"/><path d="M12 8v4M12 16h.01"/>',
  circleX: '<circle cx="12" cy="12" r="9"/><path d="m15 9-6 6M9 9l6 6"/>',
  spinner: '<circle cx="12" cy="12" r="9" stroke-dasharray="40 20"/>',
  external: '<path d="M15 3h6v6M10 14 21 3M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
  close: '<path d="M18 6 6 18M6 6l12 12"/>',
  triangle: '<path d="M12 3 2 20h20L12 3z" fill="currentColor" stroke="none"/>',
};
export function icon(name) {
  const span = document.createElement('span');
  span.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ''}</svg>`;
  return span.firstChild;
}

/** Hazard badge: orange triangle mark + text label (never colour alone). */
export function hazardBadge(isHazardous) {
  return isHazardous
    ? el('span', { class: 'badge' }, icon('triangle'), 'Hazardous')
    : el('span', { class: 'badge quiet', text: 'Not hazardous' });
}

/** Status of a pipeline run as {cls, icon, label}. Status colours always come with an icon + label. */
export function runStatus(run) {
  if (!run) return { cls: 'info', icon: 'circleAlert', label: 'No runs yet' };
  if (run.status === 'failed') return { cls: 'critical', icon: 'circleX', label: 'Failed' };
  if (run.status === 'running') return { cls: 'info', icon: 'spinner', label: 'Running' };
  if (run.quality_failures > 0) {
    const n = run.quality_failures;
    return { cls: 'warning', icon: 'circleAlert', label: `Success · ${n} check${n > 1 ? 's' : ''} failed` };
  }
  return { cls: 'good', icon: 'circleCheck', label: 'Success' };
}

export function statusEl(status) {
  return el('span', { class: `status ${status.cls}` }, icon(status.icon), status.label);
}

/** Only link to NASA/JPL pages (the URL comes from the database). */
export function safeJplUrl(url) {
  try {
    const u = new URL(url);
    return u.protocol === 'https:' || u.protocol === 'http:'
      ? (/(^|\.)nasa\.gov$/.test(u.hostname) ? u.href.replace(/^http:/, 'https:') : null)
      : null;
  } catch {
    return null;
  }
}
