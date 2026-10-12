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
