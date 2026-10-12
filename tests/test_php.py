"""PHP API checks that need no database or web server: lint, input validation, MySQL-down errors."""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from pipeline.config import PROJECT_ROOT

PHP = shutil.which("php") or "/Applications/XAMPP/xamppfiles/bin/php"
DASHBOARD = PROJECT_ROOT / "dashboard"
pytestmark = pytest.mark.skipif(not Path(PHP).exists(), reason="PHP CLI not installed")


def run_endpoint(name: str, query: str, tmp_path: Path, config: str | None = None) -> dict:
    """Run an endpoint with the PHP CLI, with $_GET filled from a query string."""
    env = {**os.environ, "ASTEROID_WATCH_CONFIG": str(tmp_path / "missing.ini")}
    if config is not None:
        ini = tmp_path / "db.ini"
        ini.write_text(config)
        env["ASTEROID_WATCH_CONFIG"] = str(ini)
    code = f'parse_str({json.dumps(query)}, $_GET); include {json.dumps(str(DASHBOARD / "api" / name))};'
    out = subprocess.run([PHP, "-d", "display_errors=0", "-r", code], env=env,
                         capture_output=True, text=True, timeout=30)
    return json.loads(out.stdout)


def test_all_php_files_lint():
    files = sorted(DASHBOARD.rglob("*.php"))
    assert files
    for f in files:
        result = subprocess.run([PHP, "-l", str(f)], capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("name, query, message", [
    ("approaches.php", "page=0", "'page' must be a whole number"),
    ("approaches.php", "per_page=500", "'per_page' must be a whole number from 1 to 100"),
    ("approaches.php", "sort=miss_distance_km;DROP", "'sort' must be one of"),
    ("approaches.php", "start=2026-13-01", "'start' must be a date"),
    ("approaches.php", "start=2026-10-12&end=2026-10-01", "'start' must be on or before 'end'"),
    ("approaches.php", "hazardous=yes", "'hazardous' must be one of"),
    ("asteroid.php", "id=1%20OR%201=1", "'id' is required and must be a numeric neo_id"),
    ("asteroid.php", "", "'id' is required"),
    ("runs.php", "limit=abc", "'limit' must be a whole number"),
    ("trends.php", "end=yesterday", "'end' must be a date"),
])
def test_bad_input_is_rejected_before_any_query(name, query, message, tmp_path):
    body = run_endpoint(name, query, tmp_path)   # no config file: proves no DB access happened
    assert message in body["error"]


def test_missing_config_gives_friendly_error(tmp_path):
    body = run_endpoint("summary.php", "", tmp_path)
    assert body == {"error": "Dashboard database config not found. Run `make deploy`."}


def test_mysql_down_gives_friendly_error(tmp_path):
    # Nothing listens on port 1, and the socket doesn't exist: the same failure as MySQL being off.
    config = 'socket = "/nonexistent.sock"\nhost = "127.0.0.1"\nport = 1\ndbname = "x"\nuser = "x"\npassword = "x"\n'
    body = run_endpoint("summary.php", "", tmp_path, config)
    assert body == {"error": "Cannot connect to MySQL. Is XAMPP MySQL running?"}
