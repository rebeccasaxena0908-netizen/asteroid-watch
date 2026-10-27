"""The pipeline's steps as plain functions, shared by both ways of running it:

- run_pipeline.run(): a manual run from the terminal (`asteroid-watch run`), steps in a row
- flows/daily.py: the scheduled Prefect flow, where each step is a task with its own retries

Each step opens its own database connection, so a step can be retried on its own.
The steps that call NASA share one NeoWsClient, created by the caller, which counts every
HTTP request of the run (retries included) for pipeline_runs.api_calls, even if a step fails.
"""

import json
import logging
import socket
import time
from collections.abc import Callable
from datetime import date, datetime, timedelta

from pipeline import quality
from pipeline.config import PROJECT_ROOT, Settings, load_settings
from pipeline.db import connect
from pipeline.extract import ExtractResult, NeoWsClient, extract_feed, extract_lookups
from pipeline.load import asteroids_needing_orbits, load_feed_rows, load_known_aliases, load_orbital_rows
from pipeline.transform import TransformResult, transform_feeds, transform_orbital

log = logging.getLogger("pipeline")

FAILURE_LOG = PROJECT_ROOT / "logs" / "failed_attempts.log"
NASA_HOST = ("api.nasa.gov", 443)


class DatabaseDown(Exception):
    """MySQL can't be reached, so the run can't even be recorded in pipeline_runs."""


class NetworkDown(Exception):
    """NASA's API host stayed unreachable for the whole waiting time."""


def nasa_client(settings: Settings | None = None) -> NeoWsClient:
    settings = settings or load_settings()
    if not settings.has_real_api_key:
        raise SystemExit("NASA_API_KEY is not set in .env")
    return NeoWsClient(settings.nasa_api_key)


