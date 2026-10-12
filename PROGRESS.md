# Progress

| Phase | Status |
|---|---|
| 1. Setup | ✅ Done (2026-10-12) |
| 2. Extract | ✅ Done (2026-10-12) |
| 3. Transform and load | ⏳ Next |
| 4. Quality checks and scheduling (+ JPL cross-check) | |
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
