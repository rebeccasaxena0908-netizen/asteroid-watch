"""Add pipeline_runs.source: which data source a run fetched from (neows, jpl_cad, sentry, ...).

Existing runs: ETL runs fetched from NeoWs (the default). Cross-check runs called the
JPL Close-Approach Data API, so they become 'jpl_cad'.

Revision ID: 0002_pipeline_runs_source
Revises: 0001_v1_baseline
Created: 2026-10-27
"""

from alembic import op

revision = "0002_pipeline_runs_source"
down_revision = "0001_v1_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS source VARCHAR(20) NOT NULL DEFAULT 'neows' AFTER run_type"
    )
    op.execute("UPDATE pipeline_runs SET source = 'jpl_cad' WHERE run_type = 'crosscheck'")


def downgrade() -> None:
    op.execute("ALTER TABLE pipeline_runs DROP COLUMN source")
