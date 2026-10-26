-- FROZEN (v2): this is the v1 baseline, run by Alembic migration 0001_v1_baseline.
-- Don't edit it or run it by hand: schema changes go in migrations/versions/.
-- Asteroid Watch: core schema (MySQL / MariaDB, InnoDB, utf8mb4)
-- Safe to re-run: every table uses CREATE TABLE IF NOT EXISTS.
-- The database itself is created by pipeline/setup_db.py.

-- One row per asteroid (near-Earth object).
CREATE TABLE IF NOT EXISTS asteroids (
    neo_id                    VARCHAR(20)   NOT NULL,
    name                      VARCHAR(100)  NOT NULL,
    nasa_jpl_url              VARCHAR(255)  NULL,
    absolute_magnitude_h      DECIMAL(6,3)  NULL,
    est_diameter_min_m        DOUBLE        NULL,
    est_diameter_max_m        DOUBLE        NULL,
    is_potentially_hazardous  BOOLEAN       NOT NULL DEFAULT FALSE,
    is_sentry_object          BOOLEAN       NOT NULL DEFAULT FALSE,
    first_seen_at             DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at                DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (neo_id),
    INDEX idx_asteroids_hazardous (is_potentially_hazardous)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- One row per close approach of an asteroid to a body (usually Earth).
-- UNIQUE(neo_id, epoch_ms) means re-running the pipeline never creates duplicates.
CREATE TABLE IF NOT EXISTS close_approaches (
    id                     BIGINT        NOT NULL AUTO_INCREMENT,
    neo_id                 VARCHAR(20)   NOT NULL,
    approach_date          DATE          NOT NULL,
    approach_datetime      DATETIME      NULL,
    epoch_ms               BIGINT        NOT NULL,
    relative_velocity_kps  DOUBLE        NULL,
    relative_velocity_kph  DOUBLE        NULL,
    miss_distance_km       DOUBLE        NULL,
    miss_distance_lunar    DOUBLE        NULL,
    miss_distance_au       DOUBLE        NULL,
    orbiting_body          VARCHAR(20)   NOT NULL DEFAULT 'Earth',
    loaded_at              DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_approach (neo_id, epoch_ms),
    INDEX idx_approach_date (approach_date),
    INDEX idx_miss_distance (miss_distance_km),
    CONSTRAINT fk_approach_asteroid FOREIGN KEY (neo_id)
        REFERENCES asteroids (neo_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Orbital details from the NeoWs Lookup API (cached; refetched only when missing or stale).
CREATE TABLE IF NOT EXISTS orbital_data (
    neo_id                   VARCHAR(20)   NOT NULL,
    orbit_class              VARCHAR(20)   NULL,
    orbit_class_description  VARCHAR(255)  NULL,
    eccentricity             DOUBLE        NULL,
    inclination_deg          DOUBLE        NULL,
    orbital_period_days      DOUBLE        NULL,
    first_observation_date   DATE          NULL,
    last_observation_date    DATE          NULL,
    fetched_at               DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (neo_id),
    CONSTRAINT fk_orbital_asteroid FOREIGN KEY (neo_id)
        REFERENCES asteroids (neo_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- One row per pipeline execution (audit log).
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id             INT           NOT NULL AUTO_INCREMENT,
    run_type           VARCHAR(20)   NOT NULL DEFAULT 'manual',  -- manual / daily / backfill
    started_at         DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at        DATETIME      NULL,
    status             VARCHAR(20)   NOT NULL DEFAULT 'running', -- running / success / failed
    date_range_start   DATE          NULL,
    date_range_end     DATE          NULL,
    api_calls          INT           NOT NULL DEFAULT 0,
    records_extracted  INT           NOT NULL DEFAULT 0,
    records_after_dedupe INT         NULL,                       -- approaches left after removing duplicate listings
    rows_inserted      INT           NOT NULL DEFAULT 0,
    rows_updated       INT           NOT NULL DEFAULT 0,
    quality_failures   INT           NOT NULL DEFAULT 0,
    error_message      TEXT          NULL,
    PRIMARY KEY (run_id),
    INDEX idx_runs_started (started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Result of each data quality check, per run.
CREATE TABLE IF NOT EXISTS quality_results (
    id          INT           NOT NULL AUTO_INCREMENT,
    run_id      INT           NOT NULL,
    check_name  VARCHAR(100)  NOT NULL,
    passed      BOOLEAN       NOT NULL,
    details     VARCHAR(500)  NULL,
    checked_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_quality_run (run_id),
    CONSTRAINT fk_quality_run FOREIGN KEY (run_id)
        REFERENCES pipeline_runs (run_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Old provisional neo_ids that NeoWs also lists under a newer numbered neo_id (same designation),
-- e.g. 3430309 "(2008 TC4)" -> 2614134 "614134 (2008 TC4)". The pipeline stores approaches
-- of an old id under its numbered id. See docs/duplicate_ids.md.
CREATE TABLE IF NOT EXISTS neo_id_aliases (
    old_neo_id       VARCHAR(20)   NOT NULL,
    numbered_neo_id  VARCHAR(20)   NOT NULL,
    designation      VARCHAR(50)   NOT NULL,
    created_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (old_neo_id),
    INDEX idx_alias_numbered (numbered_neo_id),
    CONSTRAINT fk_alias_asteroid FOREIGN KEY (numbered_neo_id)
        REFERENCES asteroids (neo_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
