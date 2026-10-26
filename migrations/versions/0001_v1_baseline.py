"""v1 baseline: the schema as it was at the end of v1.

Runs the v1 SQL files (tables, views, the records_after_dedupe column). They are all
safe to re-run, so this works on an empty database. The existing database was marked
as already being at this revision (`alembic stamp 0001_v1_baseline`) without running it.

Revision ID: 0001_v1_baseline
Revises:
Created: 2026-10-27
"""

from alembic import op

from pipeline.config import PROJECT_ROOT
from pipeline.db import split_sql

revision = "0001_v1_baseline"
down_revision = None
branch_labels = None
depends_on = None

V1_SQL_FILES = ["01_schema.sql", "02_views.sql", "03_migrations.sql"]


def upgrade() -> None:
    for name in V1_SQL_FILES:
        for statement in split_sql((PROJECT_ROOT / "sql" / name).read_text()):
            op.execute(statement)


def downgrade() -> None:
    raise NotImplementedError("Downgrading the baseline would delete every table and all data; restore a backup.")