def date_window(backfill_days: int, forward_days: int, today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    return today - timedelta(days=backfill_days), today + timedelta(days=forward_days)


# --- before the run: network and database ---------------------------------------------

def host_reachable(address: tuple[str, int] = NASA_HOST, timeout: float = 10) -> bool:
    """Can we open a connection to NASA's API? (DNS + TCP only: costs no API request.)"""
    try:
        socket.create_connection(address, timeout=timeout).close()
        return True
    except OSError:
        return False


def wait_for_network(max_wait: timedelta = timedelta(hours=2), interval: timedelta = timedelta(minutes=5),
                     reachable: Callable[[], bool] = host_reachable,
                     sleep: Callable[[float], None] = time.sleep,
                     now: Callable[[], float] = time.time) -> float:
    """Wait until NASA's API host is reachable, checking every `interval`, for at most `max_wait`.

    Uses the wall clock: if the Mac sleeps while we wait, the time asleep counts, and we check
    again as soon as it wakes. Returns the seconds waited; raises NetworkDown when time is up.
    """
    started = now()
    deadline = started + max_wait.total_seconds()
    while True:
        if reachable():
            waited = now() - started
            if waited >= 1:
                log.info("Network is back after %.0f s", waited)
            return waited
        remaining = deadline - now()
        if remaining <= 0:
            raise NetworkDown(f"{NASA_HOST[0]} unreachable for {max_wait}; giving up for this attempt")
        log.warning("No network (%s unreachable); checking again in %.0f s", NASA_HOST[0],
                    min(interval.total_seconds(), remaining))
        sleep(min(interval.total_seconds(), remaining))


def record_failed_attempt(reason: str, **details) -> None:
    """Append one JSON line to logs/failed_attempts.log, for failures that can't go into MySQL."""
    FAILURE_LOG.parent.mkdir(exist_ok=True)
    entry = {"time": datetime.now().isoformat(timespec="seconds"), "reason": reason, **details}
    with FAILURE_LOG.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def recent_failed_attempts(days: int = 7) -> list[dict]:
    if not FAILURE_LOG.exists():
        return []
    since = datetime.now() - timedelta(days=days)
    entries = [json.loads(line) for line in FAILURE_LOG.read_text().splitlines() if line.strip()]
    return [e for e in entries if datetime.fromisoformat(e["time"]) >= since]


def check_database(**details) -> None:
    """Raise DatabaseDown (after writing it to the local failure log) if MySQL is unreachable."""
    try:
        connect().close()
    except Exception as exc:
        reason = f"MySQL not reachable ({type(exc).__name__})"
        record_failed_attempt(reason, **details)
        raise DatabaseDown(reason + ". Is XAMPP MySQL running?") from None


def recent_success(run_type: str, within: timedelta) -> int | None:
    """run_id of a successful NeoWs run of this type that started within `within`, if any."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT MAX(run_id) AS r FROM pipeline_runs WHERE source = 'neows' AND run_type = %s "
                    "AND status = 'success' AND started_at >= NOW() - INTERVAL %s SECOND",
                    (run_type, int(within.total_seconds())))
        return cur.fetchone()["r"]


# --- the run log (pipeline_runs) -------------------------------------------------------

def start_run(run_type: str, start: date, end: date) -> int:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO pipeline_runs (run_type, source, status, date_range_start, date_range_end) "
                        "VALUES (%s, 'neows', 'running', %s, %s)", (run_type, start, end))
            run_id = cur.lastrowid
        conn.commit()
    log.info("Run %d (%s) started: %s to %s", run_id, run_type, start, end)
    return run_id


def finish_run(run_id: int, status: str, stats: dict, error: str | None = None) -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE pipeline_runs SET finished_at = NOW(), status = %s, api_calls = %s, "
                "records_extracted = %s, records_after_dedupe = %s, rows_inserted = %s, rows_updated = %s, "
                "quality_failures = %s, "
                "error_message = %s WHERE run_id = %s",
                (status, stats.get("api_calls", 0), stats.get("records_extracted", 0),
                 stats.get("records_after_dedupe"), stats.get("rows_inserted", 0), stats.get("rows_updated", 0),
                 stats.get("quality_failures", 0), error, run_id))
        conn.commit()


# --- extract -> transform -> load -> quality -> orbits ---------------------------------

def extract(client: NeoWsClient, start: date, end: date) -> ExtractResult:
    """Bronze: fetch the NeoWs feed in 7-day chunks and save the raw JSON."""
    return extract_feed(client, start, end)


def transform(extracted: ExtractResult) -> TransformResult:
    """Silver: flatten, convert, dedupe, and map old IDs to numbered IDs (using known aliases)."""
    with connect() as conn:
        clean = transform_feeds(extracted.payloads, load_known_aliases(conn))
    log.info("Transformed %d records into %d asteroids and %d approaches "
             "(%d duplicates removed, %d old-id copies removed, %d old-id approaches moved "
             "to numbered ids, %d rejected)",
             clean.records_seen, len(clean.asteroids), len(clean.approaches), clean.duplicates_removed,
             clean.same_object_removed, clean.same_object_remapped, len(clean.rejected))
    for reason in clean.rejected[:10]:
        log.warning("Rejected: %s", reason)
    return clean


def load(clean: TransformResult) -> dict:
    """Gold: upsert asteroids, approaches and new aliases in one transaction."""
    with connect() as conn:
        counts = load_feed_rows(conn, clean.asteroids, clean.approaches, clean.new_aliases)
    return {"rows_inserted": counts["close_approaches"].inserted, "rows_updated": counts["close_approaches"].updated}


def check_quality(run_id: int, extracted: ExtractResult, clean: TransformResult) -> int:
    """Run the 8 checks, save them in quality_results, return the number that failed."""
    with connect() as conn:
        with conn.cursor() as cur:
            checks = quality.run_checks(extracted, clean, cur)
        for c in checks:
            (log.info if c.passed else log.warning)("Quality %s %s: %s",
                                                    "PASS" if c.passed else "FAIL", c.check_name, c.details)
        return quality.save_results(conn, run_id, checks)


def orbital_lookups(client: NeoWsClient, limit: int) -> int:
    """Fetch orbits for up to `limit` asteroids missing them (or stale); returns how many were stored."""
    if limit <= 0:
        return 0
    with connect() as conn:
        neo_ids = asteroids_needing_orbits(conn, limit)
        log.info("Fetching orbital data for %d asteroids", len(neo_ids))
        rows = [r for r in map(transform_orbital, extract_lookups(client, neo_ids)) if r]
        load_orbital_rows(conn, rows)
    return len(rows)
