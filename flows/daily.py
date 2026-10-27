"""The daily NeoWs pipeline as a Prefect flow, scheduled at 19:00 IST (flows/serve.py).

The work is done by the same step functions as a manual run (pipeline/steps.py); Prefect
adds the schedule, retries, a run history and the UI at http://127.0.0.1:4200.

Failure handling (see docs/orchestration.md):
- No network (e.g. the Mac woke briefly with Wi-Fi off): wait, checking every 5 minutes,
  for up to 2 hours (never past the end of the scheduled day), instead of failing in seconds.
- MySQL down: write the failure to logs/failed_attempts.log (it can't go into pipeline_runs)
  and retry the whole flow 30 minutes later, up to 6 times (19:30 ... 22:00).
- NASA errors: the HTTP client retries within seconds; the extract task then retries
  after 1, 5 and 15 minutes.
- Missed days (Mac off or asleep): Prefect runs the late runs when the Mac is back; the
  first one does the work and the others see a success under 6 hours old and stop.
"""

import logging
from datetime import datetime, timedelta

from prefect import flow, task
from prefect.cache_policies import NO_CACHE
from prefect.runtime import flow_run

from pipeline import steps
from pipeline.run_pipeline import log_to_file

# The "pipeline" logger goes to logs/pipeline.log and, through Prefect's extra_loggers setting
# (pyproject.toml), to the run's logs in the Prefect UI.
log = logging.getLogger("pipeline")


def step_task(fn, name: str, retries: int = 0, retry_delay_seconds: float | list[float] = 0):
    """A pipeline step as a Prefect task. Results stay in memory: no caching, and nothing
    (such as raw NASA data) is written to disk by Prefect."""
    return task(name=name, retries=retries, retry_delay_seconds=retry_delay_seconds,
                cache_policy=NO_CACHE, persist_result=False)(fn)


wait_for_network = step_task(steps.wait_for_network, "wait for network")   # waits by itself, no retries
check_database = step_task(steps.check_database, "check database")         # the whole flow retries instead
recent_success = step_task(steps.recent_success, "already ran?")
start_run = step_task(steps.start_run, "start run", retries=2, retry_delay_seconds=30)
extract = step_task(steps.extract, "extract", retries=3, retry_delay_seconds=[60, 300, 900])
transform = step_task(steps.transform, "transform", retries=1, retry_delay_seconds=30)
load = step_task(steps.load, "load", retries=2, retry_delay_seconds=[30, 120])
check_quality = step_task(steps.check_quality, "quality checks", retries=2, retry_delay_seconds=30)
orbital_lookups = step_task(steps.orbital_lookups, "orbital lookups", retries=1, retry_delay_seconds=300)
finish_run = step_task(steps.finish_run, "finish run", retries=3, retry_delay_seconds=30)

FLOW_RETRIES = 6
FLOW_RETRY_DELAY = 30 * 60  # seconds


class TooLate(Exception):
    """A retry that would run after the scheduled day; tomorrow's run covers these dates."""


def end_of_day(moment: datetime) -> datetime:
    return moment.replace(hour=23, minute=59, second=59, microsecond=0)


@flow(name="neows-daily", retries=FLOW_RETRIES, retry_delay_seconds=FLOW_RETRY_DELAY)
def neows_daily(backfill_days: int = 1, forward_days: int = 7, orbital_limit: int = 100,
                run_type: str = "daily", skip_if_success_within_hours: float = 6,
                max_network_wait_hours: float = 2) -> dict:
    """Yesterday .. +7 days from NeoWs into MySQL, with quality checks and orbit lookups."""
    log_to_file()  # flow runs execute in their own process, so set up the log file here
    now = datetime.now()
    scheduled = flow_run.scheduled_start_time
    day_end = end_of_day(scheduled.astimezone().replace(tzinfo=None) if scheduled else now)
    if now >= day_end:
        raise TooLate(f"Attempt at {now:%Y-%m-%d %H:%M} is after the scheduled day; tomorrow's run covers it.")

    wait_for_network(max_wait=min(timedelta(hours=max_network_wait_hours), day_end - now))
    check_database(flow_run=str(flow_run.name), run_type=run_type)

    if skip_if_success_within_hours > 0:
        previous = recent_success(run_type, timedelta(hours=skip_if_success_within_hours))
        if previous:
            log.info("Run %s already succeeded in the last %s h; nothing to do.",
                        previous, skip_if_success_within_hours)
            return {"skipped_because_of_run": previous}

    client = steps.nasa_client()
    start, end = steps.date_window(backfill_days, forward_days)
    run_id = start_run(run_type, start, end)
    stats: dict = {}
    try:
        extracted = extract(client, start, end)
        clean = transform(extracted)
        stats["records_extracted"] = clean.records_seen
        stats["records_after_dedupe"] = len(clean.approaches)
        stats |= load(clean)
        stats["quality_failures"] = check_quality(run_id, extracted, clean)
        orbital_lookups(client, orbital_limit)
        stats["api_calls"] = client.api_calls
        finish_run(run_id, "success", stats)
    except Exception as exc:
        stats["api_calls"] = client.api_calls
        error = client.redact(f"{type(exc).__name__}: {exc}")[:1000]
        finish_run(run_id, "failed", stats, error)
        log.error("Run %d failed: %s", run_id, error)
        raise
    log.info("Run %d finished: %s", run_id, stats)
    return {"run_id": run_id, **stats}
