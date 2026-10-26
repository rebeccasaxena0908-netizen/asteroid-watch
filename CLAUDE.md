# Asteroid Watch: notes for Claude

v1 spec: `AsteroidWatch_ClaudeCode_Prompt.md`. v2 spec: `AsteroidWatch_v2_ClaudeCode_Prompt.md` (both gitignored, never commit). Progress: `PROGRESS.md`. v2 plan: `docs/v2_plan.md`. v2 work is on branch `v2`; main stays v1 until Phase 13.
College Data Engineering project (5th sem BCA). Keep the code simple enough to explain in a viva.

## Rules
- Never print, log, or commit `NASA_API_KEY` or `DB_PASSWORD`. `.env` is gitignored and set to owner-only access (chmod 600); `Settings` hides secrets from repr.
- The user fills in `NASA_API_KEY` in `.env` themselves. Never ask for it in chat.
- NeoWs embeds the api_key in response `links` and requests puts it in exception text: always redact (`NeoWsClient.redact`) before saving or logging.
- Tests never hit the network or a real database; use fixtures in `tests/fixtures/`.
- PHP: PDO prepared statements only. PHP never needs the NASA key.
- No fabricated data: the dashboard shows only what's in MySQL.
- Work phase by phase. At the end of each phase: run tests, commit, update PROGRESS.md, stop.

## Environment (verified 2026-10-12)
- XAMPP MariaDB 10.4.28. Socket `/Applications/XAMPP/xamppfiles/var/mysql/mysql.sock`, TCP 127.0.0.1:3306 also works.
- App DB user `asteroid_user` (localhost + 127.0.0.1), privileges only on `asteroid_watch`. MariaDB needs DROP for `CREATE OR REPLACE VIEW`.
- Dashboard DB user `asteroid_reader`: SELECT, SHOW VIEW on asteroid_watch only.
- XAMPP root has no password; it's used only by `pipeline/setup_db.py` (and mysqldump backups).
- XAMPP php.ini has serialize_precision=100: api.php sets it to -1. MySQL SUM() returns strings via PDO: CAST AS UNSIGNED.
- Apache runs as `daemon` and can't read `~/code` (home is 750), so `make deploy` copies with rsync (a symlink gives 403). For the same reason PHP can't read the project `.env`: `make deploy` writes the read-only user's credentials to `/Applications/XAMPP/xamppfiles/etc/asteroid-watch/db.ini` (644).
- NASA key rate limit is 2,000 requests/hour (from X-RateLimit-Limit header).
- PHP 8.2.4 with pdo_mysql. Python 3.14 in `.venv`. Mac timezone is Asia/Kolkata (IST).

## Dashboard notes
- Everything loads locally: three.js/Chart.js/fonts are vendored in dashboard/assets/vendor (hashes in its README, checked by tests). No CDN at runtime.
- ES modules + import map (index.php). Data text only via textContent (tests enforce no innerHTML with data).
- Colours: series-1 #3987e5 = not hazardous, series-2 #d95926 = hazardous (validated); status colours always with icon + label.
- zsh: no word splitting of $var (use arrays or separate vars); BSD sed doesn't turn \n into a newline in replacements.
- Screenshot testing: drive Chrome over CDP (headless, `--use-angle=metal` for the real GPU); `--virtual-time-budget` hangs because of the animation loop.
- PHP strings: write "{$var}–" with braces; a UTF-8 character right after $var becomes part of the variable name.
- XAMPP PHP timezone is Europe/Berlin; all dates come from MySQL (IST), so don't use PHP date().

## Commands
`make install | requirements | lint | hooks | scan-secrets | setup-db | check-db | test | api-test | extract | run | backfill | crosscheck | deploy | undeploy`
`make schedule-install | schedule-uninstall | schedule-status | schedule-run-now` (the user installs the schedule)

## Design notes
- Tooling: deps live in pyproject.toml; requirements.txt is generated (never hand-edit). ruff is lint-only on v1 code (no `ruff format`). pre-commit hooks are local (.venv tools).
- Daily launchd job: when the lid is closed, macOS DarkWakes start the job with no network, then sleep mid-run (runs 13, 20 failed; runs 17–19 took hours). Check `pmset -g log` when diagnosing. Fix planned in Phase 3.
- Upsert counts: PyMySQL doesn't set CLIENT_FOUND_ROWS, so affected = inserts + 2*changed rows.
- Orbital lookups are capped per run (backfill finds ~1,700 asteroids, above the hourly limit if fetched all at once).
- NeoWs feed omits some dates entirely (4 of 396 in the backfill); JPL CAD shows approaches on them, so they're gaps.
- NeoWs lists some asteroids under two neo_ids (old provisional + numbered). transform.merge_aliases stores them under the numbered id (neo_id_aliases table, 60-min same-event tolerance). See docs/duplicate_ids.md. Never delete DB rows without the user's approval: back up first, preview with cleanup_twins, apply with --expect.
- XAMPP mysqldump: --routines fails (old mysql.proc); don't run mysql_upgrade without asking.
- NeoWs is a subset of JPL CAD (~23% of approaches within 0.5 AU on sampled days).
- JPL CAD: query by `spk=<neo_id>`; date-min == date-max returns nothing.
