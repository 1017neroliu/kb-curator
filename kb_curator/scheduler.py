"""APScheduler-based task scheduler for periodic jobs."""

from __future__ import annotations

import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from kb_curator.core.config import get_settings
from kb_curator.core.logging import configure_logging, get_logger

log = get_logger(__name__)


def create_scheduler() -> AsyncIOScheduler:
    """Create and configure the APScheduler instance."""
    scheduler = AsyncIOScheduler()
    settings = get_settings()

    # Job: Poll all document sources (Phase 4.2)
    scheduler.add_job(
        "kb_curator.services.polling.poll_all_sources",
        trigger="interval",
        minutes=settings.poll_interval_minutes,
        id="poll_all_sources",
        replace_existing=True,
    )

    # Job: Auto-resolve expired reviews (every 30 minutes)
    scheduler.add_job(
        "kb_curator.services.review.auto_resolve_expired_reviews",
        trigger="interval",
        minutes=settings.auto_resolve_check_interval_minutes,
        id="auto_resolve_expired_reviews",
        replace_existing=True,
    )

    # Placeholder jobs for future phases:
    # Job: Incremental quality inspection (daily at 2 AM)
    # scheduler.add_job(
    #     run_quality_inspection_for_all_kbs,
    #     trigger="cron", hour=2, minute=0,
    #     kwargs={"mode": "incremental"},
    #     id="quality_inspection_incremental",
    # )

    # Job: Full quality inspection (Sunday at 3 AM)
    # scheduler.add_job(
    #     run_quality_inspection_for_all_kbs,
    #     trigger="cron", day_of_week="sun", hour=3, minute=0,
    #     kwargs={"mode": "full"},
    #     id="quality_inspection_full",
    # )

    return scheduler


def run_scheduler() -> None:
    """Run the scheduler (entry point for poetry script)."""
    configure_logging()
    scheduler = create_scheduler()
    scheduler.start()
    log.info("scheduler_started")

    # Keep the event loop running
    try:
        asyncio.get_event_loop().run_forever()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        log.info("scheduler_stopped")
