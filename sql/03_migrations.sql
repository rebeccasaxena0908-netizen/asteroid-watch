-- Asteroid Watch: changes to tables that already exist. Safe to re-run (IF NOT EXISTS).

-- Approach records left after deduplication (records_extracted minus duplicate listings),
-- so the dashboard can explain "1,934 extracted -> 1,876 after dedupe". NULL for older runs.
ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS records_after_dedupe INT NULL AFTER records_extracted;
