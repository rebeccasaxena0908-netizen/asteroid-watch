"""Alembic migrations, checked offline: history and the SQL they would run (--sql mode)."""

import io

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from pipeline.setup_db import alembic_config


def offline_sql(revision_range: str) -> str:
    out = io.StringIO()
    config = Config(alembic_config().config_file_name, output_buffer=out)
    config.attributes["configure_logging"] = False  # keep pytest's logging setup
    command.upgrade(config, revision_range, sql=True)
    return out.getvalue()


def test_history_is_one_straight_line_from_the_v1_baseline():
    script = ScriptDirectory.from_config(alembic_config())
    revisions = list(script.walk_revisions())
    assert script.get_heads() == ["0002_pipeline_runs_source"]
    assert [r.revision for r in reversed(revisions)] == ["0001_v1_baseline", "0002_pipeline_runs_source"]
    assert revisions[-1].down_revision is None


def test_baseline_creates_every_v1_table_and_view():
    sql = offline_sql("0001_v1_baseline")
    for table in ["asteroids", "close_approaches", "orbital_data", "pipeline_runs", "quality_results",
                  "neo_id_aliases"]:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql
    for view in ["v_upcoming_approaches", "v_daily_counts", "v_hazardous_summary", "v_top_closest", "v_top_largest"]:
        assert f"CREATE OR REPLACE VIEW {view}" in sql


def test_source_migration_adds_column_and_labels_crosscheck_runs():
    sql = offline_sql("0001_v1_baseline:0002_pipeline_runs_source")
    assert "ADD COLUMN IF NOT EXISTS source VARCHAR(20) NOT NULL DEFAULT 'neows' AFTER run_type" in sql
    assert "UPDATE pipeline_runs SET source = 'jpl_cad' WHERE run_type = 'crosscheck'" in sql
