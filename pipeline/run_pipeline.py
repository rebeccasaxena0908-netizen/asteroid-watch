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
from datetime import date
from logging.handlers import RotatingFileHandler

from pipeline import quality, steps
from pipeline.config import PROJECT_ROOT
from pipeline.extract import extract_feed
from pipeline.transform import transform_feeds

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


def run(args, settings=None, today: date | None = None) -> dict:
    """A manual run: the steps in pipeline/steps.py, one after another.

    (The scheduled daily run is the Prefect flow in flows/daily.py, built from the same steps.)
    """
    client = steps.nasa_client(settings)
    start, end = steps.date_window(args.backfill_days, args.forward_days, today)
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
        for c in quality.run_checks(extracted, clean):
            (log.info if c.passed else log.warning)("Quality %s %s: %s",
                                                    "PASS" if c.passed else "FAIL", c.check_name, c.details)
        log.info("Dry run result: %s", stats)
        return stats

    steps.check_database(run_type=args.run_type, start=str(start), end=str(end))
    run_id = steps.start_run(args.run_type, start, end)
    try:
        # Extract (bronze) -> transform (silver) -> load (gold) -> quality checks -> orbits
        extracted = steps.extract(client, start, end)
        clean = steps.transform(extracted)
        stats["records_extracted"] = clean.records_seen
        stats["records_after_dedupe"] = len(clean.approaches)
        stats |= steps.load(clean)
        stats["quality_failures"] = steps.check_quality(run_id, extracted, clean)
        # Orbital data: only for asteroids missing it or with stale data, capped per run
        steps.orbital_lookups(client, args.orbital_limit)

        stats["api_calls"] = client.api_calls
        steps.finish_run(run_id, "success", stats)
        log.info("Run %d finished: %s", run_id, stats)
        return stats
    except Exception as exc:
        stats["api_calls"] = client.api_calls
        error = client.redact(f"{type(exc).__name__}: {exc}")[:1000]
        steps.finish_run(run_id, "failed", stats, error)
        log.error("Run %d failed: %s", run_id, error)
        raise


def log_to_file() -> None:
    """Send the pipeline's log lines to logs/pipeline.log (rotated at 1 MB, 5 old files kept).

    Safe to call more than once. Used by the Prefect flow, whose runs execute in their own process.
    """
    pipeline_log = logging.getLogger("pipeline")
    if any(getattr(h, "baseFilename", None) == str(LOG_FILE) for h in pipeline_log.handlers):
        return
    LOG_FILE.parent.mkdir(exist_ok=True)
    handler = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=5)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    pipeline_log.setLevel(logging.INFO)
    pipeline_log.addHandler(handler)


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
