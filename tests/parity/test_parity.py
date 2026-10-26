"""Parity: the FastAPI API returns exactly what the PHP API returns, for the same request.

Needs XAMPP (Apache + MySQL) with the PHP API deployed (`make legacy-deploy`). Run with
`make parity-test`. Skipped when the PHP API isn't reachable.

"Exactly" means: the same HTTP status, the same content type and cache headers, and the
same response body byte for byte. If the bytes ever differ, the test reports where, with a
type-aware comparison of the parsed JSON (1 and 1.0 differ, "21.650" and 21.65 differ).
"""

import pytest
import requests
from fastapi.testclient import TestClient

from api.main import app
from pipeline.db import connect

PHP = "http://localhost/asteroid-watch/api"
fastapi = TestClient(app, raise_server_exceptions=False)


def php_reachable() -> bool:
    try:
        return requests.get(f"{PHP}/runs.php", params={"limit": 1}, timeout=3).status_code == 200
    except requests.RequestException:
        return False


pytestmark = pytest.mark.skipif(not php_reachable(), reason="PHP API not reachable (XAMPP off or not deployed)")


def differences(php, ours, path="$") -> list[str]:
    """Every difference in type, value or key order between two parsed JSON values."""
    if type(php) is not type(ours):
        return [f"{path}: {type(php).__name__} {php!r} vs {type(ours).__name__} {ours!r}"]
    if isinstance(php, dict):
        if list(php) != list(ours):
            return [f"{path}: keys {list(php)} vs {list(ours)}"]
        return [d for k in php for d in differences(php[k], ours[k], f"{path}.{k}")]
    if isinstance(php, list):
        if len(php) != len(ours):
            return [f"{path}: {len(php)} items vs {len(ours)}"]
        return [d for i, (a, b) in enumerate(zip(php, ours, strict=True)) for d in differences(a, b, f"{path}[{i}]")]
    return [] if php == ours else [f"{path}: {php!r} vs {ours!r}"]


def compare(endpoint: str, params: dict | None = None, method: str = "GET") -> None:
    php = requests.request(method, f"{PHP}/{endpoint}.php", params=params, timeout=30)
    ours = fastapi.request(method, f"/api/{endpoint}", params=params)
    assert ours.status_code == php.status_code, (php.text, ours.text)
    for header in ["Content-Type", "Cache-Control", "X-Content-Type-Options"]:
        assert ours.headers[header] == php.headers[header], header
    assert differences(php.json(), ours.json()) == []
    assert ours.content == php.content


@pytest.mark.parametrize("params", [
    {}, {"pretty": "1"},
])
def test_summary(params):
    compare("summary", params)


SEARCHES = ["2008 TC4", "eros", "%", "_", "\\", "(", "–", "' OR 1=1 --", "x" * 50, " 2008 TC4\t", "zzzz-none"]
BAD_APPROACHES = [
    {"page": "0"}, {"page": "10001"}, {"page": "abc"}, {"page": "5.0"}, {"page": "1e2"}, {"page": " 5"},
    {"per_page": "0"}, {"per_page": "101"}, {"sort": "miss_distance_km;DROP"}, {"sort": "DATE"},
    {"order": "up"}, {"hazardous": "yes"}, {"hazardous": "TRUE"}, {"start": "2026-13-01"},
    {"start": "2026-02-30"}, {"start": "2026-1-5"}, {"start": "20261012"}, {"end": "yesterday"},
    {"start": "2026-10-12", "end": "2026-10-01"}, {"q": "x" * 51},
    {"start": "2026-10-12", "end": "2026-10-01", "hazardous": "yes"},   # first error wins, as in PHP
]


@pytest.mark.parametrize("params", [
    {}, {"pretty": "1"}, {"per_page": "1"}, {"per_page": "100"}, {"page": "2"}, {"page": "9999"},
    {"page": "007"}, {"page": "+5"}, {"page": ""},
    *[{"sort": s, "order": o} for s in ["date", "distance", "velocity", "size", "name"] for o in ["asc", "desc"]],
    {"hazardous": "true"}, {"hazardous": "false"}, {"hazardous": "all"},
    {"start": "2026-10-01", "end": "2026-10-31"}, {"start": "2026-10-20"}, {"end": "2025-11-01"},
    {"start": "2030-01-01"}, {"start": "2026-10-12", "end": "2026-10-12"},
    *[{"q": q} for q in SEARCHES],
    {"q": "2008", "hazardous": "true", "sort": "distance", "order": "desc", "per_page": "5", "page": "2"},
    *BAD_APPROACHES,
], ids=str)
def test_approaches(params):
    compare("approaches", params)


def test_approaches_every_page_of_the_whole_table():
    total = requests.get(f"{PHP}/approaches.php", params={"per_page": 1}, timeout=10).json()["data"]["total"]
    for page in range(1, total // 100 + 2):
        compare("approaches", {"per_page": "100", "page": str(page)})


@pytest.mark.parametrize("params", [
    {"id": "2614134"}, {"id": "3430309"}, {"id": "2000433"}, {"id": "1"}, {"id": "abc"}, {"id": "1 OR 1=1"},
    {"id": ""}, {}, {"id": "1" * 21}, {"id": "-5"}, {"id": "2614134", "pretty": "1"},
], ids=str)
def test_asteroid(params):
    compare("asteroid", params)


def test_asteroid_every_stored_id_and_alias():
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT neo_id FROM asteroids UNION ALL SELECT old_neo_id FROM neo_id_aliases")
        ids = [r["neo_id"] for r in cur.fetchall()]
    assert len(ids) > 1000
    for neo_id in ids:
        compare("asteroid", {"id": neo_id})


@pytest.mark.parametrize("params", [
    {}, {"pretty": "1"}, {"start": "2025-10-12", "end": "2026-11-11"}, {"start": "2026-10-01", "end": "2026-10-31"},
    {"start": "2030-01-01"}, {"end": "yesterday"}, {"start": "2026-10-12", "end": "2026-10-01"},
], ids=str)
def test_trends(params):
    compare("trends", params)


@pytest.mark.parametrize("params", [
    {}, {"limit": "1"}, {"limit": "50"}, {"limit": "0"}, {"limit": "51"}, {"limit": "abc"}, {"pretty": "1"},
], ids=str)
def test_runs(params):
    compare("runs", params)


@pytest.mark.parametrize("endpoint", ["summary", "approaches", "asteroid", "trends", "runs"])
@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
def test_other_methods_are_rejected(endpoint, method):
    compare(endpoint, method=method)
