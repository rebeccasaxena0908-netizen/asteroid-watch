# Progress

| Phase | Status |
|---|---|
| 1. Setup | ✅ Done (2026-10-12) |
| 2. Extract | ✅ Done (2026-10-12) |
| 3. Transform and load | ✅ Done (2026-10-12) |
| 4. Quality checks and scheduling (+ JPL cross-check) | ✅ Done (2026-10-12) |
| 5. PHP JSON API | ✅ Done (2026-10-12) |
| 6. Animated dashboard | ✅ Done (2026-10-12) |
| 7. Docs and submission material | ✅ Done (2026-10-12) |

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

### 4b. Extra quality check: same asteroid under two IDs
- Found while preparing the JPL check: NeoWs lists some asteroids under both an old provisional id and a newer numbered id, e.g. `3430309` "(2008 TC4)" and `2614134` "614134 (2008 TC4)", with identical approaches. UNIQUE(neo_id, epoch_ms) can't catch this.
- New table-level check `no_same_object_under_two_ids` (same designation + epoch under 2+ neo_ids). Current data: **FAIL, 57 approaches stored twice (25 of them hazardous)**.
- Fixed in 4d below.

### 4c. JPL cross-check (`pipeline/jpl_crosscheck.py`, `make crosscheck`)
- Compares a reproducible random sample (seed 42) of stored approaches with the JPL CAD API by SPK-ID (= neo_id), and compares per-day counts within 0.5 AU on the 4 feed-missing days + 10 random days. Saved as a `crosscheck` run (run 6, 64 calls) in pipeline_runs/quality_results; report in `docs/jpl_crosscheck.md`.
- **Values:** 47 of 48 found approaches match (median diff 0.0000% for distance, velocity and time). Outlier: (2019 NG2) 0.57% distance, 21 min (possibly a newer orbit solution; not verified).
- **Objects:** 2 of 50 not found in JPL by their (provisional) SPK-ID: (2015 FV118), (2018 WG2). (2025 US6) is also not found.
- **Coverage:** on 14 sampled days NeoWs gave 50 approaches within 0.5 AU vs JPL's 217 (~23%). On the 4 feed-missing days JPL lists 10, 19, 13 and 11 approaches, so **those are real gaps in NeoWs, not empty days.**
- Gotcha: CAD with date-min = date-max returns 0 rows; use [day, day+1).
- Tests: 68 passing (with a real CAD response fixture).

### 4d. Duplicate-ID fix (approved by the user) — full write-up in `docs/duplicate_ids.md`
- Rule: when a designation is listed under several neo_ids with exactly one numbered, the others are aliases; their approaches are stored under the numbered id, and a copy within 60 min of a numbered-id approach is dropped. New table `neo_id_aliases` remembers mappings for later runs.
- Backup `backups/asteroid_watch_2026-10-12_before_twin_cleanup.sql`, checked by a test restore. `cleanup_twins.py` preview, then apply with `--expect 57,1,56 --skip 54290860`.
- **Before → after:** asteroids 1,684 → 1,628; close_approaches 1,934 → 1,877; hazardous approaches 213 → 188; orbital_data 605 → 578; aliases 0 → 56. (2017 AE5) Jul 4 approach moved to 2755140.
- Run 7 (backfill re-run): 0 inserted / 0 updated; `no_same_object_under_two_ids` 57 → **1** (only the skipped (2022 OP)).
- (2022 OP) cleaned after separate approval (fresh backup, `--expect 1,0,1`). Run 8: `no_same_object_under_two_ids` **PASS (0)**. Final: 1,627 asteroids, 1,876 approaches.
- Tests: 78 passing.

