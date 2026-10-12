import pytest

from pipeline.config import PROJECT_ROOT
from pipeline.db import check_identifier, split_sql


def test_split_sql_drops_comments_and_blank_statements():
    text = "-- comment\nCREATE TABLE a (x INT);\n\n-- another\nCREATE VIEW v AS SELECT 1;\n"
    assert split_sql(text) == ["CREATE TABLE a (x INT)", "CREATE VIEW v AS SELECT 1"]


def test_schema_defines_all_tables():
    statements = split_sql((PROJECT_ROOT / "sql" / "01_schema.sql").read_text())
    tables = {s.split()[5] for s in statements if s.startswith("CREATE TABLE IF NOT EXISTS")}
    assert tables == {"asteroids", "close_approaches", "orbital_data", "pipeline_runs", "quality_results"}


def test_close_approaches_has_dedupe_key():
    schema = (PROJECT_ROOT / "sql" / "01_schema.sql").read_text()
    assert "UNIQUE KEY uq_approach (neo_id, epoch_ms)" in schema


def test_views_file_defines_all_views():
    statements = split_sql((PROJECT_ROOT / "sql" / "02_views.sql").read_text())
    views = {s.split()[4] for s in statements}
    assert views == {"v_upcoming_approaches", "v_daily_counts", "v_hazardous_summary",
                     "v_top_closest", "v_top_largest"}


@pytest.mark.parametrize("bad", ["asteroid-watch", "x; DROP TABLE y", "a`b", ""])
def test_check_identifier_rejects_unsafe_names(bad):
    with pytest.raises(ValueError):
        check_identifier(bad)
