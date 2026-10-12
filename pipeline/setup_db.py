"""One-time database setup: creates the database and the app user, then runs the SQL files.

Connects as the MySQL admin user (XAMPP default: root with no password).
Override with DB_ROOT_USER / DB_ROOT_PASSWORD environment variables if yours differs.
Safe to re-run.

Usage: python -m pipeline.setup_db
"""
import os
from dataclasses import replace

from pipeline.config import PROJECT_ROOT, load_settings
from pipeline.db import check_identifier, connect, run_sql_file

SQL_FILES = [PROJECT_ROOT / "sql" / "01_schema.sql", PROJECT_ROOT / "sql" / "02_views.sql"]

# The app user gets only what the pipeline and dashboard need, and only on this database.
# DROP is required by MariaDB for CREATE OR REPLACE VIEW.
APP_PRIVILEGES = ("SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES, DROP, "
                  "CREATE VIEW, SHOW VIEW")

# 'localhost' covers socket connections; '127.0.0.1' covers TCP connections.
APP_HOSTS = ["localhost", "127.0.0.1"]


def create_database_and_user() -> None:
    settings = load_settings()
    if not settings.db_password:
        raise SystemExit("DB_PASSWORD is empty in .env. Set it before running setup.")
    db_name = check_identifier(settings.db_name)
    check_identifier(settings.db_user)

    admin = replace(
        settings,
        db_user=os.environ.get("DB_ROOT_USER", "root"),
        db_password=os.environ.get("DB_ROOT_PASSWORD", ""),
    )
    with connect(admin, use_database=False) as conn, conn.cursor() as cur:
        cur.execute(
            f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
        for host in APP_HOSTS:
            # Values (not identifiers) are passed as parameters, so the password is escaped safely.
            cur.execute("CREATE USER IF NOT EXISTS %s@%s IDENTIFIED BY %s",
                        (settings.db_user, host, settings.db_password))
            cur.execute("ALTER USER %s@%s IDENTIFIED BY %s",
                        (settings.db_user, host, settings.db_password))
            cur.execute(f"GRANT {APP_PRIVILEGES} ON `{db_name}`.* TO %s@%s",
                        (settings.db_user, host))
        cur.execute("FLUSH PRIVILEGES")
        conn.commit()
    print(f"Database `{db_name}` and user `{settings.db_user}` are ready.")


def create_tables_and_views() -> None:
    with connect() as conn:
        for path in SQL_FILES:
            count = run_sql_file(conn, path)
            print(f"Ran {path.name}: {count} statements")


if __name__ == "__main__":
    create_database_and_user()
    create_tables_and_views()
