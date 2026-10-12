# Dashboard JSON API

Base URL: `http://localhost/asteroid-watch/api/`. These are PHP files served by XAMPP Apache. Everything is read from MySQL using a **read-only** user (`asteroid_reader`: SELECT and SHOW VIEW on `asteroid_watch` only).

- Only `GET` is accepted (other methods get 405).
- Success: `{"data": ...}` with HTTP 200. Errors: `{"error": "message"}` with 400 (bad input), 404 (not found), 503 (MySQL off or config missing) or 500 (other; the details go only to Apache's error log).
- Add `pretty=1` to any request for indented JSON.
- All SQL uses PDO prepared statements with bound values. Sort columns and directions come from fixed whitelists, never from the request.

| Endpoint | Parameters | Returns |
|---|---|---|
| `summary.php` | none | `totals` (asteroids, approaches, hazardous counts, orbits, date range), `this_week` (today + 6 days), `closest_this_week`, `closest_upcoming`, `closest_on_record`, `largest`, `last_run` (latest ETL run with its quality failure count) |
| `approaches.php` | `start`, `end` (YYYY-MM-DD); `hazardous` = all/true/false; `q` (name search, ≤ 50 chars, `%`/`_` matched literally); `sort` = date/distance/velocity/size/name; `order` = asc/desc; `page` (1–10000); `per_page` (1–100, default 25) | `items`, `page`, `per_page`, `total`, `total_pages`, `filters` |
| `asteroid.php` | `id` (numeric neo_id, required) | `asteroid`, `orbit` (or null if not fetched yet), `approaches`, `old_ids`, `resolved_from` (set when an old provisional ID was requested; see `duplicate_ids.md`) |
| `trends.php` | `start`, `end` (optional) | `daily` (counts per day), `size_histogram` (8 bins by max diameter), `velocity_vs_distance` (one point per approach), `hazardous_split` |
| `runs.php` | `limit` (1–50, default 10) | `runs`, newest first, each with its `quality` check results (ETL and cross-check runs) |

## Configuration

`make deploy` writes `/Applications/XAMPP/xamppfiles/etc/asteroid-watch/db.ini` from `.env` (`pipeline/dashboard_config.py`), then copies `dashboard/` to htdocs.

- **Why not `.env`?** The file has to live outside the web root, and Apache's `daemon` user can't read the project's `.env` inside the home folder.
- **What it contains:** only the read-only user. It never holds the NASA key or the pipeline user's password.

Web-facing protections: `includes/.htaccess` blocks direct access to the PHP helpers (403), and `dashboard/.htaccess` turns off directory listings.

## Tests

- `make test` (offline): PHP lint, input validation for every endpoint (rejected before any database access), and the "MySQL is off" and "config missing" error messages.
- `make api-test` (needs XAMPP and `make deploy`): calls every endpoint and checks its numbers against direct SQL. It also checks pagination, sorting, literal search, the SQL injection attempt, old-ID resolution, 404/405/400 responses, and the 403 on `includes/`.
