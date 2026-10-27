# Daily schedule (macOS launchd)

`com.asteroidwatch.pipeline.plist` runs the pipeline every day at **09:00 local time**
(yesterday .. +7 days, `--run-type daily`). If the Mac is asleep at 09:00, launchd runs the job
once when it wakes.

**XAMPP MySQL must be running** when the job runs. If it isn't, the run fails before it can be
written to `pipeline_runs`; the error appears in `logs/pipeline.log`, and the dashboard's
"last run" stays old.

## Install

```bash
make schedule-install
```

This does:

```bash
mkdir -p logs ~/Library/LaunchAgents
sed "s|__PROJECT_DIR__|$PWD|g" scheduler/com.asteroidwatch.pipeline.plist \
    > ~/Library/LaunchAgents/com.asteroidwatch.pipeline.plist
plutil -lint ~/Library/LaunchAgents/com.asteroidwatch.pipeline.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.asteroidwatch.pipeline.plist
```

## Check it

```bash
make schedule-status       # is it loaded? last exit code?
make schedule-run-now      # run it once right now, as launchd would
tail -f logs/pipeline.log
```

## Uninstall

```bash
make schedule-uninstall
```

This does:

```bash
launchctl bootout gui/$(id -u)/com.asteroidwatch.pipeline
rm ~/Library/LaunchAgents/com.asteroidwatch.pipeline.plist
```

After changing the plist template, uninstall and install again.

---

# API server (macOS launchd)

`com.asteroidwatch.api.plist` keeps the dashboard and API running at **http://localhost:8010**
(`asteroid-watch serve`: uvicorn, 1 worker, listening on 127.0.0.1 only). It starts when you log
in, and launchd restarts it if it stops (at most once every 10 seconds). If MySQL is off, the
server keeps running and the dashboard shows "Database offline" until MySQL is back.

```bash
make api-install      # install and start
make api-status       # running? pid? last exit code?
make api-restart      # restart, e.g. after changing the code
make api-uninstall    # stop and remove
```

Logs: `logs/api.out.log` and `logs/api.err.log`. Port 8010 must be free: if another program
already uses it, the server can't start (see `logs/api.err.log`).

---

# Daily pipeline with Prefect (v2, replaces the 09:00 job above)

Two launchd agents keep Prefect running (see `docs/orchestration.md`):

| Agent | Runs | Logs |
|---|---|---|
| `com.asteroidwatch.prefect-server` | `prefect server start`: schedules, run history, UI at http://127.0.0.1:4200 | `logs/prefect-server.*.log` |
| `com.asteroidwatch.prefect-worker` | `python -m flows.serve`: registers the 19:00 IST deployment and runs the flows | `logs/prefect-worker.*.log`, `logs/pipeline.log` |

```bash
make prefect-install      # install and start both
make prefect-status       # both should say: state = running
make prefect-uninstall    # stop and remove both
```

launchd only keeps these processes alive. The schedule (cron `0 19 * * *`, Asia/Kolkata) lives
in Prefect. If the Mac is asleep or off at 19:00, the run starts as soon as it's awake again.

## Retiring the old 09:00 job

Keep `com.asteroidwatch.pipeline` until the Prefect flow has succeeded **on its own schedule
twice** (two 19:00 runs with status success in `asteroid-watch status` or the Prefect UI). Then:

```bash
make schedule-uninstall
```

Until then both run each day. That's harmless: loads are idempotent, and the runs are 10 hours
apart, more than the flow's 6-hour "already ran" window.
