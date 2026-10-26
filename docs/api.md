# Dashboard JSON API (FastAPI)

Base URL: `http://localhost:8000/api/`. The same server shows the dashboard at `http://localhost:8000/` and interactive docs at **`http://localhost:8000/docs`**, where you can try every endpoint. Start it with `asteroid-watch serve` (or `make serve`), or keep it running with launchd (`make api-install`, see `scheduler/README.md`).

Everything is read from MySQL with a **read-only** user (`asteroid_reader`: SELECT and SHOW VIEW on `asteroid_watch` only). The server listens on `127.0.0.1` only, so other machines can't reach it.

v2 replaced the PHP API (now in `legacy/php/`) with this one. Before the switch, parity tests proved **every response is byte-for-byte identical** to the PHP version (see [How we know it's identical](#how-we-know-its-identical)).

## Endpoints

- Only `GET` is accepted (other methods get 405).
- Success: `{"data": ...}` with HTTP 200. Errors: `{"error": "message"}` with 400 (bad input), 404 (not found), 503 (MySQL off, or the read-only user isn't configured) or 500 (anything else; details go only to the server log).
- Add `pretty=1` to any JSON request for indented output.

| Endpoint | Parameters | Returns |
|---|---|---|
| `summary` | none | `totals` (asteroids, approaches, hazardous counts, orbits, date range), `this_week` (today + 6 days), `closest_this_week`, `closest_upcoming`, `closest_on_record`, `largest`, `last_run` (latest ETL run with its quality failure count) |
| `approaches` | `start`, `end` (YYYY-MM-DD); `hazardous` = all/true/false; `q` (name search, ≤ 50 chars, `%`/`_` matched literally); `sort` = date/distance/velocity/size/name; `order` = asc/desc; `page` (1–10000); `per_page` (1–100, default 25) | `items`, `page`, `per_page`, `total`, `total_pages`, `filters` |
| `asteroid` | `id` (numeric neo_id, required) | `asteroid`, `orbit` (or null if not fetched yet), `approaches`, `old_ids`, `resolved_from` (set when an old provisional ID was requested; see `duplicate_ids.md`) |
| `trends` | `start`, `end` (optional) | `daily` (counts per day), `size_histogram` (8 bins by max diameter, counts asteroids), `counts` (approaches, asteroids, asteroids without a size estimate), `velocity_vs_distance` (one point per approach), `hazardous_split` |
| `runs` | `limit` (1–50, default 10) | `runs`, newest first, each with `records_extracted`, `records_after_dedupe` (null for runs before it existed) and its `quality` check results (ETL and cross-check runs) |

### Downloads (CSV and Excel)

| Endpoint | Parameters | File |
|---|---|---|
| `approaches.csv`, `approaches.xlsx` | Same filters and sort as `approaches` (no paging: every matching row, up to 100,000) | `asteroid-watch-approaches-<date>.csv/.xlsx` |
| `runs.csv`, `runs.xlsx` | none | Every pipeline run, including its `source` |

The dashboard's **CSV / Excel** buttons above the table always download the table's current search, hazard filter, time window and sort order. The pipeline section has **Runs CSV / Runs Excel** buttons.

- **CSV:** UTF-8 with a byte-order mark, so Excel shows names such as "–" correctly. True/false appear as yes/no.
- **Excel:** written with `openpyxl`. The header row is bold and frozen, and numbers stay numbers, so they sort and sum.
- **Formula protection:** a text cell that starts with `=`, `+`, `-` or `@` would run as a formula when opened in Excel ("CSV injection"). Such cells get a leading `'`, so they're shown as text.

## How it works

| File | Role |
|---|---|
| `api/main.py` | Creates the app, maps errors to the PHP API's JSON errors and status codes, serves the dashboard (`/`), its `assets/`, and `/docs` |
| `api/routes/*.py` | One module per endpoint, like the PHP files: `summary.py`, `approaches.py`, `asteroid.py`, `trends.py`, `runs.py`, plus `exports.py` |
| `api/params.py` | Input validation, ported one-for-one from the PHP helpers (`param_date`, `param_int`, `param_enum`, `param_text`), with the same error messages |
| `api/db.py` | The read-only connection pool, and the conversion of database values to what PHP sent |
| `api/schemas.py` | Pydantic response models: the exact JSON shape of every endpoint |
| `api/responses.py` | JSON output identical to PHP's `json_encode` (compact, or indented with `pretty=1`) and the same headers |

1. **A request arrives**, for example `GET /api/approaches?hazardous=true&sort=distance`. FastAPI calls the endpoint function with the query parameters as plain strings.
2. **Validation comes first**, before any database access, in the same order as in PHP, so the first error reported is the same. Dates must be real `YYYY-MM-DD` dates, numbers must be whole and within limits, and enums must come from fixed lists. A failure becomes HTTP 400 with PHP's message.
3. **SQL with bound parameters.** The queries are the PHP API's SQL, run with SQLAlchemy `text()` and `:name` placeholders. Values are always sent separately from the SQL text. Sort columns come from a fixed dictionary (`SORT_COLUMNS`), never from the request. Search text has `%`, `_` and `\` escaped, so they match literally.
4. **Values as PHP sent them.** PHP's PDO returned DECIMAL as a string (`"21.650"`), DATE as `"2026-10-12"` and DATETIME as `"2026-10-12 06:30:00"`. MySQL BOOLEAN columns become `true`/`false`. `api/db.py` (`php_value`, `with_bools`) converts PyMySQL's values the same way.
5. **The response is checked** against its Pydantic model in **strict** mode: a wrong type (for example a float where PHP sent a string) is a server error, not silently different JSON. The models also produce the `/docs` page.
6. **Errors:** MySQL off → 503 "Cannot connect to MySQL. Is XAMPP MySQL running?" (the dashboard shows its offline banner). Anything unexpected → 500 with a generic message; the details go only to the server log.

**Static files:** only `dashboard/assets/` and the vendored Swagger UI (`api/static/swagger-ui/`, so `/docs` works offline) are served. Nothing else in the project, such as `.env`, is reachable; tests try path-traversal URLs. Assets are sent with `Cache-Control: no-cache`, so the browser re-checks them on every load (an unchanged file costs a 304) and never runs a stale version. This replaces PHP's `?v=<file time>` URLs.

## How we know it's identical

`tests/parity/test_parity.py` (`make parity-test`, with the PHP API deployed by `make legacy-deploy`) sends the same request to both APIs and requires the same status, the same `Content-Type`, `Cache-Control` and `X-Content-Type-Options` headers, and an **identical response body, byte for byte**. On 2026-10-27, all **104 tests passed**. They covered:

- every endpoint, with and without `pretty=1`
- every sort key and order, both hazard filters, date ranges, empty results and the last page
- 11 searches, including `%`, `_`, `\`, `' OR 1=1 --` and a non-ASCII dash
- **all 1,684 asteroid IDs and old aliases**, and every page of the approaches table
- 21 kinds of bad input, including two errors at once (the first one must win, as in PHP)
- POST, PUT and DELETE on every endpoint

The comparison is type-aware, so `1` vs `1.0` or `"21.650"` vs `21.65` is a failure. As a check, the test was run against a deliberately broken conversion (DECIMAL sent as a number), and it failed as expected.

## Tests

- `make test` (offline, 36 API tests in `tests/test_api_app.py`):
  - every validation error, rejected before any database access (the database layer is made to fail if touched)
  - 503 for MySQL down and for a missing read-only user
  - 405, 404 and the security headers
  - `pretty=1` output and value conversion
  - strict models, and user input kept out of the SQL text
  - formula-safe exports
  - the static-file boundaries
  - `/docs` loading only local files, and the Swagger UI file hashes
- `make api-test` (needs MySQL): the v1 checks of answers against direct SQL (totals, filters, pagination, literal search, the injection attempt, old-ID resolution, trends sums, runs with checks) run against FastAPI and, when deployed, against the legacy PHP API. Also checked: exports match SQL counts, and the schema matches the models.
- `make parity-test`: see above.
