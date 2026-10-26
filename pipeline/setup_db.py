"""One-time database setup: creates the database and users, then applies the migrations.

Connects as the MySQL admin user (XAMPP default: root with no password).
Override with DB_ROOT_USER / DB_ROOT_PASSWORD environment variables if yours differs.
Safe to re-run.

Usage: python -m pipeline.setup_db
"""
import os
from dataclasses import replace

from alembic import command
from alembic.config import Config

from pipeline.config import PROJECT_ROOT, load_settings
from pipeline.db import check_identifier, connect

# The app user gets only what the pipeline and dashboard need, and only on this database.
# DROP is required by MariaDB for CREATE OR REPLACE VIEW.
APP_PRIVILEGES = ("SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES, DROP, "
                  "CREATE VIEW, SHOW VIEW")

# The dashboard (PHP) user can only read.
READER_PRIVILEGES = "SELECT, SHOW VIEW"

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
        users = [(settings.db_user, settings.db_password, APP_PRIVILEGES)]
        if settings.dashboard_db_password:
            check_identifier(settings.dashboard_db_user)
            users.append((settings.dashboard_db_user, settings.dashboard_db_password, READER_PRIVILEGES))
        for user, password, privileges in users:
            for host in APP_HOSTS:
                # Values (not identifiers) are passed as parameters, so the password is escaped safely.
                cur.execute("CREATE USER IF NOT EXISTS %s@%s IDENTIFIED BY %s", (user, host, password))
                cur.execute("ALTER USER %s@%s IDENTIFIED BY %s", (user, host, password))
                cur.execute(f"GRANT {privileges} ON `{db_name}`.* TO %s@%s", (user, host))
            print(f"User `{user}` ready ({privileges} on `{db_name}`)")
        cur.execute("FLUSH PRIVILEGES")
        conn.commit()
    print(f"Database `{db_name}` is ready.")


def alembic_config() -> Config:
    return Config(str(PROJECT_ROOT / "alembic.ini"))


def migrate(revision: str = "head") -> None:
    """Create or update tables and views with Alembic (migrations/versions/).

    On an empty database the first migration runs the v1 SQL files; later ones apply
    each schema change in order. Already-applied migrations are skipped.
    """
    command.upgrade(alembic_config(), revision)


if __name__ == "__main__":
    create_database_and_user()
    migrate()
