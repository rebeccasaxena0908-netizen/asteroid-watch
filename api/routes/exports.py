"""CSV and Excel downloads: the approaches table (with the dashboard's current filters) and the run history.

    GET /api/approaches.csv   /api/approaches.xlsx   same filters as /api/approaches, all pages
    GET /api/runs.csv         /api/runs.xlsx         every pipeline run

Spreadsheet safety: a text cell starting with = + - @ (or a tab / carriage return) would
be run as a formula by Excel ("CSV injection"), so such cells get a leading apostrophe.
"""

import csv
import io
from datetime import date

from fastapi import APIRouter
from fastapi.responses import Response
from openpyxl import Workbook
from openpyxl.styles import Font

from api.db import query_all, with_bools
from api.routes.approaches import COLUMNS, END, FROM, HAZARDOUS, ORDER, SORT, START, Q, approach_query
from api.routes.runs import RUN_COLUMNS

router = APIRouter()

MAX_EXPORT_ROWS = 100_000  # keeps memory bounded once the table holds JPL's century of data
FORMULA_START = ("=", "+", "-", "@", "\t", "\r")
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def safe_cell(value):
    """Booleans as yes/no; text that a spreadsheet would treat as a formula gets a leading '."""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, str) and value.startswith(FORMULA_START):
        return "'" + value
    return value


def to_csv(rows: list[dict], columns: list[str]) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([safe_cell(row[c]) for c in columns])
    return out.getvalue().encode("utf-8-sig")  # the BOM makes Excel read the file as UTF-8


def to_xlsx(rows: list[dict], columns: list[str], title: str) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = title
    ws.append(columns)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in rows:
        ws.append([safe_cell(row[c]) for c in columns])
    ws.freeze_panes = "A2"
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def download(rows: list[dict], name: str, kind: str) -> Response:
    columns = list(rows[0]) if rows else []
    filename = f"asteroid-watch-{name}-{date.today().isoformat()}.{kind}"
    if kind == "csv":
        body, media = to_csv(rows, columns), "text/csv; charset=utf-8"
    else:
        body, media = to_xlsx(rows, columns, name), XLSX_TYPE
    return Response(body, media_type=media, headers={
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


def approach_rows(start, end, hazardous, q, sort, order) -> list[dict]:
    aq = approach_query(start, end, hazardous, q, sort, order)
    rows = query_all(f"SELECT {COLUMNS} {FROM} {aq.where_sql} ORDER BY {aq.order_sql} LIMIT :limit",
                     aq.params | {"limit": MAX_EXPORT_ROWS})
    return [with_bools(r) for r in rows]


def run_rows() -> list[dict]:
    return query_all(f"SELECT {RUN_COLUMNS.replace('run_type,', 'run_type, source,')} "
                     "FROM pipeline_runs ORDER BY run_id DESC LIMIT :limit", {"limit": MAX_EXPORT_ROWS})


@router.get("/approaches.csv", summary="Download approaches as CSV (same filters as /api/approaches)")
def approaches_csv(start: str | None = START, end: str | None = END, hazardous: str | None = HAZARDOUS,
                   q: str | None = Q, sort: str | None = SORT, order: str | None = ORDER) -> Response:
    return download(approach_rows(start, end, hazardous, q, sort, order), "approaches", "csv")


@router.get("/approaches.xlsx", summary="Download approaches as Excel (same filters as /api/approaches)")
def approaches_xlsx(start: str | None = START, end: str | None = END, hazardous: str | None = HAZARDOUS,
                    q: str | None = Q, sort: str | None = SORT, order: str | None = ORDER) -> Response:
    return download(approach_rows(start, end, hazardous, q, sort, order), "approaches", "xlsx")


@router.get("/runs.csv", summary="Download the pipeline run history as CSV")
def runs_csv() -> Response:
    return download(run_rows(), "runs", "csv")


@router.get("/runs.xlsx", summary="Download the pipeline run history as Excel")
def runs_xlsx() -> Response:
    return download(run_rows(), "runs", "xlsx")
