"""MySQL connection helpers (PyMySQL).

Run `python -m pipeline.db` to check that the database is reachable.
"""
import re
from pathlib import Path

import pymysql
from pymysql.cursors import DictCursor

from pipeline.config import Settings, load_settings


def connection_args(settings: Settings, use_database: bool = True) -> dict:
    """Build PyMySQL connect() arguments. Prefers the Unix socket when it exists."""
    args = {
        "user": settings.db_user,
        "password": settings.db_password,
        "charset": "utf8mb4",
        "cursorclass": DictCursor,
        "autocommit": False,
    }
    if settings.db_socket and Path(settings.db_socket).exists():
        args["unix_socket"] = settings.db_socket
    else:
        args["host"] = settings.db_host
        args["port"] = settings.db_port
    if use_database:
        args["database"] = settings.db_name
    return args


def connect(settings: Settings | None = None, use_database: bool = True):
    return pymysql.connect(**connection_args(settings or load_settings(), use_database))


def split_sql(text: str) -> list[str]:
    """Split a .sql file into statements. Drops '--' comment lines.

    Our SQL files contain no stored procedures or semicolons inside strings,
    so splitting on ';' is enough.
    """
    lines = [line for line in text.splitlines() if not line.strip().startswith("--")]
    statements = "\n".join(lines).split(";")
    return [s.strip() for s in statements if s.strip()]


def run_sql_file(conn, path: Path) -> int:
    statements = split_sql(Path(path).read_text())
    with conn.cursor() as cur:
        for statement in statements:
            cur.execute(statement)
    conn.commit()
    return len(statements)


SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9_]+$")


def check_identifier(name: str) -> str:
    """Database and user names cannot be bound as query parameters, so validate them."""
    if not SAFE_IDENTIFIER.match(name):
        raise ValueError(f"Unsafe SQL identifier: {name!r}")
    return name


def main() -> None:
    settings = load_settings()
    args = connection_args(settings)
    via = f"socket {args['unix_socket']}" if "unix_socket" in args else f"TCP {args['host']}:{args['port']}"
    print(f"Connecting as {settings.db_user} via {via} ...")
    with connect(settings) as conn, conn.cursor() as cur:
        cur.execute("SELECT VERSION() AS version")
        print(f"OK: server {cur.fetchone()['version']}, database {settings.db_name}")
        cur.execute("SHOW FULL TABLES")
        for row in cur.fetchall():
            name, kind = list(row.values())
            if kind == "VIEW":
                print(f"  view   {name}")
            else:
                cur.execute(f"SELECT COUNT(*) AS n FROM `{check_identifier(name)}`")
                print(f"  table  {name:<20} {cur.fetchone()['n']} rows")


if __name__ == "__main__":
    main()