## Phase 5: PHP JSON API (2026-10-12) — reference in `docs/api.md`
- Endpoints in `dashboard/api/`: `summary.php`, `approaches.php` (date range, hazardous filter, name search, 5 sort keys, pagination), `asteroid.php` (detail + orbit + all approaches; old ids resolve to numbered), `trends.php` (daily counts, size histogram, velocity vs distance, hazardous split), `runs.php` (runs + quality results).
- `includes/db.php`: PDO, real prepared statements (`EMULATE_PREPARES=false`), socket first then TCP. `includes/api.php`: JSON responses, GET only, validation helpers, errors 400/404/405/503/500 (no internal details leaked).
- Read-only MySQL user `asteroid_reader` (SELECT, SHOW VIEW on asteroid_watch) created by `make setup-db`; password generated into `.env`.
- `make deploy` writes `/Applications/XAMPP/xamppfiles/etc/asteroid-watch/db.ini` (outside the web root, read-only user only), then rsyncs. `.htaccess`: includes/ → 403, no directory listings.
- Fixed: XAMPP's `serialize_precision=100` printed floats like `7622017.520253947935998…` (now -1); SUM() returned strings (now CAST to integers); JSON is compact by default (trends 646 KB → 362 KB), with `?pretty=1` for reading.
- Tests: `make test` **91 passing** (offline, including 13 PHP CLI tests: lint, validation, MySQL-down message). `make api-test` **10 passing** (live endpoints checked against direct SQL).
- Live numbers (after the duplicate-ID fix): 1,628 asteroids (176 hazardous), 1,877 approaches (188 hazardous), 578 with orbits; this week 38 approaches (8 hazardous); closest on record (2025 US6) at 0.355 LD; largest 433 Eros (max ~49.4 km).

