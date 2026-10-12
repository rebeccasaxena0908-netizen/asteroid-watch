"""Data quality checks, run after every load and saved to quality_results.

Checks look at this run's batch (what was extracted and transformed), except the two duplicate
checks, which look at the whole close_approaches table. A failed check does not stop the
run: the data is still loaded, and the failure is recorded so it shows on the dashboard.
"""
from dataclasses import dataclass
from datetime import timedelta

from pipeline.extract import ExtractResult
from pipeline.transform import TransformResult


@dataclass
class CheckResult:
    check_name: str
    passed: bool
    details: str


def check_not_null_keys(clean: TransformResult) -> CheckResult:
    bad = len(clean.rejected)
    return CheckResult("not_null_keys", bad == 0,
                       f"{bad} of {clean.records_seen} records missing neo_id, date or epoch")


def check_positive(clean: TransformResult, column: str, name: str) -> CheckResult:
    bad = [a for a in clean.approaches if a[column] is None or a[column] <= 0]
    examples = ", ".join(a["neo_id"] for a in bad[:5])
    return CheckResult(name, not bad, f"{len(bad)} of {len(clean.approaches)} approaches have "
                                      f"{column} missing or <= 0" + (f" (e.g. {examples})" if bad else ""))


def check_diameter_order(clean: TransformResult) -> CheckResult:
    missing = bad = 0
    for a in clean.asteroids:
        low, high = a["est_diameter_min_m"], a["est_diameter_max_m"]
        if low is None or high is None:
            missing += 1
        elif low > high:
            bad += 1
    return CheckResult("diameter_min_le_max", bad == 0,
                       f"{bad} of {len(clean.asteroids)} asteroids have min > max diameter; "
                       f"{missing} have no diameter")


def check_no_duplicates(cur) -> CheckResult:
    cur.execute("SELECT COUNT(*) AS n FROM (SELECT neo_id, epoch_ms FROM close_approaches "
                "GROUP BY neo_id, epoch_ms HAVING COUNT(*) > 1) d")
    dupes = cur.fetchone()["n"]
    return CheckResult("no_duplicate_approaches", dupes == 0,
                       f"{dupes} duplicated (neo_id, epoch_ms) pairs in close_approaches")


# Designation = the text in the last brackets of the name: "614134 (2008 TC4)" -> "2008 TC4".
DESIGNATION_SQL = "SUBSTRING_INDEX(SUBSTRING_INDEX(a.name, '(', -1), ')', 1)"


def check_same_object_under_two_ids(cur) -> CheckResult:
    """NeoWs sometimes lists one asteroid under its old provisional id AND its newer numbered id
    (e.g. 3430309 "(2008 TC4)" and 2614134 "614134 (2008 TC4)"), with identical approaches.
    UNIQUE(neo_id, epoch_ms) can't catch that, so look for one designation + epoch under 2+ ids."""
    cur.execute(f"SELECT COUNT(*) AS n FROM (SELECT {DESIGNATION_SQL} AS designation, ca.epoch_ms "
                "FROM close_approaches ca JOIN asteroids a ON a.neo_id = ca.neo_id "
                "GROUP BY designation, ca.epoch_ms HAVING COUNT(DISTINCT ca.neo_id) > 1) d")
    events = cur.fetchone()["n"]
    return CheckResult("no_same_object_under_two_ids", events == 0,
                       f"{events} approaches stored under two different neo_ids for the same designation")


def check_expected_days(extracted: ExtractResult) -> CheckResult:
    expected = {(extracted.start + timedelta(days=i)).isoformat() for i in range(extracted.days_requested)}
    missing = sorted(expected - extracted.dates_fetched)
    details = f"{len(expected) - len(missing)} of {len(expected)} requested days returned by the API"
    if missing:
        details += f"; missing: {', '.join(missing[:10])}" + (" ..." if len(missing) > 10 else "")
    return CheckResult("expected_days_fetched", not missing, details)


def check_element_count(extracted: ExtractResult, clean: TransformResult) -> CheckResult:
    return CheckResult("row_count_matches_element_count", clean.records_seen == extracted.element_count,
                       f"API element_count {extracted.element_count}, records found {clean.records_seen}")


def run_checks(extracted: ExtractResult, clean: TransformResult, cur=None) -> list[CheckResult]:
    """All checks. Pass cur=None (dry run) to skip the database check."""
    results = [
        check_not_null_keys(clean),
        check_positive(clean, "miss_distance_km", "miss_distance_positive"),
        check_positive(clean, "relative_velocity_kps", "velocity_positive"),
        check_diameter_order(clean),
        check_expected_days(extracted),
        check_element_count(extracted, clean),
    ]
    if cur is not None:
        results.append(check_no_duplicates(cur))
        results.append(check_same_object_under_two_ids(cur))
    return results


def save_results(conn, run_id: int, results: list[CheckResult]) -> int:
    """Insert results for this run; returns the number of failed checks."""
    with conn.cursor() as cur:
        cur.executemany("INSERT INTO quality_results (run_id, check_name, passed, details) "
                        "VALUES (%s, %s, %s, %s)",
                        [(run_id, r.check_name, r.passed, r.details[:500]) for r in results])
    conn.commit()
    return sum(not r.passed for r in results)
