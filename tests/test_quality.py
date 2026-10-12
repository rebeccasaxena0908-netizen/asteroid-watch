import json
from datetime import date
from pathlib import Path

from pipeline.extract import ExtractResult
from pipeline.quality import (check_no_duplicates, check_same_object_under_two_ids, run_checks,
                              save_results)
from pipeline.transform import transform_feeds

FIXTURE = Path(__file__).parent / "fixtures" / "feed_sample.json"


def batch():
    """ExtractResult + TransformResult for the fixture (2026-10-13 .. 2026-10-14, 4 approaches)."""
    payload = json.loads(FIXTURE.read_text())
    extracted = ExtractResult(start=date(2026, 10, 13), end=date(2026, 10, 14), payloads=[payload],
                              element_count=payload["element_count"],
                              dates_fetched=set(payload["near_earth_objects"]))
    return extracted, transform_feeds([payload])


def by_name(results):
    return {r.check_name: r for r in results}


def test_all_checks_pass_on_real_fixture():
    extracted, clean = batch()
    results = run_checks(extracted, clean)

    assert len(results) == 6  # no DB check in a dry run
    assert all(r.passed for r in results), [r for r in results if not r.passed]


def test_detects_missing_days():
    extracted, clean = batch()
    extracted.end = date(2026, 10, 16)  # asked for 4 days, API returned 2

    check = by_name(run_checks(extracted, clean))["expected_days_fetched"]

    assert not check.passed
    assert "2 of 4" in check.details
    assert "2026-10-15, 2026-10-16" in check.details


def test_detects_element_count_mismatch():
    extracted, clean = batch()
    extracted.element_count = 5

    assert not by_name(run_checks(extracted, clean))["row_count_matches_element_count"].passed


def test_detects_bad_distance_and_velocity():
    extracted, clean = batch()
    clean.approaches[0]["miss_distance_km"] = 0
    clean.approaches[1]["relative_velocity_kps"] = None

    checks = by_name(run_checks(extracted, clean))

    assert not checks["miss_distance_positive"].passed
    assert "1 of 4" in checks["miss_distance_positive"].details
    assert not checks["velocity_positive"].passed


def test_detects_diameter_min_greater_than_max():
    extracted, clean = batch()
    clean.asteroids[0]["est_diameter_min_m"] = clean.asteroids[0]["est_diameter_max_m"] + 1
    clean.asteroids[1]["est_diameter_max_m"] = None

    check = by_name(run_checks(extracted, clean))["diameter_min_le_max"]

    assert not check.passed
    assert "1 of 4" in check.details and "1 have no diameter" in check.details


def test_detects_rejected_records():
    extracted, clean = batch()
    clean.rejected.append("approach without date/epoch for 123")

    assert not by_name(run_checks(extracted, clean))["not_null_keys"].passed


class FakeCursor:
    def __init__(self, fetch=None):
        self.fetch = fetch
        self.rows = None

    def execute(self, sql, params=None):
        self.sql = sql

    def fetchone(self):
        return self.fetch

    def executemany(self, sql, rows):
        self.rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeConn:
    def __init__(self):
        self.cur = FakeCursor()
        self.committed = False

    def cursor(self):
        return self.cur

    def commit(self):
        self.committed = True


def test_duplicate_check_uses_database_count():
    assert check_no_duplicates(FakeCursor({"n": 0})).passed
    failed = check_no_duplicates(FakeCursor({"n": 3}))
    assert not failed.passed and "3 duplicated" in failed.details


def test_same_object_check_uses_designation_and_epoch():
    cur = FakeCursor({"n": 57})
    check = check_same_object_under_two_ids(cur)
    assert not check.passed and "57 approaches" in check.details
    assert "ABS(c2.epoch_ms - c1.epoch_ms)" in cur.sql
    assert check_same_object_under_two_ids(FakeCursor({"n": 0})).passed


def test_save_results_returns_failure_count():
    extracted, clean = batch()
    extracted.element_count = 99
    conn = FakeConn()

    failures = save_results(conn, 7, run_checks(extracted, clean))

    assert failures == 1
    assert conn.committed
    assert len(conn.cur.rows) == 6 and all(row[0] == 7 for row in conn.cur.rows)
