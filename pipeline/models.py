"""SQLAlchemy 2.0 models: the database schema described in Python.

They mirror the tables in sql/01_schema.sql exactly (names, types, defaults, keys and
indexes), and a live test compares them with the real database. Alembic (migrations/)
uses them to check that every schema change is a migration.

The v1 loader still writes with PyMySQL (load.py): its upsert counting depends on
MySQL's affected-rows numbers. The models are used for the schema, the CLI and the API.

The views (sql/02_views.sql) aren't modelled here. They are plain SQL, created by the
baseline migration.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.mysql import DECIMAL, DOUBLE
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Every table: InnoDB (transactions + foreign keys), utf8mb4 (full Unicode).
TABLE_OPTIONS = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"}

NOW = text("CURRENT_TIMESTAMP")
NOW_ON_UPDATE = text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")


class Base(DeclarativeBase):
    pass


class Asteroid(Base):
    """One row per asteroid. neo_id is NASA's ID (the JPL SPK-ID)."""

    __tablename__ = "asteroids"
    __table_args__ = (Index("idx_asteroids_hazardous", "is_potentially_hazardous"), TABLE_OPTIONS)

    neo_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    nasa_jpl_url: Mapped[str | None] = mapped_column(String(255))
    absolute_magnitude_h: Mapped[Decimal | None] = mapped_column(DECIMAL(6, 3))
    est_diameter_min_m: Mapped[float | None] = mapped_column(DOUBLE)
    est_diameter_max_m: Mapped[float | None] = mapped_column(DOUBLE)
    is_potentially_hazardous: Mapped[bool] = mapped_column(Boolean, server_default=text("0"))
    is_sentry_object: Mapped[bool] = mapped_column(Boolean, server_default=text("0"))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, server_default=NOW)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=NOW_ON_UPDATE)


class CloseApproach(Base):
    """One pass of an asteroid near a body (Earth). UNIQUE(neo_id, epoch_ms) prevents duplicates."""

    __tablename__ = "close_approaches"
    __table_args__ = (
        Index("uq_approach", "neo_id", "epoch_ms", unique=True),
        Index("idx_approach_date", "approach_date"),
        Index("idx_miss_distance", "miss_distance_km"),
        TABLE_OPTIONS,
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    neo_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("asteroids.neo_id", name="fk_approach_asteroid", ondelete="CASCADE")
    )
    approach_date: Mapped[date] = mapped_column(Date)
    approach_datetime: Mapped[datetime | None] = mapped_column(DateTime)
    epoch_ms: Mapped[int] = mapped_column(BigInteger)
    relative_velocity_kps: Mapped[float | None] = mapped_column(DOUBLE)
    relative_velocity_kph: Mapped[float | None] = mapped_column(DOUBLE)
    miss_distance_km: Mapped[float | None] = mapped_column(DOUBLE)
    miss_distance_lunar: Mapped[float | None] = mapped_column(DOUBLE)
    miss_distance_au: Mapped[float | None] = mapped_column(DOUBLE)
    orbiting_body: Mapped[str] = mapped_column(String(20), server_default=text("'Earth'"))
    loaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=NOW_ON_UPDATE)


class OrbitalData(Base):
    """Orbit of an asteroid from NeoWs Lookup (one-to-one with asteroids; cached)."""

    __tablename__ = "orbital_data"
    __table_args__ = (TABLE_OPTIONS,)

    neo_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("asteroids.neo_id", name="fk_orbital_asteroid", ondelete="CASCADE"), primary_key=True
    )
    orbit_class: Mapped[str | None] = mapped_column(String(20))
    orbit_class_description: Mapped[str | None] = mapped_column(String(255))
    eccentricity: Mapped[float | None] = mapped_column(DOUBLE)
    inclination_deg: Mapped[float | None] = mapped_column(DOUBLE)
    orbital_period_days: Mapped[float | None] = mapped_column(DOUBLE)
    first_observation_date: Mapped[date | None] = mapped_column(Date)
    last_observation_date: Mapped[date | None] = mapped_column(Date)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, server_default=NOW_ON_UPDATE)


class PipelineRun(Base):
    """One row per run (the audit log). source says which data source the run fetched from."""

    __tablename__ = "pipeline_runs"
    __table_args__ = (Index("idx_runs_started", "started_at"), TABLE_OPTIONS)

    run_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_type: Mapped[str] = mapped_column(String(20), server_default=text("'manual'"))
    # Added by migration 0002: neows, jpl_cad, sentry, ...
    source: Mapped[str] = mapped_column(String(20), server_default=text("'neows'"))
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=NOW)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), server_default=text("'running'"))
    date_range_start: Mapped[date | None] = mapped_column(Date)
    date_range_end: Mapped[date | None] = mapped_column(Date)
    api_calls: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    records_extracted: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    records_after_dedupe: Mapped[int | None] = mapped_column(Integer)
    rows_inserted: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    rows_updated: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    quality_failures: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    error_message: Mapped[str | None] = mapped_column(Text)


class QualityResult(Base):
    """Result of one data quality check in one run."""

    __tablename__ = "quality_results"
    __table_args__ = (Index("idx_quality_run", "run_id"), TABLE_OPTIONS)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pipeline_runs.run_id", name="fk_quality_run", ondelete="CASCADE")
    )
    check_name: Mapped[str] = mapped_column(String(100))
    passed: Mapped[bool] = mapped_column(Boolean)
    details: Mapped[str | None] = mapped_column(String(500))
    checked_at: Mapped[datetime] = mapped_column(DateTime, server_default=NOW)


class NeoIdAlias(Base):
    """Old provisional neo_id -> numbered neo_id of the same asteroid. See docs/duplicate_ids.md."""

    __tablename__ = "neo_id_aliases"
    __table_args__ = (Index("idx_alias_numbered", "numbered_neo_id"), TABLE_OPTIONS)

    old_neo_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    numbered_neo_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("asteroids.neo_id", name="fk_alias_asteroid", ondelete="CASCADE")
    )
    designation: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=NOW)
