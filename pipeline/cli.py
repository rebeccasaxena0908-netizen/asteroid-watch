"""The `asteroid-watch` command: one entry point for everything (Typer).

    asteroid-watch run          yesterday .. +7 days, with orbit lookups
    asteroid-watch quick-run    the same without orbit lookups (a few seconds)
    asteroid-watch backfill     last 365 .. +30 days
    asteroid-watch crosscheck   compare a sample with NASA JPL CAD
    asteroid-watch status       last run per source, row counts, schema version
    asteroid-watch test         offline tests (--api: integration tests, --parity: PHP vs FastAPI)
    asteroid-watch migrate      apply database migrations (Alembic)
    asteroid-watch serve        the API and dashboard at http://localhost:8010

Each command calls the existing module (pipeline.run_pipeline, pipeline.jpl_crosscheck, ...),
so `python -m pipeline.run_pipeline` keeps working exactly as before.
`asteroid-watch <command> --help` lists every option.
"""

import subprocess
import sys
from datetime import datetime, timedelta

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import func, select

from pipeline import jpl_crosscheck, run_pipeline
from pipeline.models import Asteroid, CloseApproach, NeoIdAlias, OrbitalData, PipelineRun, QualityResult

# show_locals=False: Typer's error display would otherwise print local variables,
# which can include database passwords.
app = typer.Typer(help="Asteroid Watch: NASA near-Earth data pipeline.", no_args_is_help=True,
                  pretty_exceptions_show_locals=False, add_completion=False)
console = Console()

# 8010, not 8000: port 8000 is often taken by other local dev servers.
DEFAULT_PORT = 8010
STALE_AFTER = timedelta(hours=26)  # same threshold as the dashboard's warning
TABLES = [Asteroid, CloseApproach, OrbitalData, NeoIdAlias, PipelineRun, QualityResult]


def _pipeline(backfill_days: int, forward_days: int, orbital_limit: int, run_type: str, dry_run: bool) -> None:
    argv = ["--backfill-days", str(backfill_days), "--forward-days", str(forward_days),
            "--orbital-limit", str(orbital_limit), "--run-type", run_type]
    if dry_run:
        argv.append("--dry-run")
    raise typer.Exit(run_pipeline.main(argv))


@app.command()
def run(
    backfill_days: int = typer.Option(1, help="Days before today."),
    forward_days: int = typer.Option(7, help="Days after today."),
    orbital_limit: int = typer.Option(100, help="Max orbit lookups this run (0 = skip)."),
    run_type: str = typer.Option("manual", help="manual, daily or backfill."),
    dry_run: bool = typer.Option(False, help="Extract and transform only; no database writes."),
) -> None:
    """Run the pipeline: extract, transform, load, quality checks, orbit lookups."""
    _pipeline(backfill_days, forward_days, orbital_limit, run_type, dry_run)


@app.command("quick-run")
def quick_run(dry_run: bool = typer.Option(False, help="No database writes.")) -> None:
    """Yesterday .. +7 days without orbit lookups (a few seconds; good for a live demo)."""
    _pipeline(1, 7, 0, "manual", dry_run)


@app.command()
def backfill(
    backfill_days: int = typer.Option(365, help="Days before today."),
    forward_days: int = typer.Option(30, help="Days after today."),
    orbital_limit: int = typer.Option(500, help="Max orbit lookups."),
) -> None:
    """Load a long range (default: the last 365 days and the next 30)."""
    _pipeline(backfill_days, forward_days, orbital_limit, "backfill", False)


@app.command()
def crosscheck(
    sample: int = typer.Option(50, help="Approaches to compare."),
    days: int = typer.Option(10, help="Random days for the coverage check."),
) -> None:
    """Compare a sample of stored approaches with NASA JPL CAD; writes docs/jpl_crosscheck.md."""
    jpl_crosscheck.main(["--sample", str(sample), "--days", str(days)])


def age_text(when: datetime | None, now: datetime) -> str:
    """'3 h ago', '2 d ago'; '-' when there is no time."""
    if when is None:
        return "-"
    hours = (now - when).total_seconds() / 3600
    if hours < 1:
        return f"{max(0, round(hours * 60))} min ago"
    return f"{hours:.0f} h ago" if hours < 48 else f"{hours / 24:.0f} d ago"


def is_stale(last_success: datetime | None, now: datetime) -> bool:
    return last_success is None or now - last_success > STALE_AFTER