## Phase 6: Animated dashboard (2026-10-12) — http://localhost/asteroid-watch
- `dashboard/index.php` + `assets/css/dashboard.css` + ES modules in `assets/js/` (api, format, ui, charts, table, modal, health, space, main). An import map pins three.js and adds cache-busting versions. Libraries come only from jsdelivr, with exact versions: three@0.160.0, chart.js@4.4.1, @fontsource Inter/Space Grotesk 5.0.18.
- **3D background (`space.js`):** Earth is a procedural shader planet that cross-fades to the local NASA Blue Marble texture (`assets/img/earth_bluemarble_2048.jpg`, 2048×1024, 435 KB, public domain), with day/night terminator, ocean glint, soft atmosphere and 23.4° tilt. Twinkling starfield (2,600; 1,400 on small screens), blurred painted nebula, Moon at 1 LD. **This week's 38 real approaches are the rocks:** orbit radius log-scaled by miss distance, size by diameter, speed by velocity, orange = hazardous. Mouse/touch parallax, drag to rotate with inertia, hover label, click/tap opens the asteroid. Pauses when the tab is hidden, adaptive pixel ratio, on-demand rendering under prefers-reduced-motion.
- **Glass tiles** with count-up numbers (this week, closest, largest, hazardous, last run); closest/largest open the detail modal.
- **Charts (Chart.js):** approaches per day (weekly for the full year) with a Today marker and gaps for missing days; hazardous doughnut; size histogram; speed vs miss-distance scatter (log x, click a dot to open it). Palette checked with the dataviz validator on the chart surface (#141a2e): all checks pass (CVD ΔE 26.8). HTML legends and a "Show data" table under every chart.
- **Table:** server-side search (debounced), hazard filter, time window, sortable headers (aria-sort), pagination, skeleton rows; becomes two-line cards on phones.
- **Detail modal:** size, next/last approach, miss distance in LD/km/AU, speed, a log "how close" scale with the Moon, an orbit sketch from the period (Kepler's 3rd law) and eccentricity vs Earth's orbit, all stored approaches, JPL link, old-ID note.
- **Pipeline health:** latest ETL run with an 8-check meter and a stale warning (> 26 h), plus a run history with each check's result.
- **Errors:** MySQL off shows a banner with Retry, "Database offline" status, and "–" placeholders (never a made-up 0). The 3D scene keeps running.
- **Verified in Chrome (M2 GPU via Metal and SwiftShader):** 61 fps; desktop 1440×900 and phone 390×844 with no horizontal scroll; reduced motion; 3D hover labels; modal; full-year range; search; MySQL-down state. Bugs found and fixed through screenshots: nebula dither grid, atmosphere ring, rocks over the hero text, PHP `"$min–"` UTF-8 interpolation in size labels, "null" text, Indian vs international digit grouping, partial-week dips.
- Tests: `make test` **94 passing** (new: libraries only from allowed CDNs with pinned versions, local texture, no innerHTML with data); `make api-test` **10 passing**.

### 6b. Polish + offline (2026-10-12, requested after review)
- **Hero:** the scene measures the text column and places Earth so that the furthest any orbit can reach on screen (r/√(1−(r/D)²), perspective included) stays right of it; shrinks only if needed. Measured over 4 s of animation: leftmost rock vs text edge at 1100/1280/1440/1920 px wide = +66/+81/+87/+111 px clear.
- **Tile** renamed to "Hazardous asteroids tracked" (all time; sub-line "8 pass this week").
- **Pipeline:** new column `pipeline_runs.records_after_dedupe` (schema + idempotent `sql/03_migrations.sql`); the panel shows "1,934 extracted → 1,876 after dedupe" with a note on the 58 duplicate listings. Run 9 (backfill) is the first run with the value.
- **Size chart:** the 304 vs 305 difference is not a missing size (0 asteroids lack one): the size chart counts asteroids, the others approaches, and (2014 QS295) passes twice in that range. `trends.php` now returns `counts` and the chart explains the difference from the data.
- **JPL cross-check runs** show "Completed · N findings" (info style, "finding" tags) instead of "checks failed".
- **Vendored for offline use:** three.js 0.160.0, Chart.js 4.4.1 (published `dist/chart.umd.js`; the earlier `chart.umd.min.js` was generated on the fly by jsdelivr and isn't part of the package), Inter and Space Grotesk (latin + latin-ext) with their MIT/OFL licences in `dashboard/assets/vendor/` (1.0 MB). All 14 files are checked against jsdelivr's published SHA-256 hashes; `vendor/README.md` records source URLs and hashes, and a test re-checks them.
- **Offline test:** Chrome with jsdelivr/cdnjs/unpkg/Google Fonts blocked: **0 external requests**, 3D scene running, 4 charts drawn, all 4 font weights loaded.
- Tests: `make test` **96 passing**, `make api-test` **10 passing**.

## Phase 7: Docs and submission material (2026-10-12)
- `README.md`: overview with live numbers, Mermaid architecture and ER diagrams, setup from zero (10 steps), commands, data-quality table and findings, **real screenshots** (`docs/screenshots/`, 7 JPEGs, ~1.2 MB), project structure, data sources and licences, limitations.
- `docs/architecture.md` (components, ETL design decisions, security, scheduling, failure handling, testing), `docs/er_diagram.md` (every table, key, index, view, user), `docs/report_outline.md` (college report outline with the project's real numbers and figure list), `docs/demo_script.md` (5-minute script with timings, pre-demo checklist, Plan B, 14 likely viva questions with answers).
- `make quick-run` for live demos (daily range, no orbit lookups): 2.5 s, 8/8 checks pass.
- Verified: a fresh `git clone` (no .env, no data) → `make install` → `make test` = 96 passed; all relative links in the docs resolve; all 4 Mermaid diagrams parse and render (mermaid 10.9.1 in Chrome).

## Final state
- Tables: 1,627 asteroids (176 hazardous), 1,876 approaches (188 hazardous), 578 orbits, 57 ID aliases, 10 runs.
- Tests: `make test` 96 passing (offline), `make api-test` 10 passing.
- Acceptance criteria: `make test` passes without internet ✅ · `make run` fetches, transforms, loads and logs; a re-run creates no duplicates ✅ · dashboard loads from MySQL at http://localhost/asteroid-watch and animates at 60 fps on the M2 ✅ · no API key in git history ✅ (scanned before every commit).
- Still for the user: `make schedule-install` to turn on the daily 09:00 run.

---

# v2 (branch `v2`). Plan, order and estimates: `docs/v2_plan.md`

| Phase | Status |
|---|---|
| 0. Baseline and tooling | ✅ Done (2026-10-27) |
| 1. Python foundation (SQLAlchemy, Alembic, Typer) | ✅ Done (2026-10-27) |
| 2. FastAPI replaces PHP | ✅ Done (2026-10-27) |
| 3. Orchestration with Prefect | ⏳ Next |

Order: 0 → 1 → 2 → 3 → 4 → 5 → 7 → 8 → 9 → 6 → 10 → 11 → 12 → 13.

## v2 Phase 0: Baseline and tooling (2026-10-27)

### Baseline (before any v2 change)
- `make test` **96 passed**, `make api-test` **10 passed**.
- Tables: 1,627 asteroids, 1,876 approaches, **1,078 orbits** (up from 578: the daily runs keep filling them in), 57 aliases, 21 runs, 121 quality results.
- `make quick-run` = **run 21**: 2 API calls, 3.0 s, 51 records → 49 after removing 2 old-ID copies, 0 inserted, 3 updated, 8/8 checks passed.

### Why run 20 failed (and what else the daily job is doing)
- **Cause of run 20: the Mac was asleep (lid closed, on battery), so there was no network.** At 09:11:42 on 26 Oct macOS did a 19-second maintenance wake ("DarkWake", logged by `pmset -g log`). launchd used it to start the missed 09:00 job. Wi-Fi isn't connected during a DarkWake, so the first 4 requests failed within 40 ms each (ConnectionError, never reached NASA). The Mac went back to sleep at 09:12:01, during the 16 s backoff, and the process stayed frozen until the next DarkWake at 09:44:14. The 5th attempt then also failed, and the run was marked failed at 09:44:15. The retries worked as designed. They were just all used up within one 19-second window with no network.
- **Same mechanism, different ending: runs 17–19 took 3–6 hours.** Run 17 started in a 2-second DarkWake at 09:07:36, was frozen when the Mac slept at 09:07:38, and finished at 15:07 when the lid was opened. Run 13 (13 Oct) failed exactly like run 20. The power log no longer covers that date, so this is likely but not verified.
- **19, 20 and 21 Oct: XAMPP MySQL wasn't running** ("Connection refused"). These runs couldn't write to `pipeline_runs`, so they're only in `logs/launchd.err.log`. The dashboard's "> 26 h" stale warning is what shows them.
- **14–18 and 22 Oct: no log entry at all.** The job didn't start. launchd catches up a missed run after sleep, but not after a shutdown, so the Mac was probably off.
- **No data was lost.** Every day has approaches in the database (the v1 backfill reached 11 Nov). The missed runs only lost NASA's updates for those days.
- **Fix: planned for Phase 3 (Prefect), not changed now.** Check the network before extracting and wait for a real wake if it's down. Retry the whole flow later (minutes apart, not seconds). Record failed attempts even when MySQL is down. Optionally, you could schedule a full wake just before 09:00 (`sudo pmset repeat wake …`). That's a system setting, so it's your choice.

### Tooling
- `pyproject.toml`: metadata, dependencies (runtime + `dev`), pytest/ruff/mypy settings. `make install` = `pip install -e ".[dev]"`. `requirements.txt` is generated (`make requirements`, `scripts/gen_requirements.py`); a test and a hook keep it in sync.
- **ruff** (lint: E, W, F, I, B, UP; line length 120) and **mypy** (non-strict): `make lint`. Fixes needed in v1 code, none changing behaviour: 1 lambda → def, an explicit `zip(strict=False)`, import order in 3 test files, and 5 type hints (`rate_limit_remaining: int | None`, `diameter_m(dict | None)`, an explicit "unreachable" after the retry loop). `ruff format` wasn't applied to v1, to avoid rewriting ~700 lines.
- **pre-commit** (`make hooks`, installed): secret scan, requirements in sync, ruff, mypy. All local hooks using `.venv`.
- **Secret scan** `scripts/check_secrets.py` (`make scan-secrets`): searches files for the real `.env` secret values and for credential patterns; prints names only. Scanned the working tree and **all 11 commits of history: no secrets found.**
- **GitHub Actions** `.github/workflows/tests.yml`: Python 3.14 + PHP 8.2 (pdo_mysql) on Ubuntu; lint, type check, requirements check, secret-pattern scan, offline tests.
- The daily launchd job is unchanged and still imports correctly under `env -i` (as launchd runs it).
- Docs: `docs/v2_plan.md` (order, decisions, memory/disk estimates, final folder structure), `docs/tooling.md` (how it works).
- Tests: `make test` **101 passed** (96 v1 + 5 tooling), `make api-test` **10 passed**.

## v2 Phase 1: Python foundation (2026-10-27) — how it works: `docs/schema_and_cli.md`
- **SQLAlchemy 2.x models** (`pipeline/models.py`, SQLAlchemy 2.1.6, 2.0-style API): all 6 tables with exact types, NULLs, defaults (incl. ON UPDATE CURRENT_TIMESTAMP), keys, index/FK names, ON DELETE CASCADE, InnoDB/utf8mb4. Before the migration, `alembic check` against the live DB (types and server defaults compared) showed exactly one difference: the new `source` column. After it: **no differences**.
- `pipeline.db.engine()`: SQLAlchemy engine with the v1 socket-or-TCP rule; password in connect_args, never in the URL.
- **Alembic** (`alembic.ini` without credentials, `migrations/`): `0001_v1_baseline` runs the v1 SQL files (now marked frozen); `0002_pipeline_runs_source` adds `source VARCHAR(20) NOT NULL DEFAULT 'neows'` after `run_type` and sets cross-check runs to `jpl_cad`.
  - Live DB: backup `backups/asteroid_watch_2026-10-27_before_alembic.sql` (857 KB, test restore: 6/6 table counts and 5 views match) → `alembic stamp 0001_v1_baseline` → `alembic upgrade head` (ran 0002 only). Row counts unchanged: 1,627 / 1,876 / 1,078 / 57 / 21 / 121. Runs by source: neows 20, jpl_cad 1.
  - Fresh-DB test: both migrations on an empty throwaway database → 6 tables + alembic_version + 5 views, `alembic check` clean; dropped.
  - `setup_db.py` now creates the DB and users, then runs `alembic upgrade head` (instead of the SQL files).
- Pipeline writes `source`: `neows` for ETL runs, `jpl_cad` for cross-checks. PHP API output unchanged (its queries list columns explicitly).
- **Typer CLI `asteroid-watch`** (`pipeline/cli.py`): `run`, `quick-run`, `backfill`, `crosscheck`, `status`, `test [--api]`, `migrate`, `setup-db`, `check-db`, `serve` (placeholder until Phase 2: prints how to use the XAMPP dashboard, exit 1). Makefile targets call it; options identical to v1 (tested). Typer's local-variable display in tracebacks is off (could show passwords).
- `asteroid-watch status` now: schema 0002 (up to date); neows last success run 22; jpl_cad last success run 6 (14 days ago, 3 findings).
- Live check: `make quick-run` via the CLI = **run 22**: 2 API calls, 51 → 49 records, 0 inserted, 0 updated, 8/8 checks passed, `source = neows`. The launchd command (`python -m pipeline.run_pipeline`) is unchanged and imports fine under `env -i`.
- Tests: `make test` **118 passed** (101 + 17: models vs SQL files, migration history and offline SQL, CLI option mapping, status without MySQL, no locals in tracebacks). `make api-test` **13 passed** (10 API + 3 new: DB at head, models = live DB, status).

### Phase 3 requirements added by the user (2026-10-27)
- Before extracting, wait until the network is actually reachable: check every few minutes for up to 2 hours, instead of failing within seconds.
- If XAMPP MySQL isn't running: record the failure in a local log file and retry later the same day.
- Move the daily time from 09:00 to an evening time (IST) when the Mac is usually open; keep the catch-up-on-wake behaviour. **19:00 IST** (confirmed by the user).
- No `pmset`.

## v2 Phase 2: FastAPI replaces PHP (2026-10-27) — reference and how it works: `docs/api.md`
- **FastAPI app** (`api/`, FastAPI 0.162, Pydantic 2.14, uvicorn 0.54): the 5 endpoints at `/api/summary|approaches|asteroid|trends|runs`, one route module per PHP file. Same SQL as PHP (SQLAlchemy `text()` with bound `:params`), validation ported one-for-one (`api/params.py`, same messages and order), same errors (400/404/405/503/500) and headers. Connects as `asteroid_reader` from `.env`.
- Values converted to what PHP's PDO sent (`api/db.py`): DECIMAL → `"21.650"`, DATE/DATETIME → strings, BOOLEAN → true/false. **Strict** Pydantic response models (`api/schemas.py`) check every response and generate `/docs`.
- **Parity tests** (`tests/parity/test_parity.py`, `make parity-test`): **104 passed, every body byte-for-byte identical** to PHP. Covered: all endpoints, ± `pretty=1`, all sorts/filters, 11 searches incl. `%`, `_`, `\`, injection text and "–", all **1,684** asteroid IDs + aliases, every page of approaches, 21 bad inputs, POST/PUT/DELETE. A deliberately broken DECIMAL conversion was caught (by the comparison and, earlier, by the strict model).
- **Switch done after parity passed:** `dashboard/index.html` (static, rendered once from index.php; `?v=` URLs replaced by `Cache-Control: no-cache` + ETag revalidation); JS calls `/api/<name>`; PHP moved with `git mv` to `legacy/php/` (api/, includes/, index.php, .htaccess) with a README. `make legacy-deploy` / `legacy-undeploy` put the PHP API back on XAMPP for parity tests (only api/ and includes/ are replaced).
- **Served by FastAPI:** dashboard at `/`, `dashboard/assets/` only (path traversal → 404, tested), `/docs` with **Swagger UI 5.33.2 vendored** (`api/static/swagger-ui/`, 4 files, SHA-256 matched jsdelivr's published hashes; re-checked by a test) so docs work offline.
- **Exports:** `/api/approaches.csv|.xlsx` (the table's current filters and sort, all pages, ≤ 100,000 rows) and `/api/runs.csv|.xlsx`; buttons in the table toolbar and the pipeline section. UTF-8 BOM for Excel; formula-injection protection (`= + - @` cells get `'`). Live check: hazardous CSV = 188 rows = API total; runs Excel = 22 runs with numeric cells.
- **Server:** `asteroid-watch serve` (uvicorn, 1 worker, 127.0.0.1:8000; `--port`, `--reload`), `make serve`. **launchd agent** `scheduler/com.asteroidwatch.api.plist` (RunAtLoad, KeepAlive, ThrottleInterval 10, logs/api.*.log); `make api-install | api-status | api-restart | api-uninstall`. **Not installed: the user installs it.** Measured: 36 MB resident while serving (estimate was ~120 MB; macOS may compress idle memory).
- **Port conflict found:** port 8000 is already used by another project of the user's (`~/Desktop/Remembrance/backend`, uvicorn, running since 23 Oct). Left untouched; tested on 8010. The API agent will fail to bind 8000 while that runs (see question in the Phase 2 summary).
- **Browser check** (headless Chrome over CDP, Metal GPU, on :8010): 1440×900 and 390×844 — 26 requests, 0 errors, 0 failed, 0 external, 4 charts, live tiles, 15 table rows, 10 runs; clicking "Hazardous" changed the count 95 → 17 and the CSV link's filters; phone width has no horizontal scroll.
- **Test changes (intended interface changes):** `tests/test_php.py` now points at `legacy/php/`; `tests/test_dashboard_assets.py` checks `index.html` (+ a new test: no PHP left in `dashboard/`); `tests/integration/test_api.py` runs each v1 check against FastAPI and, when deployed, PHP; CLI tests updated for the real `serve` and `test --parity`. Test client: `httpx2` (Starlette deprecates `httpx`).
- README, `docs/api.md`, `scheduler/README.md` updated (full README rewrite in Phase 13).
- Tests: `make test` **155 passed** (36 new API tests: validation before DB access, 503s, 405/404, headers, value conversion, strict models, SQL stays parameterised, formula-safe exports, static boundaries, local `/docs`, Swagger hashes); `make api-test` **23 passed**; `make parity-test` **104 passed**.
