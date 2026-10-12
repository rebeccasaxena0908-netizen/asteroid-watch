// Pipeline health panel (api/runs.php): latest ETL run summary + run history with quality checks.

import { el, icon, fmtInt, fmtDate, fmtDuration, timeAgo, hoursSince, runStatus, statusEl } from './format.js';

const TYPE_LABEL = { daily: 'Daily run', backfill: 'Backfill', manual: 'Manual run', crosscheck: 'JPL cross-check' };

/** A quality check. In a JPL cross-check a non-passing result is a finding about the data, not an error. */
function checkItem(c, isCrosscheck) {
  const state = c.passed ? 'pass' : (isCrosscheck ? 'finding' : 'fail');
  const word = { pass: 'passed', fail: 'failed', finding: 'finding' }[state];
  return el('li', { class: state },
    icon({ pass: 'check', fail: 'alert', finding: 'circleAlert' }[state]),
    el('div', {},
      el('code', { text: c.check_name }), ' ',
      el('span', { class: state === 'finding' ? 'badge quiet' : 'visually-hidden', text: word }),
      el('span', { class: 'd', text: c.details || '' })));
}

/** "1,934 extracted → 1,876 after dedupe" (older runs have no dedupe count). */
function extractedText(run) {
  return run.records_after_dedupe == null
    ? `${fmtInt(run.records_extracted)} extracted`
    : `${fmtInt(run.records_extracted)} extracted → ${fmtInt(run.records_after_dedupe)} after dedupe`;
}

function runItem(run, open) {
  const s = runStatus(run);
  const range = run.date_range_start ? `${fmtDate(run.date_range_start)} – ${fmtDate(run.date_range_end)}` : '';
  const counts = run.run_type === 'crosscheck'
    ? `${fmtInt(run.records_extracted)} approaches compared · ${fmtInt(run.api_calls)} JPL calls`
    : `${extractedText(run)} · +${fmtInt(run.rows_inserted)} new · ${fmtInt(run.rows_updated)} updated · ${fmtInt(run.api_calls)} API calls`;
  const details = el('details', { class: 'run' },
    el('summary', {},
      el('span', { class: 'run-id', text: `#${run.run_id}` }),
      el('div', { class: 'run-main' },
        el('div', { class: 'run-title' }, TYPE_LABEL[run.run_type] || run.run_type,
           el('span', { class: 'badge quiet', text: timeAgo(run.started_at) })),
        el('div', { class: 'run-meta', text: [range, counts, fmtDuration(run.duration_seconds)].filter(Boolean).join(' · ') })),
      statusEl(s)),
    run.error_message ? el('p', { class: 'section-sub', style: 'padding: 0 14px 0 96px', text: run.error_message }) : null,
    el('ul', { class: 'checks' }, run.quality.length
      ? run.quality.map((c) => checkItem(c, run.run_type === 'crosscheck'))
      : el('li', { text: 'No quality checks recorded for this run.' })));
  if (open) details.open = true;
  return details;
}

export function renderHealth(runs) {
  const summary = document.getElementById('health-summary');
  const list = document.getElementById('runs');
  const etl = runs.filter((r) => r.run_type !== 'crosscheck');
  const last = etl[0];

  if (!last) {
    summary.replaceChildren(el('h3', { text: 'No pipeline runs yet' }), el('p', { class: 'section-sub', text: 'Run `make run` to load data.' }));
  } else {
    const s = runStatus(last);
    const passed = last.quality.filter((q) => q.passed).length;
    const stale = hoursSince(last.finished_at || last.started_at) > 26;
    const removed = last.records_after_dedupe == null ? 0 : last.records_extracted - last.records_after_dedupe;
    // replaceChildren() would print "null", so drop empty parts first.
    summary.replaceChildren(...[
      el('span', { class: 'eyebrow', text: 'Latest ETL run' }),
      el('div', { class: `big-status status ${s.cls}` }, icon(s.icon), el('span', { class: 't', text: s.label })),
      el('p', { class: 'section-sub', text: `Run #${last.run_id} · ${TYPE_LABEL[last.run_type] || last.run_type} · finished ${timeAgo(last.finished_at)}` }),
      el('div', { class: 'check-meter', role: 'img', 'aria-label': `${passed} of ${last.quality.length} quality checks passed` },
        last.quality.map((q) => el('span', { class: q.passed ? 'pass' : 'fail', title: q.check_name }))),
      el('dl', { class: 'kv' },
        el('dt', { text: 'Quality checks passed' }), el('dd', { text: `${passed} of ${last.quality.length}` }),
        el('dt', { text: 'Records extracted → after dedupe' }),
        el('dd', { text: last.records_after_dedupe == null ? fmtInt(last.records_extracted)
                         : `${fmtInt(last.records_extracted)} → ${fmtInt(last.records_after_dedupe)}` }),
        el('dt', { text: 'Rows inserted / updated' }), el('dd', { text: `${fmtInt(last.rows_inserted)} / ${fmtInt(last.rows_updated)}` }),
        el('dt', { text: 'NASA API calls' }), el('dd', { text: fmtInt(last.api_calls) }),
        el('dt', { text: 'Duration' }), el('dd', { text: fmtDuration(last.duration_seconds) })),
      removed > 0 ? el('p', { class: 'dedupe-note', text: `${fmtInt(removed)} duplicate listing${removed > 1 ? 's' : ''} removed before loading: NeoWs sometimes lists the same approach twice, for example under an asteroid's old ID.` }) : null,
      stale ? el('p', { class: 'stale-note' }, icon('alert'),
        'The last run finished more than a day ago. Is the daily launchd job installed, and was XAMPP MySQL running at 09:00?') : null,
    ].filter(Boolean));
  }

  list.replaceChildren(...(runs.length ? runs.map((r, i) => runItem(r, i === 0)) : [el('div', { class: 'empty', text: 'No runs recorded.' })]));
}

/** Small chip in the top bar. offline = the API could not reach MySQL. */
export function renderRunChip(lastRun, offline = false) {
  const s = offline ? { cls: 'critical', icon: 'circleX', label: 'Database offline' } : runStatus(lastRun);
  const chip = document.getElementById('run-chip-status');
  chip.className = `status ${s.cls}`;
  chip.replaceChildren(icon(s.icon), el('span', { class: 'chip-text', text: lastRun && !offline ? `Updated ${timeAgo(lastRun.finished_at)}` : s.label }));
  document.getElementById('run-chip').setAttribute('aria-label', `Pipeline: ${s.label}${lastRun ? `, updated ${timeAgo(lastRun.finished_at)}` : ''}`);
}
