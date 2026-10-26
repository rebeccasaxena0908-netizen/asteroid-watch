"""GET /api/approaches: close approaches with filters, sorting and pagination (was approaches.php).

The filter and sort rules are shared with the CSV/Excel export (routes/exports.py).
"""

import math
from dataclasses import dataclass

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response

from api.db import query_all, query_one, with_bools
from api.params import check_range, like_pattern, param_date, param_enum, param_int, param_text
from api.responses import data_response
from api.schemas import ApproachesResponse

router = APIRouter()

# Sort keys map to fixed SQL. User input never becomes SQL text.
SORT_COLUMNS = {
    "date": "ca.epoch_ms",
    "distance": "ca.miss_distance_km",
    "velocity": "ca.relative_velocity_kps",
    "size": "a.est_diameter_max_m",
    "name": "a.name",
}
FROM = "FROM close_approaches ca JOIN asteroids a ON a.neo_id = ca.neo_id"
COLUMNS = """ca.id AS approach_id, ca.neo_id, a.name, a.is_potentially_hazardous,
                a.est_diameter_min_m, a.est_diameter_max_m, ca.approach_date, ca.approach_datetime,
                ca.relative_velocity_kps, ca.relative_velocity_kph,
                ca.miss_distance_km, ca.miss_distance_lunar, ca.miss_distance_au, ca.orbiting_body"""

# Query parameters, documented once and shared with the export endpoints.
START = Query(None, description="First approach date, YYYY-MM-DD (inclusive)")
END = Query(None, description="Last approach date, YYYY-MM-DD (inclusive)")
HAZARDOUS = Query(None, description="all | true | false (default all)")
Q = Query(None, description="Name search, at most 50 characters; % and _ match literally")
SORT = Query(None, description="date | distance | velocity | size | name (default date)")
ORDER = Query(None, description="asc | desc (default asc)")


@dataclass
class ApproachQuery:
    """Validated filters as SQL: a WHERE clause with :placeholders, its values, and the ORDER BY."""

    filters: dict
    where_sql: str
    params: dict
    order_sql: str


def approach_query(start, end, hazardous, q, sort, order) -> ApproachQuery:
    """Validate the filters (in the PHP API's order) and turn them into SQL with bound values."""
    start = param_date("start", start)
    end = param_date("end", end)
    check_range(start, end)
    hazardous = param_enum("hazardous", hazardous, "all", ["all", "true", "false"])
    q = param_text("q", q, 50)
    sort = param_enum("sort", sort, "date", list(SORT_COLUMNS))
    order = param_enum("order", order, "asc", ["asc", "desc"])

    where, params = [], {}
    if start:
        where.append("ca.approach_date >= :start")
        params["start"] = start
    if end:
        where.append("ca.approach_date <= :end")
        params["end"] = end
    if hazardous != "all":
        where.append("a.is_potentially_hazardous = :hazardous")
        params["hazardous"] = 1 if hazardous == "true" else 0
    if q:
        where.append("a.name LIKE :q ESCAPE '\\\\'")
        params["q"] = like_pattern(q)
    order_sql = SORT_COLUMNS[sort] + (" DESC" if order == "desc" else " ASC") + ", ca.id ASC"
    return ApproachQuery(
        filters={"start": start, "end": end, "hazardous": hazardous, "q": q, "sort": sort, "order": order},
        where_sql="WHERE " + " AND ".join(where) if where else "",
        params=params,
        order_sql=order_sql,
    )


@router.get("/approaches", response_model=ApproachesResponse, summary="Close approaches (filtered, paged)")
def approaches(
    request: Request,
    start: str | None = START, end: str | None = END, hazardous: str | None = HAZARDOUS,
    q: str | None = Q, sort: str | None = SORT, order: str | None = ORDER,
    page: str | None = Query(None, description="1..10000 (default 1)"),
    per_page: str | None = Query(None, description="1..100 (default 25)"),
) -> Response:
    aq = approach_query(start, end, hazardous, q, sort, order)
    page_n = param_int("page", page, 1, 1, 10000)
    per_page_n = param_int("per_page", per_page, 25, 1, 100)

    total = query_one(f"SELECT COUNT(*) AS n {FROM} {aq.where_sql}", aq.params)["n"]  # type: ignore[index]
    rows = query_all(
        f"SELECT {COLUMNS} {FROM} {aq.where_sql} ORDER BY {aq.order_sql} LIMIT :limit OFFSET :offset",
        aq.params | {"limit": per_page_n, "offset": (page_n - 1) * per_page_n})

    return data_response(request, ApproachesResponse, {
        "items": [with_bools(r) for r in rows],
        "page": page_n,
        "per_page": per_page_n,
        "total": total,
        "total_pages": math.ceil(total / per_page_n),
        "filters": aq.filters,
    })
