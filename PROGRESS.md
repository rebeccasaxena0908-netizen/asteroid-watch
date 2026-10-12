# Progress

| Phase | Status |
|---|---|
| 1. Setup | ✅ Done (2026-10-12) |
| 2. Extract | ✅ Done (2026-10-12) |
| 3. Transform and load | ✅ Done (2026-10-12) |
| 4. Quality checks and scheduling (+ JPL cross-check) | ⏳ Next |
| 5. PHP JSON API | |
| 6. Animated dashboard | |
| 7. Docs and submission material | |

## Phase 1: Setup (2026-10-12)
- Checked XAMPP: MariaDB 10.4.28 reachable via socket and TCP; Apache + PHP 8.2.4 (pdo_mysql) running.
- Python venv `.venv` with requests, python-dotenv, PyMySQL, pytest (`requirements.txt`).
- `.env.example` (placeholders) and `.env` (gitignored, chmod 600, random DB password, NASA key placeholder).
- `pipeline/setup_db.py` creates database `asteroid_watch` and user `asteroid_user`, with privileges limited to that database.
- `sql/01_schema.sql`: asteroids, close_approaches (UNIQUE neo_id+epoch_ms), orbital_data, pipeline_runs, quality_results, with indexes on approach_date, miss_distance_km, is_potentially_hazardous.
- `sql/02_views.sql`: the 5 dashboard views.
- Deploy test: a symlink into htdocs gives HTTP 403 (Apache user `daemon` can't read the home folder); an rsync copy gives HTTP 200. `make deploy` copies.
- Tests: 13 passing (config, socket/TCP selection, secret hiding, SQL file checks).
- Git repo initialised; public GitHub repo `asteroid-watch` created.

## Phase 2: Extract (2026-10-12)
- `pipeline/extract.py`: NeoWs feed client. Splits ranges into 7-day chunks; retries 429/5xx/network errors with exponential backoff (2s, 4s, 8s, 16s) or `Retry-After`; logs `X-RateLimit-Remaining`; saves raw JSON to `data/raw/<run date>/feed_<start>_<end>.json`.
- The API key is redacted from raw files (NeoWs puts it inside `links` URLs) and from all error messages.
- `tests/fixtures/feed_sample.json`: a real response trimmed to 4 approaches (redacted).
- Tests: 27 passing (chunking, the 57-call backfill math, retries/backoff, Retry-After, no key in errors or files).
- Real run (2026-10-05 to 2026-10-19, 15 days): **3 API calls, 15/15 days returned, 86 close approaches (= API element_count), 86 unique asteroids, 16 potentially hazardous.** Rate limit is 2,000/hour (1,997 left after the run). Busiest day: 2026-10-17 with 11 approaches.

## Phase 3: Transform and load (2026-10-12)
- `pipeline/transform.py`: flattens feed JSON into asteroid and approach rows; string numbers become floats/ints; diameters in meters (km x 1000 fallback); `2026-Oct-19 00:44` becomes a datetime; dedupes by neo_id and (neo_id, epoch_ms); rejects rows with no id, date or epoch.
- `pipeline/load.py`: upserts with `INSERT ... ON DUPLICATE KEY UPDATE` in batches of 500, in one transaction. Inserted vs updated counts come from row counts before and after plus affected rows.
- Orbital data: NeoWs Lookup for asteroids with no orbit or one older than 30 days, hazardous first, capped per run (`--orbital-limit`, default 100) to respect the rate limit. Raw responses saved as `neo_<id>.json`.
- `pipeline/run_pipeline.py`: CLI (`--backfill-days`, `--forward-days`, `--orbital-limit`, `--run-type`, `--dry-run`); every run is logged in `pipeline_runs` (failed runs too, with a redacted error).
- `make run` (yesterday..+7) and `make backfill` (365..+30, 500 orbit lookups).
- Tests: 50 passing. A new real Lookup fixture is trimmed and redacted.

**Backfill results (2025-10-12 to 2026-11-11):**

| Table | Rows |
|---|---|
| asteroids | 1,684 (201 potentially hazardous) |
| close_approaches | 1,934 (213 hazardous; 197 upcoming) |
| orbital_data | 505 (APO 313, ATE 119, AMO 71, IEO 2); the rest fill in on daily runs |
| pipeline_runs | 3 |

- Run 2 (backfill): 557 API calls (57 feed + 500 lookups), 279 s.
- **Re-run proof:** run 3 repeated the same backfill: 1,934 records extracted, **0 inserted, 0 updated**, table counts unchanged, 0 duplicate (neo_id, epoch_ms) groups.
- Spot check: 5 random DB rows match the raw JSON exactly (name, date, km, lunar, km/s, diameter, hazard flag).
- Finding for Phase 4: 4 of 396 dates are missing from the API response entirely (2026-01-19, 2026-04-16, 2026-04-20, 2026-08-16). Not yet known whether those days had no approaches or are data gaps.
- Interesting: (2025 US6) has 5 approaches within 0.36–1 lunar distance between 2025-10-12 and 2025-12-02, at only about 2 km/s.

## Phase 4: Quality checks and scheduling (2026-10-12)

### 4a. Quality checks and daily schedule
- `pipeline/quality.py`: 7 checks run after every load and saved to `quality_results`; the failure count goes to `pipeline_runs.quality_failures`. A failed check is recorded but does not stop the run.
  - On the run's batch: `not_null_keys`, `miss_distance_positive`, `velocity_positive`, `diameter_min_le_max`, `expected_days_fetched`, `row_count_matches_element_count`.
  - On the whole table: `no_duplicate_approaches`.
- Logging: `logs/pipeline.log` (rotating, 1 MB x 5) as well as the terminal.
- Real results: run 4 (daily range, 9 days): **7/7 passed**. Run 5 (full backfill): **6/7 passed**; `expected_days_fetched` failed: 392 of 396 days returned (missing 2026-01-19, 2026-04-16, 2026-04-20, 2026-08-16).
- Orbital data now 605 rows (run 4 added 100).
- `scheduler/com.asteroidwatch.pipeline.plist`: launchd template, daily 09:00 IST, yesterday..+7 days, `--run-type daily`. Install/uninstall: `make schedule-install` / `make schedule-uninstall` (see `scheduler/README.md`). Checked with `plutil -lint` and a dry run under an empty environment (`env -i`). **Not installed yet: the user runs it.**
- Tests: 59 passing.
