"""Cross-check our NeoWs data against NASA JPL's Close-Approach Data (CAD) API (no key needed).

Two checks:
1. Values: for a random sample of stored approaches, ask CAD for the same object (by SPK-ID,
   which is what NeoWs uses as neo_id) around the same date, and compare miss distance,
   velocity and time.
2. Coverage: for some days, compare how many approaches NeoWs gave us with how many CAD lists
   within the same distance limit. Includes every day the NeoWs feed left out.

Results are saved as a 'crosscheck' run in pipeline_runs + quality_results (so the dashboard
can show them) and written to docs/jpl_crosscheck.md for the report.

Usage: python -m pipeline.jpl_crosscheck --sample 50 --days 10
"""
import argparse
import logging
import random
import statistics
import time
from datetime import date, datetime, timedelta

from pipeline.config import PROJECT_ROOT
from pipeline.db import connect
from pipeline.extract import ExtractError, NeoWsClient
from pipeline.quality import CheckResult, save_results
from pipeline.transform import parse_approach_datetime, to_float

log = logging.getLogger("pipeline.jpl")

CAD_URL = "https://ssd-api.jpl.nasa.gov/cad.api"
REPORT = PROJECT_ROOT / "docs" / "jpl_crosscheck.md"
DIST_TOLERANCE = 0.01          # 1% relative difference
VELOCITY_TOLERANCE = 0.01
TIME_TOLERANCE_MIN = 10
SEED = 42                      # same sample every time, so results are reproducible
PAUSE_SECONDS = 1.0            # be polite to a free API


def cad_rows(payload: dict) -> list[dict]:
    """CAD returns {"fields": [...], "data": [[...], ...]}; turn it into a list of dicts."""
    fields = payload.get("fields", [])
    return [dict(zip(fields, row, strict=False)) for row in payload.get("data", [])]


def relative_diff(ours: float | None, theirs: float | None) -> float | None:
    if ours is None or theirs is None or theirs == 0:
        return None
    return abs(ours - theirs) / abs(theirs)


def compare_approach(row: dict, cad: list[dict]) -> dict:
    """Compare one stored approach with the CAD rows for that object (nearest in time wins)."""
    result = {"neo_id": row["neo_id"], "name": row["name"], "date": row["approach_date"],
              "status": "not_in_jpl", "dist_diff": None, "vel_diff": None, "time_diff_min": None}
    candidates = [(c, parse_approach_datetime(c.get("cd"))) for c in cad]
    candidates = [(c, t) for c, t in candidates if t is not None]
    if not candidates or row["approach_datetime"] is None:
        return result
    best, when = min(candidates, key=lambda ct: abs(ct[1] - row["approach_datetime"]))
    result["time_diff_min"] = abs(when - row["approach_datetime"]).total_seconds() / 60
    result["dist_diff"] = relative_diff(row["miss_distance_au"], to_float(best.get("dist")))
    result["vel_diff"] = relative_diff(row["relative_velocity_kps"], to_float(best.get("v_rel")))
    ok = (result["dist_diff"] is not None and result["dist_diff"] <= DIST_TOLERANCE
          and result["vel_diff"] is not None and result["vel_diff"] <= VELOCITY_TOLERANCE
          and result["time_diff_min"] <= TIME_TOLERANCE_MIN)
    result["status"] = "match" if ok else "differs"
    return result


def cad_count_on_day(cad: list[dict], day: date) -> int:
    prefix = day.strftime("%Y-%b-%d")   # CAD dates look like "2026-Jan-19 02:27"
    return sum(1 for c in cad if str(c.get("cd", "")).startswith(prefix))


def sample_approaches(cur, n: int) -> list[dict]:
    cur.execute("SELECT ca.neo_id, a.name, ca.approach_date, ca.approach_datetime, ca.miss_distance_au, "
                "ca.relative_velocity_kps FROM close_approaches ca JOIN asteroids a ON a.neo_id = ca.neo_id "
                "ORDER BY RAND(%s) LIMIT %s", (SEED, n))
    return cur.fetchall()


