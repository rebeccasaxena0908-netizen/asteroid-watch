"""Run the whole pipeline: extract -> transform -> load -> quality checks (+ orbital data).

Every run is logged in pipeline_runs and in logs/pipeline.log.

Examples:
    python -m pipeline.run_pipeline                                   # yesterday .. +7 days
    python -m pipeline.run_pipeline --backfill-days 365 --forward-days 30 --run-type backfill
    python -m pipeline.run_pipeline --dry-run                         # no database writes

pipeline_runs.rows_inserted / rows_updated count close_approaches rows (the main fact table);
asteroid and orbital counts are written to the log.
"""
import argparse
import logging
import sys
from datetime import date, timedelta
from logging.handlers import RotatingFileHandler

from pipeline import quality
from pipeline.config import PROJECT_ROOT, load_settings
from pipeline.db import connect
from pipeline.extract import NeoWsClient, extract_feed, extract_lookups
from pipeline.load import asteroids_needing_orbits, load_feed_rows, load_known_aliases, load_orbital_rows
from pipeline.transform import transform_feeds, transform_orbital

log = logging.getLogger("pipeline")
LOG_FILE = PROJECT_ROOT / "logs" / "pipeline.log"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Asteroid Watch ETL pipeline")
    parser.add_argument("--backfill-days", type=int, default=1, help="days before today (default 1)")
    parser.add_argument("--forward-days", type=int, default=7, help="days after today (default 7)")
    parser.add_argument("--orbital-limit", type=int, default=100,
                        help="max NeoWs Lookup calls for orbital data this run (default 100, 0 = skip)")
    parser.add_argument("--run-type", default="manual", choices=["manual", "daily", "backfill"])
    parser.add_argument("--dry-run", action="store_true", help="extract and transform only, no database writes")
    return parser.parse_args(argv)


def start_run(conn, run_type: str, start: date, end: date) -> int:
    with conn.cursor() as cur:
        cur.execute("INSERT INTO pipeline_runs (run_type, status, date_range_start, date_range_end) "
                    "VALUES (%s, 'running', %s, %s)", (run_type, start, end))
        run_id = cur.lastrowid
    conn.commit()
    return run_id


def finish_run(conn, run_id: int, status: str, stats: dict, error: str | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE pipeline_runs SET finished_at = NOW(), status = %s, api_calls = %s, "
            "records_extracted = %s, records_after_dedupe = %s, rows_inserted = %s, rows_updated = %s, "
            "quality_failures = %s, "
            "error_message = %s WHERE run_id = %s",
            (status, stats.get("api_calls", 0), stats.get("records_extracted", 0), stats.get("records_after_dedupe"),
             stats.get("rows_inserted", 0), stats.get("rows_updated", 0),
             stats.get("quality_failures", 0), error, run_id))
    conn.commit()


def log_checks(checks) -> None:
    for c in checks:
        (log.info if c.passed else log.warning)("Quality %s %s: %s",
                                                "PASS" if c.passed else "FAIL", c.check_name, c.details)


def run(args, settings=None, today: date | None = None) -> dict:
    settings = settings or load_settings()
    if not settings.has_real_api_key:
        raise SystemExit("NASA_API_KEY is not set in .env")
    today = today or date.today()
    start, end = today - timedelta(days=args.backfill_days), today + timedelta(days=args.forward_days)
    client = NeoWsClient(settings.nasa_api_key)
    stats: dict = {}

    if args.dry_run:
        log.info("DRY RUN %s to %s (no database writes)", start, end)
        extracted = extract_feed(client, start, end)
        clean = transform_feeds(extracted.payloads)
        stats = {"api_calls": client.api_calls, "records_extracted": clean.records_seen,
                 "asteroids": len(clean.asteroids), "approaches": len(clean.approaches),
                 "duplicates_removed": clean.duplicates_removed,
                 "same_object_removed": clean.same_object_removed,
                 "same_object_remapped": clean.same_object_remapped, "rejected": len(clean.rejected)}
        log_checks(quality.run_checks(extracted, clean))
        log.info("Dry run result: %s", stats)
        return stats

    conn = connect(settings)
    run_id = start_run(conn, args.run_type, start, end)
    log.info("Run %d (%s) started: %s to %s", run_id, args.run_type, start, end)
    try:
        # Extract (bronze) -> transform (silver) -> load
        extracted = extract_feed(client, start, end)
        clean = transform_feeds(extracted.payloads, load_known_aliases(conn))
        stats["records_extracted"] = clean.records_seen
        stats["records_after_dedupe"] = len(clean.approaches)
        log.info("Transformed %d records into %d asteroids and %d approaches "
                 "(%d duplicates removed, %d old-id copies removed, %d old-id approaches moved "
                 "to numbered ids, %d rejected)",
                 clean.records_seen, len(clean.asteroids), len(clean.approaches), clean.duplicates_removed,
                 clean.same_object_removed, clean.same_object_remapped, len(clean.rejected))
        for reason in clean.rejected[:10]:
            log.warning("Rejected: %s", reason)

        counts = load_feed_rows(conn, clean.asteroids, clean.approaches, clean.new_aliases)
        stats["rows_inserted"] = counts["close_approaches"].inserted
        stats["rows_updated"] = counts["close_approaches"].updated

        with conn.cursor() as cur:
            checks = quality.run_checks(extracted, clean, cur)
        log_checks(checks)
        stats["quality_failures"] = quality.save_results(conn, run_id, checks)

        # Orbital data: only for asteroids missing it or with stale data, capped per run
        if args.orbital_limit > 0:
            neo_ids = asteroids_needing_orbits(conn, args.orbital_limit)
            log.info("Fetching orbital data for %d asteroids", len(neo_ids))
            rows = [r for r in map(transform_orbital, extract_lookups(client, neo_ids)) if r]
            load_orbital_rows(conn, rows)

        stats["api_calls"] = client.api_calls
        finish_run(conn, run_id, "success", stats)
        log.info("Run %d finished: %s", run_id, stats)
        return stats
    except Exception as exc:
        stats["api_calls"] = client.api_calls
        error = client.redact(f"{type(exc).__name__}: {exc}")[:1000]
        conn.rollback()
        finish_run(conn, run_id, "failed", stats, error)
        log.error("Run %d failed: %s", run_id, error)
        raise
    finally:
        conn.close()


def setup_logging() -> None:
    """Log to the terminal and to logs/pipeline.log (rotated at 1 MB, 5 old files kept)."""
    LOG_FILE.parent.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(), RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=5)],
    )


def main(argv=None) -> int:
    setup_logging()
    try:
        run(parse_args(argv))
    except SystemExit:
        raise
    except Exception as exc:
        # Messages are already redacted by NeoWsClient; no traceback, to keep the log short.
        log.error("Pipeline failed: %s: %s", type(exc).__name__, exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
