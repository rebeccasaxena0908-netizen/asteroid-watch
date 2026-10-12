# Progress

| Phase | Status |
|---|---|
| 1. Setup | ✅ Done (2026-10-12) |
| 2. Extract | ⏳ Next |
| 3. Transform and load | |
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

### To do for you
- Put your NASA key in `.env` (`NASA_API_KEY=...`) before Phase 2's real run.
