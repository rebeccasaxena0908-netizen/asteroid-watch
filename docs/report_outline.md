# Project report outline: Asteroid Watch

An outline for the college report (BCA 5th semester, Data Engineering). Each section lists what to write, the facts and numbers to use (all measured in this project), and the figures to include. The figures are already in `docs/screenshots/` or rendered from the Mermaid diagrams in the README and `docs/`.

Suggested length: 25–35 pages, including figures.

---

## Front matter

- Title page: *Asteroid Watch: An Automated Data Pipeline for Tracking Near-Earth Objects using NASA APIs*
- Certificate / declaration / acknowledgements (as your college requires)
- Table of contents, list of figures, list of tables

## Abstract (about 200 words)

Cover: the problem (tracking near-Earth asteroids from public NASA data), what was built (an automated ETL pipeline from NASA APIs to Python to MySQL, plus a PHP JSON API and an animated dashboard), how it runs (daily with launchd), and key results:
- One year of data loaded: **1,876 close approaches** by **1,627 asteroids**, 12 Oct 2025 – 11 Nov 2026
- **Idempotent:** re-running the whole year inserted **0 rows**
- **8 automated quality checks** per run
- **Two real data-quality problems found in NASA's feed:** the same asteroid under two IDs (58 duplicate listings), and missing days
- **Cross-checked with NASA JPL:** values match (median difference 0.0000%), but NeoWs holds only about 23% of the approaches JPL lists

## 1. Introduction

- 1.1 **Background:** near-Earth objects (NEOs), close approaches, lunar distance (LD) and astronomical unit (AU), and NASA's "potentially hazardous asteroid" classification (not an impact prediction).
- 1.2 **Motivation:** public data is available but nested and raw; turning it into a reliable, queryable, monitored dataset is a data engineering problem.
- 1.3 **Problem statement:** collect NEO close-approach data automatically every day, store it cleanly without duplicates, verify its quality, and present it clearly.
- 1.4 **Scope:** NASA NeoWs (feed + lookup), plus JPL CAD for validation; a single machine (XAMPP on macOS).

## 2. Objectives

1. Extract data from the NASA NeoWs API within its limits (7 days per request; hourly rate limit).
2. Transform nested JSON into normalised relational tables.
3. Load into MySQL idempotently (re-runs create no duplicates).
4. Automate daily runs and log every run.
5. Check data quality on every run and validate against an independent source (JPL).
6. Serve the data through a secure API and an interactive dashboard.
7. Keep secrets out of code and version control.

## 3. Tools and technologies

A table with each tool, its version and why it was chosen:

