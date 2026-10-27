"""The pipeline steps' failure handling (no network, no database) and the manual-run orchestration."""

import json
from argparse import Namespace
from datetime import date, timedelta

import pytest

from pipeline import run_pipeline, steps
from pipeline.extract import ExtractError, ExtractResult
from pipeline.transform import TransformResult

KEY = "TEST_KEY_123"


class FakeClock:
    """time.time and time.sleep for tests: sleeping moves the clock, plus any extra 'Mac asleep' time."""

    def __init__(self, asleep_after_first_sleep: float = 0):
        self.t = 1_000_000.0
        self.sleeps: list[float] = []
        self.asleep = asleep_after_first_sleep

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += seconds + self.asleep
        self.asleep = 0


def test_wait_for_network_checks_every_interval_until_reachable():
    clock = FakeClock()
    answers = iter([False, False, True])
    waited = steps.wait_for_network(timedelta(hours=2), timedelta(minutes=5), lambda: next(answers),
                                    clock.sleep, clock.now)
    assert clock.sleeps == [300, 300]
    assert waited == 600


def test_wait_for_network_gives_up_after_the_maximum_wait():
    clock = FakeClock()
    with pytest.raises(steps.NetworkDown):
        steps.wait_for_network(timedelta(minutes=12), timedelta(minutes=5), lambda: False, clock.sleep, clock.now)
    assert clock.sleeps == [300, 300, 120]   # never sleeps past the deadline


def test_time_asleep_counts_and_the_network_is_checked_again_on_wake():
    # The Mac sleeps for 3 hours during the first wait; on waking, the network is back.
    clock = FakeClock(asleep_after_first_sleep=3 * 3600)
    answers = iter([False, True])
    waited = steps.wait_for_network(timedelta(hours=2), timedelta(minutes=5), lambda: next(answers),
                                    clock.sleep, clock.now)
    assert waited == 300 + 3 * 3600


def test_reachable_immediately_does_not_wait():
    clock = FakeClock()
    assert steps.wait_for_network(reachable=lambda: True, sleep=clock.sleep, now=clock.now) == 0
    assert clock.sleeps == []


def test_mysql_down_is_written_to_the_local_failure_log(tmp_path, monkeypatch):
    monkeypatch.setattr(steps, "FAILURE_LOG", tmp_path / "failed_attempts.log")

    def refused(*args, **kwargs):
        raise ConnectionRefusedError("password=secret-value")   # must not end up in the log
    monkeypatch.setattr(steps, "connect", refused)

    with pytest.raises(steps.DatabaseDown, match="Is XAMPP MySQL running"):
        steps.check_database(run_type="daily", flow_run="eager-wasp")
    text = (tmp_path / "failed_attempts.log").read_text()
    entry = json.loads(text)
    assert entry["reason"] == "MySQL not reachable (ConnectionRefusedError)"
    assert (entry["run_type"], entry["flow_run"]) == ("daily", "eager-wasp")
    assert "secret-value" not in text
    assert steps.recent_failed_attempts() == [entry]


def test_recent_failed_attempts_ignores_old_entries(tmp_path, monkeypatch):
    log = tmp_path / "failed_attempts.log"
    monkeypatch.setattr(steps, "FAILURE_LOG", log)
    log.write_text('{"time": "2020-01-01T19:00:00", "reason": "old"}\n')
    steps.record_failed_attempt("new")
    assert [e["reason"] for e in steps.recent_failed_attempts(days=7)] == ["new"]


def test_date_window():
    assert steps.date_window(1, 7, date(2026, 10, 27)) == (date(2026, 10, 26), date(2026, 11, 3))


class FakeClient:
    def __init__(self):
        self.api_calls = 0

    def redact(self, text: str) -> str:
        return text.replace(KEY, "REDACTED")


@pytest.fixture
def fake_steps(monkeypatch):
    """Replace every step that touches NASA or MySQL; record the calls."""
    calls: list = []
    client = FakeClient()
    clean = TransformResult(approaches=[{}, {}], records_seen=3)
    monkeypatch.setattr(steps, "nasa_client", lambda settings=None: client)
    monkeypatch.setattr(steps, "check_database", lambda **kw: calls.append("check_database"))
    monkeypatch.setattr(steps, "start_run", lambda *a: calls.append("start_run") or 77)

    def extract(c, start, end):
        calls.append("extract")
        c.api_calls += 2
        return ExtractResult(start=start, end=end)
    monkeypatch.setattr(steps, "extract", extract)
    monkeypatch.setattr(steps, "transform", lambda ex: calls.append("transform") or clean)
    monkeypatch.setattr(steps, "load", lambda cl: calls.append("load") or {"rows_inserted": 1, "rows_updated": 0})
    monkeypatch.setattr(steps, "check_quality", lambda run_id, ex, cl: calls.append("check_quality") or 0)

    def orbits(c, limit):
        calls.append(("orbital_lookups", limit))
        c.api_calls += limit
        return limit
    monkeypatch.setattr(steps, "orbital_lookups", orbits)
    monkeypatch.setattr(steps, "finish_run", lambda *a: calls.append(("finish_run", *a)))
    return calls, client


ARGS = Namespace(backfill_days=1, forward_days=7, orbital_limit=5, run_type="manual", dry_run=False)


def test_manual_run_calls_the_steps_in_order(fake_steps):
    calls, _ = fake_steps
    stats = run_pipeline.run(ARGS, today=date(2026, 10, 27))
    assert calls[:6] == ["check_database", "start_run", "extract", "transform", "load", "check_quality"]
    assert calls[6] == ("orbital_lookups", 5)
    assert calls[7] == ("finish_run", 77, "success", stats)
    assert stats == {"records_extracted": 3, "records_after_dedupe": 2, "rows_inserted": 1, "rows_updated": 0,
                     "quality_failures": 0, "api_calls": 7}


def test_failed_run_is_recorded_with_api_calls_and_a_redacted_error(fake_steps, monkeypatch):
    calls, client = fake_steps

    def failing_extract(c, start, end):
        c.api_calls += 5
        raise ExtractError(f"Gave up on /feed?api_key={KEY} after 5 attempts")
    monkeypatch.setattr(steps, "extract", failing_extract)
    with pytest.raises(ExtractError):
        run_pipeline.run(ARGS, today=date(2026, 10, 27))
    _, run_id, status, stats, error = calls[-1]
    assert (run_id, status, stats["api_calls"]) == (77, "failed", 5)
    assert KEY not in error and "REDACTED" in error
