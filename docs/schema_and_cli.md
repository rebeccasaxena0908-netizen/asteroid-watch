# Models, migrations and the CLI: how it works

Added in v2 Phase 1. Three pieces: **SQLAlchemy models** describe the tables in Python, **Alembic migrations** record every change to them, and the **Typer CLI** (`asteroid-watch`) is one command for everything.

## 1. SQLAlchemy models (`pipeline/models.py`)

Each table is a Python class, and each column is an attribute with its type:

```python
class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    run_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(20), server_default=text("'neows'"))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)   # "| None" = NULL allowed
```

- **They mirror the v1 schema exactly:** column types (`DOUBLE`, `DECIMAL(6,3)`, `VARCHAR(20)`), `NULL`/`NOT NULL`, defaults (including `ON UPDATE CURRENT_TIMESTAMP`), primary keys, the `uq_approach (neo_id, epoch_ms)` unique key, index and foreign-key names, `ON DELETE CASCADE`, and InnoDB/utf8mb4.
- **This is proven, not assumed.** `alembic check` compares the models with the live database, types and defaults included, and reports "No new upgrade operations detected". A test (`tests/integration/test_schema.py`) runs the same comparison. Offline tests compare the models with `sql/01_schema.sql`.
- **What uses them:** Alembic, the `status` command, and (from Phase 2) the FastAPI API.
- **What doesn't (yet):** the v1 loader (`load.py`) still writes with PyMySQL. Its insert/update counting relies on MySQL's affected-rows numbers for `INSERT … ON DUPLICATE KEY UPDATE` (see `architecture.md` §4), and it works, so it wasn't rewritten.
- **Views** (`v_top_closest`, …) are plain SQL and aren't modelled.

## 2. Alembic migrations (`migrations/`)

A **migration** is a small Python file that changes the schema one step (`upgrade`) and can undo it (`downgrade`). Alembic records the applied version in a one-row table, `alembic_version`. Before v2, schema changes were SQL files run by hand. Now every change is a numbered migration, so any database can be brought to the same state with one command.

| Revision | What it does |
|---|---|
| `0001_v1_baseline` | The v1 schema: runs `sql/01_schema.sql`, `02_views.sql` and `03_migrations.sql` (all safe to re-run) |
| `0002_pipeline_runs_source` | Adds `pipeline_runs.source` (`neows`, `jpl_cad`, …) after `run_type`; existing cross-check runs become `jpl_cad` |

**How the existing database was moved to Alembic (2026-10-27):**

1. Backup: `backups/asteroid_watch_2026-10-27_before_alembic.sql`. It was checked by restoring it into a temporary database, where all 6 table counts and all 5 views matched.
2. `alembic stamp 0001_v1_baseline`: this tells Alembic "this database is already at the v1 baseline" without running anything.
3. `alembic upgrade head`: this ran only migration 0002.
4. `alembic check`: no differences. The row counts were unchanged (1,627 / 1,876 / 1,078 / 57 / 21 / 121).

A **new, empty database** goes through both migrations (`make setup-db`). This was tested: Alembic built a throwaway database from nothing, `alembic check` found no difference, and the database was dropped.

**Commands:** `asteroid-watch migrate` (or `make migrate`) upgrades to the latest version. `.venv/bin/alembic upgrade head --sql` prints the SQL without running it. `.venv/bin/alembic history` lists the migrations.

**Connection:** `migrations/env.py` connects through `pipeline.db.engine()`, which uses the same `.env` settings and socket-or-TCP rule as the pipeline. `alembic.ini` contains no URL and no password.

**Adding a schema change later:** change the model, write a migration in `migrations/versions/`, run `asteroid-watch migrate`, and confirm that `alembic check` is clean.

## 3. The CLI (`pipeline/cli.py`)

`asteroid-watch` is installed as a command by `pip install -e .` (the `[project.scripts]` entry in `pyproject.toml`). Typer turns each Python function into a sub-command and its parameters into `--options`, with `--help` generated from the docstrings.

| Command | Does |
|---|---|
| `run` | Yesterday to +7 days, with up to 100 orbit lookups (options: `--backfill-days`, `--forward-days`, `--orbital-limit`, `--run-type`, `--dry-run`) |
| `quick-run` | The same without orbit lookups |
| `backfill` | 365 days back to 30 ahead, 500 orbit lookups |
| `crosscheck` | JPL comparison (`--sample`, `--days`) |
| `status` | Schema version; the latest and the last successful run of each source; "stale" when NeoWs hasn't succeeded for 26 hours; row counts |
| `test` | Offline tests; `--api` runs the integration tests |
| `migrate`, `setup-db`, `check-db` | Database setup and checks |
| `serve` | The FastAPI server (Phase 2) |

- **The CLI is a thin layer.** Each command calls the existing module (`run_pipeline.main`, `jpl_crosscheck.main`, …) with the same options the v1 `make` targets used. So `python -m pipeline.run_pipeline` and the daily launchd job work exactly as before. The `make` targets now call the CLI, and tests check that each command passes the same options as v1.
- **Security:** Typer's error display normally prints the local variables of the failing function, which could include a database password. It's turned off (`pretty_exceptions_show_locals=False`), and a test checks that it stays off.