| Tool | Version | Why |
|---|---|---|
| Python | 3.14 | ETL scripting, rich standard library |
| requests / PyMySQL / python-dotenv / pytest | 2.34 / 1.2 / 1.2 / 9.1 | HTTP, pure-Python MySQL driver (simple to install), config, tests |
| XAMPP: MariaDB, Apache, PHP | MariaDB 10.4.28, PHP 8.2.4 | Course-standard local stack |
| PDO | (PHP built-in) | Prepared statements against SQL injection |
| Three.js / Chart.js | 0.160.0 / 4.4.1 | 3D scene; charts |
| macOS launchd | | Built-in scheduler (cron's modern replacement on macOS) |
| Git + GitHub | | Version control, public repository |

## 4. System architecture

- Figure: the **architecture diagram** (README, "Architecture").
- Explain the **medallion layers:** bronze (raw JSON files), silver (clean rows in memory), gold (MySQL tables + views).
- Explain the components and the data flow of one daily run (see `docs/architecture.md`, sections 1–8).
- Figure: dashboard hero (`docs/screenshots/01_hero.jpg`).

## 5. ETL design

- 5.1 **Extract:** 7-day chunking (one year = 57 calls), retries with exponential backoff (2 s, 4 s, 8 s, 16 s) or `Retry-After`, rate-limit logging, raw JSON storage, **API key redaction** (NeoWs embeds the key in its response links). Include the retry table from architecture.md, section 2.
- 5.2 **Transform:** a flattening example (show the nested JSON path and the resulting row); type conversion (numbers arrive as text); units; dedupe by `(neo_id, epoch_ms)`; the old-ID → numbered-ID mapping.
- 5.3 **Load:** upserts (`INSERT … ON DUPLICATE KEY UPDATE`), why upserts make runs idempotent, counting inserts vs updates from affected rows, transactions, batching.
- 5.4 **Orbital data:** caching and per-run caps to respect the rate limit.
- 5.5 **Scheduling and logging:** launchd at 09:00 IST, `pipeline_runs`, the rotating log file.
- Table: the pipeline runs (from `pipeline_runs`: run ID, type, range, API calls, records extracted → after dedupe, inserted, quality failures).

## 6. Database design

- Figure: the **ER diagram** (`docs/er_diagram.md`).
- Each table and its keys. Why `UNIQUE(neo_id, epoch_ms)`. Why the indexes (date range, distance sort, hazard filter). The views as the "gold" layer.
- Security: two database users (read/write for the pipeline, read-only for the dashboard), each limited to one database.
- Table: row counts per table (er_diagram.md, "Current size").

## 7. Data quality

- 7.1 **The 8 checks** (README, "Data quality"), with the latest results.
- 7.2 **Case study: the same asteroid under two IDs** (`docs/duplicate_ids.md`). How it was found (JPL redirected an old ID), its size (58 duplicate listings, 25 of them hazardous, so hazardous approaches overcounted by about 12%), the rule, the alias table, and the cleanup procedure (backup, test restore, preview, approval, guarded apply). Include the before/after table.
- 7.3 **Case study: cross-check with NASA JPL** (`docs/jpl_crosscheck.md`):
  - Values: 47 of 48 found approaches match within 1% (median 0.0000%).
  - Objects: 2 of 50 sampled IDs aren't in JPL.
  - Coverage: NeoWs 50 vs JPL 217 approaches on 14 sampled days (about 23%).
  - The 4 days missing from the feed have 10–19 approaches each in JPL.
- 7.4 **Lessons:** validate against an independent source; a "unique" constraint is only as good as its key.

## 8. Implementation highlights

- PHP JSON API: endpoints, validation, prepared statements, friendly errors (`docs/api.md`).
- Dashboard features, with figures `02`–`07` from `docs/screenshots/`: tiles, charts, table, detail view, pipeline health, mobile.
- Visualisation choices: colour-blind-safe palette (validated), log scales for distance, a "Show data" table under every chart.
- Offline operation: vendored libraries with checked hashes.

## 9. Testing

- Unit tests (96, offline, real-data fixtures) and API integration tests (10, against live SQL). List the categories (architecture.md, section 12).
- The **idempotency test:** a full re-run inserted 0 rows.
- Manual and visual testing: screenshots at several screen sizes, reduced-motion mode, the MySQL-off state, and blocked-CDN (offline) mode.

## 10. Results

- Data volume: 1,876 approaches, 1,627 asteroids (176 hazardous), 578 with orbits. The pipeline used 951 NASA API calls across all ETL runs.
- Interesting findings for the report:
  - Closest approach on record: **(2025 US6)** at **0.355 LD (136,611 km)** on 13 Nov 2025. Closer than the Moon, and it passed 5 times in about 7 weeks at only about 2 km/s.
  - Largest tracked object: **433 Eros** (up to about 49 km).
  - Average **4.8 approaches per day** in NeoWs; busiest day 12.
  - Orbit classes among the 578 with orbital data: Apollo 345, Aten 147, Amor 84, Atira 2.
- Figures: the charts (approaches per week over the full year, size distribution, speed vs distance).

## 11. Limitations

Use the README's "Limitations" section: NeoWs coverage, the duplicate-ID rule, partial orbital data, the Mac-dependent scheduler, not-to-scale visuals, a single-machine setup.

## 12. Future scope

- Use JPL CAD as a **second source** to fill NeoWs's gaps (merge and deduplicate by designation and time).
- Fetch orbital data for all asteroids gradually; show the real orbit orientation using more orbital elements.
- Alerts (email or Telegram) when a hazardous asteroid comes within a threshold, or when a run fails.
- Move from XAMPP to Docker or a cloud database; schedule with Airflow for retries and monitoring.
- Incremental data-quality dashboards (trends of check results over time).
- Analysis: seasonal patterns in discoveries, and the size–distance relationship.

## 13. Conclusion (half a page)

Restate the objectives and how each was met, with the strongest results: automated, idempotent, quality-checked, validated against JPL, secure, and presented clearly.

## References

- NASA NeoWs API: https://api.nasa.gov/
- NASA JPL SBDB Close-Approach Data API: https://ssd-api.jpl.nasa.gov/doc/cad.html
- NASA CNEOS, "NEO Basics" (definitions of NEO, PHA, orbit classes): https://cneos.jpl.nasa.gov/about/neo_groups.html
- NASA Visible Earth, Blue Marble: Next Generation: https://visibleearth.nasa.gov/images/73909
- MariaDB documentation, INSERT … ON DUPLICATE KEY UPDATE: https://mariadb.com/kb/en/insert-on-duplicate-key-update/
- PHP manual, PDO prepared statements: https://www.php.net/manual/en/pdo.prepared-statements.php
- Apple Developer documentation, launchd / `launchd.plist`
- three.js: https://threejs.org/ · Chart.js: https://www.chartjs.org/

## Appendices

- A. Setup steps (README, "Setup from zero")
- B. Sample raw JSON and the rows it becomes (`tests/fixtures/feed_sample.json`)
- C. Full SQL schema (`sql/`)
- D. API reference (`docs/api.md`)
- E. JPL cross-check report (`docs/jpl_crosscheck.md`)
