# Asteroid Watch: notes for Claude

Full spec: `AsteroidWatch_ClaudeCode_Prompt.md`. Progress: `PROGRESS.md`.
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
- XAMPP root has no password; it's used only by `pipeline/setup_db.py`.
- Apache runs as `daemon` and can't read `~/code` (home is 750), so `make deploy` copies with rsync (a symlink gives 403). For the same reason PHP can't read the project `.env`; it needs its own config file in a location `daemon` can read.
- NASA key rate limit is 2,000 requests/hour (from X-RateLimit-Limit header).
- PHP 8.2.4 with pdo_mysql. Python 3.14 in `.venv`. Mac timezone is Asia/Kolkata (IST).

## Commands
`make install | setup-db | check-db | test | extract | deploy | undeploy`
