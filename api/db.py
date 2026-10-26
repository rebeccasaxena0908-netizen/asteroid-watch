"""Database access for the API: the read-only MySQL user, and PHP-compatible values.

Queries are the same SQL as the PHP API, run with SQLAlchemy text() and bound parameters
(:name placeholders, like PDO). User input never becomes SQL text.

Values are converted to exactly what PHP's PDO returned, so the JSON is identical:
DECIMAL -> "21.650" (string), DATE -> "2026-10-12", DATETIME -> "2026-10-12 06:30:00".
"""

from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
from functools import cache
from typing import Any

from sqlalchemy import Engine, TextClause, text
from sqlalchemy.exc import OperationalError

from pipeline.config import load_settings
from pipeline.db import engine as make_engine

BOOL_COLUMNS = ("is_potentially_hazardous", "is_sentry_object", "passed")


class DatabaseUnavailable(Exception):
    """MySQL is off or the read-only user isn't configured: HTTP 503."""


@cache
def reader_engine() -> Engine:
    """One connection pool per process, logged in as the read-only user (SELECT, SHOW VIEW only)."""
    settings = load_settings()
    if not settings.dashboard_db_password:
        raise DatabaseUnavailable("Read-only database user not configured: set DASHBOARD_DB_PASSWORD in .env.")
    reader = replace(settings, db_user=settings.dashboard_db_user, db_password=settings.dashboard_db_password)
    return make_engine(reader, connect_timeout=3)


def php_value(value: Any) -> Any:
    """A database value as PHP's PDO (native prepared statements) returned it."""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def with_bools(row: dict, columns: tuple[str, ...] = BOOL_COLUMNS) -> dict:
    """MySQL BOOLEAN comes back as 0/1; send real true/false (as the PHP API did)."""
    return {k: bool(v) if k in columns and v is not None else v for k, v in row.items()}


def query_all(sql: str | TextClause, params: dict | None = None) -> list[dict]:
    """Run a parameterised query and return all rows as dicts of PHP-compatible values."""
    try:
        conn = reader_engine().connect()
    except OperationalError:
        raise DatabaseUnavailable("Cannot connect to MySQL. Is XAMPP MySQL running?") from None
    with conn:
        result = conn.execute(text(sql) if isinstance(sql, str) else sql, params or {})
        return [{k: php_value(v) for k, v in row.items()} for row in result.mappings()]


def query_one(sql: str, params: dict | None = None) -> dict | None:
    rows = query_all(sql, params)
    return rows[0] if rows else None
