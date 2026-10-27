# Orchestration with Prefect: how it works

Added in v2 Phase 3. The daily pipeline is a **Prefect 3 flow**, scheduled every day at **19:00 IST**. Prefect runs on this Mac only (a local server with a SQLite database, no Docker), and launchd only keeps its two processes alive.

## 1. Why Prefect, and not Airflow?

| | Prefect 3 (chosen) | Apache Airflow |
|---|---|---|
| What has to run | One server process (API, UI, scheduler) + one worker | Scheduler, webserver, triggerer, metadata database (PostgreSQL or MySQL recommended), often Docker |
| Memory on this Mac | **Measured: about 134 MB (server) + 100 MB (worker)** | Airflow's Docker quick start asks for at least 4 GB for Docker, ideally 8 GB: the whole Mac |
| Writing a pipeline | Plain Python functions with `@flow` and `@task` | DAG files with operators; tasks normally pass data through a store (XCom) |
| Fits this project | The existing step functions became tasks unchanged | Would need restructuring around operators |

Both give schedules, retries, run history and a UI. With 8 GB of RAM and the rule that no part may need more than about 3 GB, Airflow's footprint rules it out. Prefect gives the same ideas (DAG of tasks, retries, schedules, monitoring) at a fraction of the cost.

## 2. The pieces

| Piece | Where | What it does |
|---|---|---|
| **Steps** | `pipeline/steps.py` | The pipeline as plain functions: wait for network, check database, start run, extract, transform, load, quality checks, orbital lookups, finish run. Used by both manual runs and the flow. |
| **Flow** | `flows/daily.py` (`neows_daily`) | Calls the steps as **tasks**, in order, each with its own retry policy |
| **Deployment** | `flows/serve.py` | "Run `neows_daily` on cron `0 19 * * *`, time zone Asia/Kolkata", registered with the server under the name `neows-daily/daily-19-ist` |
| **Server** | `prefect server start`, `http://127.0.0.1:4200` | Stores deployments, schedules, flow and task runs and logs (SQLite in `.prefect/`). Its scheduler creates the next runs ahead of time. Shows the UI. |
| **Worker** | `python -m flows.serve` | Asks the server for runs that are due and executes each one in a new process |
| **launchd** | `scheduler/com.asteroidwatch.prefect-server.plist`, `…prefect-worker.plist` | Starts both at login and restarts them if they stop. It doesn't schedule anything itself. |

Settings are in `pyproject.toml` under `[tool.prefect]`. They cover the database location (`.prefect/`), the server address, analytics off, the pipeline's log lines shown in the UI, and task results not saved to disk.

**Manual runs stay as they were:** `asteroid-watch run` / `make run` call the same steps directly, without Prefect, so a demo never depends on the Prefect server. `make flow-run-now` runs the real flow through Prefect.

## 3. One daily run, step by step

```
19:00  server marks the scheduled run as due  →  worker starts it in a new process
       wait for network ──► check database ──► already ran? ──► start run (pipeline_runs row)
       ──► extract ──► transform ──► load ──► quality checks ──► orbital lookups ──► finish run
```

- Every run is still written to `pipeline_runs` (`run_type = daily`, `source = neows`) and `quality_results`, so the dashboard and API work exactly as before.
- Log lines go to `logs/pipeline.log` **and** to the run's page in the Prefect UI.

## 4. Retries: three levels

| Level | Where | Policy | For |
|---|---|---|---|
| HTTP request | `NeoWsClient` (v1) | 4 retries after 2, 4, 8, 16 s (or `Retry-After`) | A brief NASA hiccup, 429, 5xx |
| Task | `flows/daily.py` | extract: 3 retries after 1, 5 and 15 min; load: 2 (30 s, 2 min); quality: 2; orbits: 1 (5 min); start/finish run: 2–3 (30 s) | NASA down for minutes; a brief database error |
| Flow | `@flow(retries=6, retry_delay_seconds=1800)` | The whole flow again, 30 min later, up to 6 times (19:30 … 22:00) | MySQL not running; a step that kept failing |

On a task retry Prefect calls the same function again. Each step opens its own database connection and every load is an idempotent upsert, so repeating a step is safe.

## 5. The failures from Phase 0, and what happens now

In Phase 0, run 20 failed because the Mac was asleep: a 19-second maintenance wake ("DarkWake") had no Wi-Fi, all retries were used up in seconds, and the Mac went back to sleep mid-run. On 19–21 October, MySQL wasn't running, and those failures were never recorded.

| Situation | Now |
|---|---|
| **No network** (DarkWake, Wi-Fi off) | `wait for network` opens a plain TCP connection to `api.nasa.gov:443` (no API request used). If that fails, it checks again **every 5 minutes for up to 2 hours**, but never past the end of the scheduled day. It uses the wall clock, so time spent asleep counts, and it checks again as soon as the Mac wakes. |
| **MySQL not running** | `check database` writes a JSON line to **`logs/failed_attempts.log`** (it can't go into `pipeline_runs`) and fails. The **whole flow retries 30 minutes later**, up to 6 times, the last at about 22:00 the same day. `asteroid-watch status` shows these entries. |
| **Mac asleep or off at 19:00** | The run stays scheduled and is marked **Late**. The worker starts it as soon as the Mac is awake and running (catch-up on wake, like launchd). |
| **Several days missed** | Each missed day leaves a late run. The first one does the work. The others reach `already ran?`, find a successful daily run less than 6 hours old, and stop without calling NASA. |
| **A retry after midnight** | It stops immediately (`TooLate`). The next day's run covers the same dates (yesterday … +7 days). |

## 6. Security and data

- **Secrets:** the API key and DB passwords stay in `.env`. Task results aren't persisted, and caching is off. The NASA client, which holds the key, is passed to tasks in memory only. After real runs, Prefect's database files in `.prefect/` were scanned for all three secret values: none found.
- **Raw data** is saved as before in `data/raw/`, with the key redacted. Prefect stores only run states, logs and parameters.
- The server listens on `127.0.0.1` only, and analytics (anonymous usage data to Prefect) are turned off.

## 7. Commands

| Command | Does |
|---|---|
| `make prefect-server` / `make prefect-worker` | Run the server / worker in the terminal |
| `make prefect-install` / `prefect-status` / `prefect-uninstall` | Keep both running with launchd (installed by you) |
| `make flow-run-now` | Run the daily flow now, through Prefect, and watch it |
| `asteroid-watch status` | Last run per source, next scheduled Prefect run, failed attempts not in MySQL |

**The old v1 launchd job** (`com.asteroidwatch.pipeline`, 09:00) keeps running until the Prefect flow has succeeded on its own schedule twice. Then it's removed with `make schedule-uninstall`. Until then, both run each day. That's harmless: loads are idempotent, and the two runs are 10 hours apart, more than the 6-hour skip window.

## 8. A compatibility note

Prefect 3.9's scheduler fails with SQLAlchemy 2.1 ("Can't evaluate bulk DML statement"): no scheduled runs were created. SQLAlchemy is pinned to the 2.0 series (2.0.55) in `pyproject.toml`. All tests, `alembic check` and the API parity tests were re-run on it.
