from __future__ import annotations

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from .services.email.poller import sync_all_accounts

logger = logging.getLogger("tracker.scheduler")

scheduler = BackgroundScheduler()
JOB_ID = "email_poll"


def start(interval_seconds: int) -> None:
    # Do NOT sync on startup — wait a full interval (or Sync Now in Settings).
    # Startup sync used to hit a dead Ollama provider and burn/stuck the app.
    from datetime import timedelta

    scheduler.add_job(
        sync_all_accounts,
        trigger="interval",
        seconds=interval_seconds,
        id=JOB_ID,
        replace_existing=True,
        max_instances=1,
        next_run_time=datetime.now(timezone.utc) + timedelta(seconds=interval_seconds),
    )
    scheduler.start()
    logger.info(
        "Scheduler started; next sync in %ss (no sync on startup)", interval_seconds
    )


def reschedule(interval_seconds: int) -> None:
    scheduler.reschedule_job(JOB_ID, trigger="interval", seconds=interval_seconds)
    logger.info("Rescheduled inbox polling to every %ss", interval_seconds)


def shutdown() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
