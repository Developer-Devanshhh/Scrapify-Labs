"""
Scrapify Labs — Scheduler
Periodic scraping jobs using APScheduler.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.config import get_settings
from src.models import Platform, ScrapeRequest
from src.scraper_manager import run_scrape_job

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def scheduled_scrape():
    """
    Default scheduled scrape job.
    Runs against all configured platforms with default governance-related keywords.
    Customize these keywords based on your municipality / region.
    """
    default_keywords = [
        "pothole",
        "water supply",
        "electricity",
        "garbage",
        "road repair",
        "civic complaint",
        "municipal",
    ]

    settings = get_settings()
    platforms = []

    if settings.reddit_configured:
        platforms.append(Platform.REDDIT)
    if settings.youtube_configured:
        platforms.append(Platform.YOUTUBE)
    if settings.twitter_configured:
        platforms.append(Platform.TWITTER)
    # Instagram + civic always available
    platforms.append(Platform.INSTAGRAM)

    if not platforms:
        logger.warning("No platforms configured — skipping scheduled scrape")
        return

    request = ScrapeRequest(
        keywords=default_keywords,
        platforms=platforms,
        max_results=30,
    )

    logger.info("Running scheduled scrape: platforms=%s", [p.value for p in platforms])
    await run_scrape_job(request)


def start_scheduler() -> AsyncIOScheduler:
    """Start the periodic scraping scheduler."""
    global _scheduler

    settings = get_settings()
    interval = settings.scrape_interval_minutes

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        scheduled_scrape,
        "interval",
        minutes=interval,
        id="periodic_scrape",
        name=f"Scrape every {interval} minutes",
        replace_existing=True,
    )
    _scheduler.start()

    logger.info("Scheduler started — scraping every %d minutes", interval)
    return _scheduler


def stop_scheduler() -> None:
    """Gracefully stop the scheduler."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
        _scheduler = None