def source_status(session) -> list[dict]:
    """One dict per source: its latest run and its latest successful run."""
    rows = []
    for source in session.scalars(select(PipelineRun.source).distinct().order_by(PipelineRun.source)):
        runs = select(PipelineRun).where(PipelineRun.source == source).order_by(PipelineRun.run_id.desc())
        latest = session.scalars(runs.limit(1)).one()
        success = session.scalars(runs.where(PipelineRun.status == "success").limit(1)).first()
        rows.append({"source": source, "latest": latest, "success": success})
    return rows


@app.command()
def status() -> None:
    """Show the last run of every source, table row counts and the schema version."""
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory
    from sqlalchemy.orm import Session

    from pipeline.db import engine
    from pipeline.setup_db import alembic_config

    now = datetime.now()
    try:
        with engine().connect() as conn, Session(conn) as session:
            current = MigrationContext.configure(conn).get_current_revision()
            sources = source_status(session)
            counts = {model.__tablename__: session.scalar(select(func.count()).select_from(model)) for model in TABLES}
    except Exception as exc:  # most often: XAMPP MySQL isn't running
        console.print(f"[red]Cannot read the database ({type(exc).__name__}). Is XAMPP MySQL running?[/red]")
        raise typer.Exit(1) from None

    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    behind = f"[yellow]behind (head is {head}): run `asteroid-watch migrate`[/yellow]"
    note = "up to date" if current == head else behind
    console.print(f"Schema version: {current} ({note})")

    table = Table(title="Sources")
    for column in ["Source", "Latest run", "Status", "Last success", "Checks"]:
        table.add_column(column)
    for row in sources:
        latest, success = row["latest"], row["success"]
        done = success.finished_at if success else None
        stale = row["source"] == "neows" and is_stale(done, now)
        status_text = {"success": "[green]✓ success[/green]", "failed": "[red]✗ failed[/red]"}.get(
            latest.status, f"[yellow]… {latest.status}[/yellow]")
        checks = "-"
        if success:  # cross-check results are findings about NASA's data, not failures (as on the dashboard)
            word = "findings" if success.run_type == "crosscheck" else "failed"
            checks = f"{success.quality_failures} {word}"
        last_success = (f"#{success.run_id}, " if success else "") + age_text(done, now)
        table.add_row(
            row["source"],
            f"#{latest.run_id} {latest.run_type}, {latest.started_at:%d %b %H:%M}",
            status_text,
            last_success + (" [red](stale)[/red]" if stale else ""),
            checks,
        )
    console.print(table)

    counts_table = Table(title="Rows")
    counts_table.add_column("Table")
    counts_table.add_column("Rows", justify="right")
    for name, n in counts.items():
        counts_table.add_row(name, f"{n:,}")
    console.print(counts_table)


@app.command()
def test(
    api: bool = typer.Option(False, "--api", help="Integration tests: API and schema against MySQL."),
    parity: bool = typer.Option(False, "--parity", help="Parity tests: legacy PHP API vs FastAPI."),
) -> None:
    """Run the tests. Default: offline unit tests (no internet or database needed)."""
    if parity:
        target = ["tests/parity"]
    elif api:
        target = ["tests/integration"]
    else:
        target = ["--ignore=tests/integration", "--ignore=tests/parity"]
    raise typer.Exit(subprocess.run([sys.executable, "-m", "pytest", "-q", *target]).returncode)


@app.command()
def migrate() -> None:
    """Apply database migrations (Alembic) up to the latest version."""
    from pipeline.setup_db import migrate as upgrade

    upgrade()


@app.command("setup-db")
def setup_db() -> None:
    """Create the database and users (as XAMPP root), then apply migrations."""
    from pipeline import setup_db as setup

    setup.create_database_and_user()
    setup.migrate()


@app.command("check-db")
def check_db() -> None:
    """Test the MySQL connection and list tables with row counts."""
    from pipeline import db

    db.main()


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Address to listen on (127.0.0.1 = this Mac only)."),
    port: int = typer.Option(DEFAULT_PORT, help="Port."),
    reload: bool = typer.Option(False, help="Restart when code changes (development)."),
) -> None:
    """Start the API and dashboard (FastAPI + uvicorn, 1 worker): http://localhost:8010"""
    import uvicorn

    console.print(f"Dashboard: http://localhost:{port}/   API docs: http://localhost:{port}/docs")
    uvicorn.run("api.main:app", host=host, port=port, workers=1, reload=reload, log_level="info")


if __name__ == "__main__":
    app()
