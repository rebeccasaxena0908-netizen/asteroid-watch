"""Input validation: the PHP API's helpers (dashboard/includes/api.php), ported one-for-one.

Every check runs before any database access, and a failure is an HTTP 400 with the same
message as the PHP API. Parameters arrive as raw strings (or None) from the query string.
"""

import re
from datetime import datetime

INT_PATTERN = re.compile(r"^-?\d+$")


class BadRequest(Exception):
    """Invalid input: HTTP 400."""


class NotFound(Exception):
    """No such record: HTTP 404."""


def param_date(name: str, value: str | None, default: str | None = None) -> str | None:
    """A real calendar date written exactly as YYYY-MM-DD (2026-02-30 and 2026-1-5 are rejected)."""
    if value is None or value == "":
        return default
    try:
        valid = datetime.strptime(value, "%Y-%m-%d").strftime("%Y-%m-%d") == value
    except ValueError:
        valid = False
    if not valid:
        raise BadRequest(f"'{name}' must be a date like 2026-10-12.")
    return value


def param_int(name: str, value: str | None, default: int, minimum: int, maximum: int) -> int:
    if value is None or value == "":
        return default
    if not INT_PATTERN.match(value) or not minimum <= int(value) <= maximum:
        raise BadRequest(f"'{name}' must be a whole number from {minimum} to {maximum}.")
    return int(value)


def param_enum(name: str, value: str | None, default: str, allowed: list[str]) -> str:
    if value is None or value == "":
        return default
    if value not in allowed:
        raise BadRequest(f"'{name}' must be one of: {', '.join(allowed)}.")
    return value


PHP_TRIM = " \t\n\r\0\x0b"  # the characters PHP's trim() removes


def param_text(name: str, value: str | None, max_length: int) -> str:
    value = (value or "").strip(PHP_TRIM)
    if len(value) > max_length:
        raise BadRequest(f"'{name}' must be at most {max_length} characters.")
    return value


def check_range(start: str | None, end: str | None) -> None:
    if start and end and start > end:
        raise BadRequest("'start' must be on or before 'end'.")


def like_pattern(text: str) -> str:
    """'%' + text + '%' for SQL LIKE, with %, _ and \\ escaped so they match literally."""
    return "%" + re.sub(r"([%_\\])", r"\\\1", text) + "%"
