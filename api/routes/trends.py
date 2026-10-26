"""GET /api/trends: data for the charts (was trends.php).

Approaches per day, size histogram, velocity vs miss distance, hazardous vs not.
start/end (optional) filter by approach date.
"""

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response

from api.db import query_all, query_one, with_bools
from api.params import check_range, param_date
from api.responses import data_response
from api.schemas import TrendsResponse

router = APIRouter()

# Size bins by maximum estimated diameter, in metres: [min, max)
SIZE_BINS: list[tuple[int, int | None]] = [
    (0, 10), (10, 25), (25, 50), (50, 100), (100, 250), (250, 500), (500, 1000), (1000, None)]
FROM = "FROM close_approaches ca JOIN asteroids a ON a.neo_id = ca.neo_id"


def size_histogram(sizes: list[dict]) -> list[dict]:
    """Count asteroids per size bin (and how many of them are hazardous)."""
    counts = [0] * len(SIZE_BINS)
    hazardous = [0] * len(SIZE_BINS)
    for s in sizes:
        d = s["est_diameter_max_m"]
        if d is None:
            continue
        for i, (lo, hi) in enumerate(SIZE_BINS):
            if d >= lo and (hi is None or d < hi):
                counts[i] += 1
                hazardous[i] += int(s["is_potentially_hazardous"])
                break
    return [{"min_m": lo, "max_m": hi, "label": f"≥ {lo} m" if hi is None else f"{lo}–{hi} m",
             "count": counts[i], "hazardous": hazardous[i]} for i, (lo, hi) in enumerate(SIZE_BINS)]


@router.get("/trends", response_model=TrendsResponse, summary="Chart data")
def trends(
    request: Request,
    start: str | None = Query(None, description="First approach date, YYYY-MM-DD"),
    end: str | None = Query(None, description="Last approach date, YYYY-MM-DD"),
) -> Response:
    start = param_date("start", start)
    end = param_date("end", end)
    check_range(start, end)
    where, params = [], {}
    if start:
        where.append("ca.approach_date >= :start")
        params["start"] = start
    if end:
        where.append("ca.approach_date <= :end")
        params["end"] = end
    where_sql = "WHERE " + " AND ".join(where) if where else ""

    daily = query_all(
        f"""SELECT ca.approach_date, COUNT(*) AS approach_count,
                CAST(SUM(a.is_potentially_hazardous) AS UNSIGNED) AS hazardous_count
         {FROM} {where_sql} GROUP BY ca.approach_date ORDER BY ca.approach_date""", params)

    # Size histogram over the distinct asteroids that approach in the range.
    sizes = query_all(
        f"SELECT DISTINCT a.neo_id, a.est_diameter_max_m, a.is_potentially_hazardous {FROM} {where_sql}", params)

    # The size chart counts asteroids; the other charts count approaches. Report both so the UI
    # can explain any difference (an asteroid that passes twice, or one without a size estimate).
    counts = query_one(
        f"""SELECT COUNT(*) AS approaches, COUNT(DISTINCT ca.neo_id) AS asteroids,
                COUNT(DISTINCT CASE WHEN a.est_diameter_max_m IS NULL THEN ca.neo_id END) AS asteroids_without_size
         {FROM} {where_sql}""", params)

    scatter = query_all(
        f"""SELECT ca.neo_id, a.name, a.is_potentially_hazardous, ca.approach_date,
                ca.relative_velocity_kps, ca.miss_distance_lunar
         {FROM} {where_sql} ORDER BY ca.epoch_ms""", params)

    hazardous = query_all(
        f"""SELECT a.is_potentially_hazardous, COUNT(DISTINCT a.neo_id) AS asteroid_count, COUNT(*) AS approach_count
         {FROM} {where_sql} GROUP BY a.is_potentially_hazardous ORDER BY a.is_potentially_hazardous""", params)

    return data_response(request, TrendsResponse, {
        "range": {"start": start, "end": end},
        "daily": daily,
        "size_histogram": size_histogram(sizes),
        "counts": counts,
        "velocity_vs_distance": [with_bools(r) for r in scatter],
        "hazardous_split": [with_bools(r) for r in hazardous],
    })
