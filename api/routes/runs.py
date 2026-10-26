"""GET /api/runs: latest pipeline runs, each with its quality check results (was runs.php)."""

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response
from sqlalchemy import bindparam, text

from api.db import query_all, with_bools
from api.params import param_int
from api.responses import data_response
from api.schemas import RunsResponse

router = APIRouter()

RUN_COLUMNS = """run_id, run_type, status, started_at, finished_at,
                TIMESTAMPDIFF(SECOND, started_at, finished_at) AS duration_seconds,
                date_range_start, date_range_end, api_calls, records_extracted, records_after_dedupe,
                rows_inserted, rows_updated, quality_failures, error_message"""


def quality_by_run(run_ids: list[int]) -> dict[int, list[dict]]:
    """One query for the checks of all these runs; the ids are bound (an expanding IN list)."""
    sql = text("SELECT run_id, check_name, passed, details FROM quality_results "
               "WHERE run_id IN :ids ORDER BY run_id, id").bindparams(bindparam("ids", expanding=True))
    by_run: dict[int, list[dict]] = {}
    for c in query_all(sql, {"ids": run_ids}):
        by_run.setdefault(c["run_id"], []).append(
            with_bools({"check_name": c["check_name"], "passed": c["passed"], "details": c["details"]}))
    return by_run


@router.get("/runs", response_model=RunsResponse, summary="Pipeline runs with quality checks")
def runs(request: Request, limit: str | None = Query(None, description="1..50 (default 10)")) -> Response:
    n = param_int("limit", limit, 10, 1, 50)
    rows = query_all(f"SELECT {RUN_COLUMNS} FROM pipeline_runs ORDER BY run_id DESC LIMIT :limit", {"limit": n})
    if rows:
        checks = quality_by_run([r["run_id"] for r in rows])
        rows = [r | {"quality": checks.get(r["run_id"], [])} for r in rows]
    return data_response(request, RunsResponse, {"runs": rows})
