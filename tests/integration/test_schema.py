"""Integration tests: the real database matches the models and the latest migration.

Needs XAMPP MySQL. Run with `make api-test`. Skipped when MySQL isn't reachable.
"""

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from typer.testing import CliRunner

from pipeline import cli
from pipeline.db import engine
from pipeline.models import Base
from pipeline.setup_db import alembic_config


def mysql_reachable() -> bool:
    try:
        with engine().connect():
            return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not mysql_reachable(), reason="MySQL not reachable (XAMPP off)")


def test_database_is_at_the_latest_migration():
    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    with engine().connect() as conn:
        assert MigrationContext.configure(conn).get_current_revision() == head


def test_models_match_the_real_database_exactly():
    with engine().connect() as conn:
        context = MigrationContext.configure(conn, opts={"compare_type": True, "compare_server_default": True})
        assert compare_metadata(context, Base.metadata) == []


def test_status_lists_the_neows_source():
    result = CliRunner().invoke(cli.app, ["status"])
    assert result.exit_code == 0, result.output
    assert "neows" in result.output and "close_approaches" in result.output
