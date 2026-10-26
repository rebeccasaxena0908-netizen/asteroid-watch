"""The SQLAlchemy models match the v1 SQL files (offline). The live comparison with the
real database is in tests/integration/test_schema.py."""

import re

from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable

from pipeline.config import PROJECT_ROOT
from pipeline.models import Base

NOT_COLUMNS = {"PRIMARY", "UNIQUE", "INDEX", "CONSTRAINT", "REFERENCES", "KEY"}


def sql_file_columns() -> dict[str, list[str]]:
    """Column names per table, in order, from sql/01_schema.sql."""
    schema = (PROJECT_ROOT / "sql" / "01_schema.sql").read_text()
    tables = {}
    for name, body in re.findall(r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\) ENGINE", schema, re.S):
        words = [line.split()[0] for line in body.splitlines() if line.strip() and not line.strip().startswith("--")]
        tables[name] = [w for w in words if w not in NOT_COLUMNS]
    return tables


def test_models_have_the_same_tables_and_columns_as_the_sql_files():
    expected = sql_file_columns()
    expected["pipeline_runs"].insert(expected["pipeline_runs"].index("run_type") + 1, "source")  # migration 0002
    models = {name: [c.name for c in table.columns] for name, table in Base.metadata.tables.items()}
    assert models == expected


def test_models_compile_to_mysql_ddl_with_keys_defaults_and_options():
    tables = Base.metadata.tables.items()
    ddl = {name: str(CreateTable(table).compile(dialect=mysql.dialect())) for name, table in tables}
    unique = {i.name: [c.name for c in i.columns] for i in Base.metadata.tables["close_approaches"].indexes if i.unique}
    assert unique == {"uq_approach": ["neo_id", "epoch_ms"]}
    assert "ON DELETE CASCADE" in ddl["close_approaches"]
    assert "DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP" in ddl["asteroids"]
    assert "source VARCHAR(20) NOT NULL DEFAULT 'neows'" in ddl["pipeline_runs"]
    assert all("ENGINE=InnoDB" in d and "CHARSET=utf8mb4" in d for d in ddl.values())


def test_nullability_follows_the_sql_file():
    schema = (PROJECT_ROOT / "sql" / "01_schema.sql").read_text()
    for name, table in Base.metadata.tables.items():
        for column in table.columns:
            if column.name == "source":
                continue
            line = re.search(rf"^\s+{column.name}\s+.*$", schema.split(f"EXISTS {name} (")[1], re.M)
            assert line, (name, column.name)
            sql_not_null = "NOT NULL" in line.group(0) or column.primary_key
            assert (not column.nullable) == sql_not_null, (name, column.name)
