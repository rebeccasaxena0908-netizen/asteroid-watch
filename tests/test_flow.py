"""The Prefect flow, run for real on Prefect's temporary test server, with fake steps (no NASA, no MySQL)."""

from datetime import datetime, timedelta

import pytest
from prefect.testing.utilities import prefect_test_harness

from flows import daily, serve
from pipeline import steps
from pipeline.extract import ExtractResult
from pipeline.transform import TransformResult


@pytest.fixture(scope="module", autouse=True)
def prefect_server():
    with prefect_test_harness():
        yield


def fake_task(fn):
    return daily.step_task(fn, "fake")


@pytest.fixture
def fakes(monkeypatch):
    calls: list = []

    class Client:
        api_calls = 0

        def redact(self, text):
            return text

    client = Client()
    monkeypatch.setattr(daily, "log_to_file", lambda: None)
    monkeypatch.setattr(steps, "nasa_client", lambda: client)
    replacements = {
        "wait_for_network": lambda max_wait: calls.append(("wait_for_network", max_wait)) or 0.0,
        "check_database": lambda **kw: calls.append("check_database"),
        "recent_success": lambda run_type, within: calls.append("recent_success") or None,
        "start_run": lambda run_type, start, end: calls.append(("start_run", run_type)) or 42,
        "extract": lambda c, start, end: calls.append("extract") or ExtractResult(start=start, end=end),
        "transform": lambda ex: calls.append("transform") or TransformResult(approaches=[{}], records_seen=1),
        "load": lambda clean: calls.append("load") or {"rows_inserted": 0, "rows_updated": 1},
        "check_quality": lambda run_id, ex, clean: calls.append("check_quality") or 0,
        "orbital_lookups": lambda c, limit: calls.append(("orbital_lookups", limit)) or 0,
        "finish_run": lambda run_id, status, stats, error=None: calls.append(("finish_run", status, error)),
    }
    for name, fn in replacements.items():
        monkeypatch.setattr(daily, name, fake_task(fn))
    return calls, monkeypatch


def run_flow(**params):
    return daily.neows_daily.with_options(retries=0)(**params)


def test_success_runs_every_task_in_order(fakes):
    calls, _ = fakes
    result = run_flow()
    names = [c if isinstance(c, str) else c[0] for c in calls]
    assert names == ["wait_for_network", "check_database", "recent_success", "start_run", "extract", "transform",
                     "load", "check_quality", "orbital_lookups", "finish_run"]
    assert calls[3] == ("start_run", "daily") and calls[-1] == ("finish_run", "success", None)
    assert calls[0][1] <= timedelta(hours=2)
    assert result["run_id"] == 42 and result["rows_updated"] == 1


def test_a_recent_success_means_nothing_to_do(fakes):
    calls, monkeypatch = fakes
    monkeypatch.setattr(daily, "recent_success", fake_task(lambda run_type, within: 24))
    assert run_flow() == {"skipped_because_of_run": 24}
    assert "extract" not in calls


def test_a_failed_step_marks_the_run_failed_and_fails_the_flow(fakes):
    calls, monkeypatch = fakes

    def broken(clean):
        raise RuntimeError("load failed")
    monkeypatch.setattr(daily, "load", fake_task(broken))
    with pytest.raises(RuntimeError):
        run_flow()
    assert calls[-1] == ("finish_run", "failed", "RuntimeError: load failed")


def test_mysql_down_fails_before_a_run_is_started(fakes):
    calls, monkeypatch = fakes

    def down(**kw):
        raise steps.DatabaseDown("MySQL not reachable")
    monkeypatch.setattr(daily, "check_database", fake_task(down))
    with pytest.raises(steps.DatabaseDown):
        run_flow()
    assert not any(isinstance(c, tuple) and c[0] == "start_run" for c in calls)


def test_no_attempt_after_the_scheduled_day(fakes):
    calls, monkeypatch = fakes
    monkeypatch.setattr(daily, "end_of_day", lambda moment: datetime(2000, 1, 1))
    with pytest.raises(daily.TooLate):
        run_flow()
    assert calls == []


def test_retry_settings():
    assert (daily.neows_daily.retries, daily.neows_daily.retry_delay_seconds) == (6, 1800)
    assert (daily.extract.retries, daily.extract.retry_delay_seconds) == (3, [60, 300, 900])
    assert daily.wait_for_network.retries == 0          # it waits by itself
    assert daily.check_database.retries == 0            # the whole flow retries 30 minutes later
    assert daily.end_of_day(datetime(2026, 10, 27, 19, 0)) == datetime(2026, 10, 27, 23, 59, 59)


def test_the_deployment_runs_daily_at_19_00_ist():
    deployment = serve.daily_deployment()
    assert deployment.name == "daily-19-ist"
    schedule = deployment.schedules[0].schedule
    assert (schedule.cron, schedule.timezone) == ("0 19 * * *", "Asia/Kolkata")
