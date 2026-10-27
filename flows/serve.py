"""The Prefect worker: registers the daily deployment (19:00 IST) and runs its flow runs.

    python -m flows.serve        (kept running by launchd: scheduler/com.asteroidwatch.prefect-worker.plist)

It needs the local Prefect server (`prefect server start`, http://127.0.0.1:4200), which
stores the schedule and the run history and creates a flow run each day at 19:00.
This process asks the server for runs that are due (including late ones after the Mac
was asleep or off) and executes them.
"""

from prefect import serve
from prefect.schedules import Cron

from flows.daily import neows_daily

DEPLOYMENT = "daily-19-ist"
SCHEDULE = "0 19 * * *"  # cron: minute 0, hour 19, every day
TIMEZONE = "Asia/Kolkata"


def daily_deployment():
    return neows_daily.to_deployment(
        name=DEPLOYMENT, schedule=Cron(SCHEDULE, timezone=TIMEZONE), tags=["neows", "daily"],
        description="NeoWs: yesterday .. +7 days, quality checks, up to 100 orbit lookups. 19:00 IST.",
    )


def main() -> None:
    serve(daily_deployment())


if __name__ == "__main__":
    main()
