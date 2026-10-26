"""Integration tests: the API's answers checked against direct SQL.

v2: every test runs against the FastAPI API (in-process, always) and, when it is deployed
(`make legacy-deploy`), against the legacy PHP API too, so both are held to the same checks.
Needs XAMPP MySQL. Run with `make api-test`. Not part of `make test` (which stays offline).
"""
import csv
import io

import pytest
import requests
from fastapi.testclient import TestClient

from api.main import app
from pipeline.db import connect

PHP_BASE = "http://localhost/asteroid-watch/api"
fastapi = TestClient(app, raise_server_exceptions=False)


def php_reachable() -> bool:
    try:
        return requests.get(f"{PHP_BASE}/summary.php", timeout=3).status_code == 200
    except requests.RequestException:
        return False


def mysql_reachable() -> bool:
    try:
        connect().close()
        return True
    except Exception:
        return False


PHP_UP = php_reachable()
pytestmark = pytest.mark.skipif(not mysql_reachable(), reason="MySQL not reachable (XAMPP off)")


@pytest.fixture(params=["fastapi", pytest.param("php", marks=pytest.mark.skipif(
    not PHP_UP, reason="legacy PHP API not deployed (make legacy-deploy)"))])
def target(request):
    return request.param


def get(target, endpoint, expected_status=200, **params):
    if target == "php":
        r = requests.get(f"{PHP_BASE}/{endpoint}.php", params=params, timeout=10)
    else:
        r = fastapi.get(f"/api/{endpoint}", params=params)
    assert r.status_code == expected_status, r.text
    assert r.headers["Content-Type"].startswith("application/json")
    return r.json()


def sql_one(sql, params=None):
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def test_summary_totals_match_database(target):
    t = get(target, "summary")["data"]["totals"]
    db = sql_one("SELECT (SELECT COUNT(*) FROM asteroids) a, (SELECT COUNT(*) FROM close_approaches) c, "
                 "(SELECT COUNT(*) FROM asteroids WHERE is_potentially_hazardous) h, "
                 "(SELECT COUNT(*) FROM orbital_data) o")
    assert (t["asteroids"], t["approaches"], t["hazardous_asteroids"], t["asteroids_with_orbits"]) == \
           (db["a"], db["c"], db["h"], db["o"])


def test_summary_last_run_is_latest_etl_run(target):
    last = get(target, "summary")["data"]["last_run"]
    db = sql_one("SELECT MAX(run_id) AS r FROM pipeline_runs WHERE run_type <> 'crosscheck'")
    assert last["run_id"] == db["r"]


def test_approaches_filter_count_and_sort(target):
    d = get(target, "approaches", start="2026-10-12", hazardous="true", sort="distance", per_page=100)["data"]
    db = sql_one("SELECT COUNT(*) n FROM close_approaches ca JOIN asteroids a USING (neo_id) "
                 "WHERE ca.approach_date >= '2026-10-12' AND a.is_potentially_hazardous")
    assert d["total"] == db["n"]
    assert all(i["is_potentially_hazardous"] is True for i in d["items"])
    distances = [i["miss_distance_km"] for i in d["items"]]
    assert distances == sorted(distances)


def test_approaches_pagination(target):
    p1 = get(target, "approaches", per_page=10, page=1)["data"]
    p2 = get(target, "approaches", per_page=10, page=2)["data"]
    assert len(p1["items"]) == 10 and p1["total_pages"] == -(-p1["total"] // 10)
    assert not {i["approach_id"] for i in p1["items"]} & {i["approach_id"] for i in p2["items"]}


def test_search_is_safe_and_literal(target):
    assert get(target, "approaches", q="2008 TC4")["data"]["total"] == 1
    assert get(target, "approaches", q="%")["data"]["total"] == 0          # wildcard matched literally
    assert get(target, "approaches", q="' OR '1'='1")["data"]["total"] == 0  # injection attempt is just text
    assert sql_one("SELECT COUNT(*) n FROM asteroids")["n"] > 0


def test_asteroid_detail_and_old_id_resolution(target):
    d = get(target, "asteroid", id="2614134")["data"]
    assert d["asteroid"]["name"] == "614134 (2008 TC4)"
    assert len(d["approaches"]) == sql_one("SELECT COUNT(*) n FROM close_approaches WHERE neo_id='2614134'")["n"]
    assert "3430309" in d["old_ids"]

    old = get(target, "asteroid", id="3430309")["data"]
    assert old["resolved_from"] == "3430309" and old["asteroid"]["neo_id"] == "2614134"


def test_asteroid_not_found_and_bad_method(target):
    assert "No asteroid" in get(target, "asteroid", expected_status=404, id="1")["error"]
    if target == "php":
        assert requests.post(f"{PHP_BASE}/summary.php", timeout=10).status_code == 405
    else:
        assert fastapi.post("/api/summary").status_code == 405
    assert get(target, "approaches", expected_status=400, page="0")["error"]


def test_trends_add_up(target):
    d = get(target, "trends")["data"]
    total = sql_one("SELECT COUNT(*) n FROM close_approaches")["n"]
    assert sum(day["approach_count"] for day in d["daily"]) == total
    assert len(d["velocity_vs_distance"]) == total
    with_size = sql_one("SELECT COUNT(DISTINCT a.neo_id) n FROM asteroids a JOIN close_approaches ca USING (neo_id) "
                        "WHERE a.est_diameter_max_m IS NOT NULL")["n"]
    assert sum(b["count"] for b in d["size_histogram"]) == with_size
    assert [b["label"] for b in d["size_histogram"]][:2] == ["0–10 m", "10–25 m"]
    assert sum(h["approach_count"] for h in d["hazardous_split"]) == total


def test_runs_with_quality_results(target):
    runs = get(target, "runs", limit=3)["data"]["runs"]
    assert [r["run_id"] for r in runs] == sorted((r["run_id"] for r in runs), reverse=True)
    for r in runs:
        n = sql_one("SELECT COUNT(*) n FROM quality_results WHERE run_id = %s", (r["run_id"],))["n"]
        assert len(r["quality"]) == n
        assert r["quality_failures"] == sum(not q["passed"] for q in r["quality"])


@pytest.mark.skipif(not PHP_UP, reason="legacy PHP API not deployed (make legacy-deploy)")
def test_includes_are_not_served():
    assert requests.get("http://localhost/asteroid-watch/includes/db.php", timeout=10).status_code == 403


def test_exports_match_the_table_and_the_run_log():
    r = fastapi.get("/api/approaches.csv", params={"hazardous": "true", "start": "2026-01-01"})
    rows = list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))))
    n = sql_one("SELECT COUNT(*) n FROM close_approaches ca JOIN asteroids a USING (neo_id) "
                "WHERE ca.approach_date >= '2026-01-01' AND a.is_potentially_hazardous")["n"]
    assert len(rows) == n and all(row["is_potentially_hazardous"] == "yes" for row in rows)
    runs = fastapi.get("/api/runs.csv").content.decode("utf-8-sig").splitlines()
    assert len(runs) - 1 == sql_one("SELECT COUNT(*) n FROM pipeline_runs")["n"]