def coverage_days(cur, n_random: int) -> tuple[list[date], dict[date, int]]:
    """Days the feed left out (count 0) plus a reproducible random sample of other days."""
    cur.execute("SELECT MIN(approach_date) AS first, MAX(approach_date) AS last FROM close_approaches")
    span = cur.fetchone()
    cur.execute("SELECT approach_date, approach_count FROM v_daily_counts")
    counts = {r["approach_date"]: r["approach_count"] for r in cur.fetchall()}
    all_days = [span["first"] + timedelta(days=i) for i in range((span["last"] - span["first"]).days + 1)]
    missing = [d for d in all_days if d not in counts]
    present = sorted(random.Random(SEED).sample(sorted(counts), min(n_random, len(counts))))
    return missing + present, counts


def run_crosscheck(sample_size: int, n_days: int) -> None:
    client = NeoWsClient(api_key="", base_url=CAD_URL)   # same retrying HTTP client, no key
    conn = connect()
    with conn.cursor() as cur:
        cur.execute("SELECT MAX(miss_distance_au) AS m FROM close_approaches")
        dist_max = round(cur.fetchone()["m"] + 0.0005, 3)   # NeoWs feed's distance limit, rounded up
        sample = sample_approaches(cur, sample_size)
        days, neows_counts = coverage_days(cur, n_days)
        cur.execute("INSERT INTO pipeline_runs (run_type, status, date_range_start, date_range_end) "
                    "VALUES ('crosscheck', 'running', %s, %s)",
                    (min(r["approach_date"] for r in sample), max(r["approach_date"] for r in sample)))
        run_id = cur.lastrowid
    conn.commit()
    log.info("Cross-check run %d: %d approaches, %d days, dist-max %s au", run_id, len(sample), len(days), dist_max)
    try:
        compared, coverage = fetch_and_compare(client, sample, days, neows_counts, dist_max)
    except Exception as exc:
        with conn.cursor() as cur:
            cur.execute("UPDATE pipeline_runs SET finished_at = NOW(), status = 'failed', api_calls = %s, "
                        "error_message = %s WHERE run_id = %s",
                        (client.api_calls, f"{type(exc).__name__}: {exc}"[:1000], run_id))
        conn.commit()
        conn.close()
        raise

    checks = summarise(compared, coverage)
    failures = save_results(conn, run_id, checks)
    with conn.cursor() as cur:
        cur.execute("UPDATE pipeline_runs SET finished_at = NOW(), status = 'success', api_calls = %s, "
                    "records_extracted = %s, quality_failures = %s WHERE run_id = %s",
                    (client.api_calls, len(sample), failures, run_id))
    conn.commit()
    conn.close()
    write_report(run_id, compared, coverage, checks, dist_max)
    for c in checks:
        log.info("%s %s: %s", "PASS" if c.passed else "FAIL", c.check_name, c.details)
    log.info("Report written to %s", REPORT.relative_to(PROJECT_ROOT))


def fetch_and_compare(client, sample, days, neows_counts, dist_max):
    # 1. Values
    compared = []
    for row in sample:
        params = {"spk": row["neo_id"], "dist-max": "1",
                  "date-min": (row["approach_date"] - timedelta(days=1)).isoformat(),
                  "date-max": (row["approach_date"] + timedelta(days=2)).isoformat()}
        try:
            cad = cad_rows(client.get_json("", params))
        except ExtractError as exc:      # CAD answers HTTP 400 "object not found" for unknown ids
            log.info("Not in JPL CAD: %s %s (%s)", row["neo_id"], row["name"], str(exc)[:80])
            cad = []
        compared.append(compare_approach(row, cad))
        time.sleep(PAUSE_SECONDS)

    # 2. Coverage. date-max is exclusive in practice, so ask for [day, day + 1).
    coverage = []
    for day in days:
        cad = cad_rows(client.get_json("", {"date-min": day.isoformat(),
                                            "date-max": (day + timedelta(days=1)).isoformat(),
                                            "dist-max": str(dist_max)}))
        coverage.append({"day": day, "neows": neows_counts.get(day, 0), "jpl": cad_count_on_day(cad, day)})
        time.sleep(PAUSE_SECONDS)
    return compared, coverage


