from datetime import datetime, timedelta

import pytest
from typer.testing import CliRunner

from pipeline import cli, jpl_crosscheck, run_pipeline

runner = CliRunner()


@pytest.fixture
def pipeline_calls(monkeypatch):
    calls = []

    def fake_main(argv):
        calls.append(argv)
        return 0

    monkeypatch.setattr(run_pipeline, "main", fake_main)
    return calls


def options(argv: list[str]) -> dict:
    """['--a', '1', '--dry-run'] -> {'--a': '1', '--dry-run': True}"""
    out: dict[str, str | bool] = {}
    i = 0
    while i < len(argv):
        if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
            out[argv[i]] = argv[i + 1]
            i += 2
        else:
            out[argv[i]] = True
            i += 1
    return out


@pytest.mark.parametrize("command, expected", [
    (["run"], {"--backfill-days": "1", "--forward-days": "7", "--orbital-limit": "100", "--run-type": "manual"}),
    (["quick-run"], {"--backfill-days": "1", "--forward-days": "7", "--orbital-limit": "0", "--run-type": "manual"}),
    (["backfill"], {"--backfill-days": "365", "--forward-days": "30", "--orbital-limit": "500",
                    "--run-type": "backfill"}),
    (["run", "--backfill-days", "3", "--run-type", "daily", "--dry-run"],
     {"--backfill-days": "3", "--forward-days": "7", "--orbital-limit": "100", "--run-type": "daily",
      "--dry-run": True}),
])
def test_pipeline_commands_pass_the_same_options_as_the_v1_make_targets(pipeline_calls, command, expected):
    result = runner.invoke(cli.app, command)
    assert result.exit_code == 0, result.output
    assert options(pipeline_calls[0]) == expected


def test_pipeline_failure_gives_exit_code_1(monkeypatch):
    monkeypatch.setattr(run_pipeline, "main", lambda argv: 1)
    assert runner.invoke(cli.app, ["quick-run"]).exit_code == 1


def test_crosscheck_passes_sample_and_days(monkeypatch):
    calls = []
    monkeypatch.setattr(jpl_crosscheck, "main", calls.append)
    assert runner.invoke(cli.app, ["crosscheck", "--sample", "5"]).exit_code == 0
    assert calls == [["--sample", "5", "--days", "10"]]


def test_test_command_runs_offline_tests_or_api_tests(monkeypatch):
    calls = []

    class Done:
        returncode = 0

    monkeypatch.setattr(cli.subprocess, "run", lambda args: calls.append(args) or Done())
    runner.invoke(cli.app, ["test"])
    runner.invoke(cli.app, ["test", "--api"])
    runner.invoke(cli.app, ["test", "--parity"])
    assert calls[0][-2:] == ["--ignore=tests/integration", "--ignore=tests/parity"]
    assert calls[1][-1] == "tests/integration"
    assert calls[2][-1] == "tests/parity"


def test_serve_runs_uvicorn_with_one_worker_on_localhost(monkeypatch):
    import uvicorn

    calls = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: calls.append((app, kwargs)))
    result = runner.invoke(cli.app, ["serve"])
    assert result.exit_code == 0, result.output
    app, kwargs = calls[0]
    assert app == "api.main:app"
    assert (kwargs["host"], kwargs["port"], kwargs["workers"]) == ("127.0.0.1", 8010, 1)


def test_status_without_mysql_gives_a_short_message(monkeypatch):
    import pipeline.db

    def no_database(*args, **kwargs):
        raise ConnectionRefusedError("refused")

    monkeypatch.setattr(pipeline.db, "engine", no_database)
    result = runner.invoke(cli.app, ["status"])
    assert result.exit_code == 1
    assert "Is XAMPP MySQL running?" in result.output


def test_error_display_never_shows_local_variables():
    # Local variables can hold database passwords.
    assert cli.app.pretty_exceptions_show_locals is False


def test_age_text_and_staleness():
    now = datetime(2026, 10, 27, 12, 0)
    assert cli.age_text(None, now) == "-"
    assert cli.age_text(now - timedelta(minutes=17), now) == "17 min ago"
    assert cli.age_text(now - timedelta(hours=5), now) == "5 h ago"
    assert cli.age_text(now - timedelta(days=14), now) == "14 d ago"
    assert not cli.is_stale(now - timedelta(hours=25), now)
    assert cli.is_stale(now - timedelta(hours=27), now)
    assert cli.is_stale(None, now)


def test_launchd_agent_uses_the_cli_default_port():
    import plistlib

    from pipeline.config import PROJECT_ROOT

    plist = plistlib.loads((PROJECT_ROOT / "scheduler" / "com.asteroidwatch.api.plist").read_bytes())
    args = plist["ProgramArguments"]
    assert args[args.index("--port") + 1] == str(cli.DEFAULT_PORT) == "8010"
    assert args[args.index("--host") + 1] == "127.0.0.1"
