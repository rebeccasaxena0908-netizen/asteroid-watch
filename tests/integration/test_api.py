"""Integration tests: the deployed PHP API (http://localhost/asteroid-watch) against direct SQL.

Needs XAMPP Apache + MySQL running and `make deploy`. Run with `make api-test`.
Skipped automatically when the API isn't reachable. Not part of `make test` (which stays offline).
"""
import pytest
import requests

from pipeline.db import connect

BASE = "http://localhost/asteroid-watch/api"


def api_reachable() -> bool:
    try:
        return requests.get(f"{BASE}/summary.php", timeout=3).status_code == 200
    except requests.RequestException:
        return False


pytestmark = pytest.mark.skipif(not api_reachable(), reason="dashboard API not reachable (XAMPP off or not deployed)")


def get(endpoint, expected_status=200, **params):
    r = requests.get(f"{BASE}/{endpoint}", params=params, timeout=10)
    assert r.status_code == expected_status, r.text
    assert r.headers["Content-Type"].startswith("application/json")
    return r.json()


def sql_one(sql, params=None):
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def test_summary_totals_match_database():
    t = get("summary.php")["data"]["totals"]
    db = sql_one("SELECT (SELECT COUNT(*) FROM asteroids) a, (SELECT COUNT(*) FROM close_approaches) c, "
                 "(SELECT COUNT(*) FROM asteroids WHERE is_potentially_hazardous) h, "
                 "(SELECT COUNT(*) FROM orbital_data) o")
    assert (t["asteroids"], t["approaches"], t["hazardous_asteroids"], t["asteroids_with_orbits"]) == \
           (db["a"], db["c"], db["h"], db["o"])


def test_summary_last_run_is_latest_etl_run():
    last = get("summary.php")["data"]["last_run"]
    db = sql_one("SELECT MAX(run_id) AS r FROM pipeline_runs WHERE run_type <> 'crosscheck'")
    assert last["run_id"] == db["r"]


def test_approaches_filter_count_and_sort():
    d = get("approaches.php", start="2026-10-12", hazardous="true", sort="distance", per_page=100)["data"]
    db = sql_one("SELECT COUNT(*) n FROM close_approaches ca JOIN asteroids a USING (neo_id) "
                 "WHERE ca.approach_date >= '2026-10-12' AND a.is_potentially_hazardous")
    assert d["total"] == db["n"]
    assert all(i["is_potentially_hazardous"] is True for i in d["items"])
    distances = [i["miss_distance_km"] for i in d["items"]]
    assert distances == sorted(distances)


def test_approaches_pagination():
    p1 = get("approaches.php", per_page=10, page=1)["data"]
    p2 = get("approaches.php", per_page=10, page=2)["data"]
    assert len(p1["items"]) == 10 and p1["total_pages"] == -(-p1["total"] // 10)
    assert not {i["approach_id"] for i in p1["items"]} & {i["approach_id"] for i in p2["items"]}


def test_search_is_safe_and_literal():
    assert get("approaches.php", q="2008 TC4")["data"]["total"] == 1
    assert get("approaches.php", q="%")["data"]["total"] == 0          # wildcard matched literally
    assert get("approaches.php", q="' OR '1'='1")["data"]["total"] == 0  # injection attempt is just text
    assert sql_one("SELECT COUNT(*) n FROM asteroids")["n"] > 0


def test_asteroid_detail_and_old_id_resolution():
    d = get("asteroid.php", id="2614134")["data"]
    assert d["asteroid"]["name"] == "614134 (2008 TC4)"
    assert len(d["approaches"]) == sql_one("SELECT COUNT(*) n FROM close_approaches WHERE neo_id='2614134'")["n"]
    assert "3430309" in d["old_ids"]

    old = get("asteroid.php", id="3430309")["data"]
    assert old["resolved_from"] == "3430309" and old["asteroid"]["neo_id"] == "2614134"


def test_asteroid_not_found_and_bad_method():
    assert "No asteroid" in get("asteroid.php", expected_status=404, id="1")["error"]
    assert requests.post(f"{BASE}/summary.php", timeout=10).status_code == 405
    assert get("approaches.php", expected_status=400, page="0")["error"]


def test_trends_add_up():
    d = get("trends.php")["data"]
    total = sql_one("SELECT COUNT(*) n FROM close_approaches")["n"]
    assert sum(day["approach_count"] for day in d["daily"]) == total
    assert len(d["velocity_vs_distance"]) == total
    with_size = sql_one("SELECT COUNT(DISTINCT a.neo_id) n FROM asteroids a JOIN close_approaches ca USING (neo_id) "
                        "WHERE a.est_diameter_max_m IS NOT NULL")["n"]
    assert sum(b["count"] for b in d["size_histogram"]) == with_size
    assert sum(h["approach_count"] for h in d["hazardous_split"]) == total


def test_runs_with_quality_results():
    runs = get("runs.php", limit=3)["data"]["runs"]
    assert [r["run_id"] for r in runs] == sorted((r["run_id"] for r in runs), reverse=True)
    for r in runs:
        n = sql_one("SELECT COUNT(*) n FROM quality_results WHERE run_id = %s", (r["run_id"],))["n"]
        assert len(r["quality"]) == n
        assert r["quality_failures"] == sum(not q["passed"] for q in r["quality"])


def test_includes_are_not_served():
    assert requests.get("http://localhost/asteroid-watch/includes/db.php", timeout=10).status_code == 403