def summarise(compared: list[dict], coverage: list[dict]) -> list[CheckResult]:
    found = [c for c in compared if c["status"] != "not_in_jpl"]
    matched = [c for c in found if c["status"] == "match"]
    neows_total = sum(c["neows"] for c in coverage)
    jpl_total = sum(c["jpl"] for c in coverage)
    feed_missing = [c for c in coverage if c["neows"] == 0]
    return [
        CheckResult("jpl_objects_found", len(found) == len(compared),
                    f"{len(found)} of {len(compared)} sampled approaches found in JPL CAD"),
        CheckResult("jpl_values_match", len(matched) == len(found),
                    f"{len(matched)} of {len(found)} found approaches match JPL within 1% distance, "
                    f"1% velocity, {TIME_TOLERANCE_MIN} min"),
        CheckResult("jpl_daily_coverage", neows_total >= jpl_total,
                    f"NeoWs has {neows_total} approaches vs JPL {jpl_total} on {len(coverage)} sampled days "
                    f"({len(feed_missing)} of them missing from the NeoWs feed)"),
    ]


def fmt_pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.4f}%"


def write_report(run_id, compared, coverage, checks, dist_max) -> None:
    found = [c for c in compared if c["dist_diff"] is not None]
    lines = [
        "# JPL cross-check report",
        "",
        f"Generated by `python -m pipeline.jpl_crosscheck` on {datetime.now():%Y-%m-%d %H:%M} "
        f"(pipeline run {run_id}). Source: [JPL SBDB Close-Approach Data API](https://ssd-api.jpl.nasa.gov/doc/cad.html).",
        "",
        "## Summary",
        "",
        "| Check | Result | Details |",
        "|---|---|---|",
        *[f"| `{c.check_name}` | {'PASS' if c.passed else 'FAIL'} | {c.details} |" for c in checks],
        "",
        "## 1. Values: NeoWs vs JPL for a random sample of approaches",
        "",
    ]
    if found:
        dist = [c["dist_diff"] for c in found]
        vel = [c["vel_diff"] for c in found if c["vel_diff"] is not None]
        mins = [c["time_diff_min"] for c in found]
        lines += [f"- Miss distance difference: median {fmt_pct(statistics.median(dist))}, max {fmt_pct(max(dist))}",
                  f"- Velocity difference: median {fmt_pct(statistics.median(vel))}, max {fmt_pct(max(vel))}",
                  f"- Time difference: median {statistics.median(mins):.1f} min, max {max(mins):.1f} min", ""]
    lines += ["| neo_id | Name | Date | Status | Distance diff | Velocity diff | Time diff (min) |",
              "|---|---|---|---|---|---|---|"]
    for c in compared:
        t = "n/a" if c["time_diff_min"] is None else f"{c['time_diff_min']:.1f}"
        lines.append(f"| {c['neo_id']} | {c['name']} | {c['date']} | {c['status']} | "
                     f"{fmt_pct(c['dist_diff'])} | {fmt_pct(c['vel_diff'])} | {t} |")
    lines += ["", f"## 2. Coverage: approaches per day within {dist_max} AU", "",
              "Days with 0 from NeoWs are dates the NeoWs feed left out of its response entirely.", "",
              "| Day | NeoWs (our DB) | JPL CAD |", "|---|---|---|"]
    lines += [f"| {c['day']} | {c['neows']} | {c['jpl']} |" for c in coverage]
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Cross-check stored approaches against JPL CAD")
    parser.add_argument("--sample", type=int, default=50, help="approaches to compare (default 50)")
    parser.add_argument("--days", type=int, default=10, help="random days for the coverage check (default 10)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    run_crosscheck(args.sample, args.days)


if __name__ == "__main__":
    main()
