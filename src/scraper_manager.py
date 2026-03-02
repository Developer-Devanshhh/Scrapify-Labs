"""
Scrapify Labs — Scraper Manager
Orchestrates scraper selection, execution, and result collection.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from src.config import Settings, get_settings
from src.database import save_job, save_posts
from src.models import JobStatus, Platform, ScrapedPost, ScrapeJob, ScrapeRequest
from src.api.webhooks import dispatch_webhook
from src.scrapers.base import BaseScraper
from src.scrapers.civic import CivicScraper
from src.scrapers.reddit import RedditScraper
from src.scrapers.youtube import YouTubeScraper

logger = logging.getLogger(__name__)


def get_scraper(platform: Platform, settings: Settings) -> BaseScraper:
    """Factory: return the right scraper instance for a platform.
    Prefers Playwright scrapers for Twitter/Instagram for reliability."""

    if platform == Platform.TWITTER:
        from src.scrapers.twitter_playwright import TwitterPlaywrightScraper
        scraper = TwitterPlaywrightScraper(settings)
        if scraper.is_configured():
            return scraper
        # Fallback to twscrape
        from src.scrapers.twitter import TwitterScraper
        return TwitterScraper(settings)

    if platform == Platform.INSTAGRAM:
        from src.scrapers.instagram_playwright import InstagramPlaywrightScraper
        scraper = InstagramPlaywrightScraper(settings)
        if scraper.is_configured():
            return scraper
        # Fallback to instaloader
        from src.scrapers.instagram import InstagramScraper
        return InstagramScraper(settings)

    scrapers: dict[Platform, type[BaseScraper]] = {
        Platform.REDDIT: RedditScraper,
        Platform.YOUTUBE: YouTubeScraper,
        Platform.CIVIC: CivicScraper,
    }
    cls = scrapers.get(platform)
    if not cls:
        raise ValueError(f"No scraper available for platform: {platform}")
    return cls(settings)


def get_configured_platforms(settings: Settings | None = None) -> list[str]:
    """Return list of platforms with valid configuration."""
    settings = settings or get_settings()
    configured = []

    checks = {
        "reddit": settings.reddit_configured,
        "youtube": settings.youtube_configured,
        "twitter": settings.twitter_configured,
        "instagram": True,  # Works without login for public data
        "civic": True,      # Always available
    }

    for name, is_ready in checks.items():
        if is_ready:
            configured.append(name)

    return configured


async def run_scrape_job(request: ScrapeRequest) -> ScrapeJob:
    """
    Execute a full scrape job across requested platforms.

    1. Create job record
    2. For each platform, run the scraper
    3. Save results to DB
    4. Fire wehook if configured
    5. Update & return job record
    """
    settings = get_settings()
    job_id = str(uuid.uuid4())[:8]

    job = ScrapeJob(
        job_id=job_id,
        status=JobStatus.RUNNING,
        platforms=request.platforms,
        keywords=request.keywords,
    )
    await save_job(job)

    all_posts: list[ScrapedPost] = []

    for platform in request.platforms:
        try:
            scraper = get_scraper(platform, settings)
            posts = await scraper.safe_scrape(
                keywords=request.keywords,
                max_results=request.max_results,
            )
            all_posts.extend(posts)
        except ValueError as e:
            logger.warning("Skipping platform: %s", e)
        except Exception as e:
            logger.error("Scraper error for %s: %s", platform.value, e)

    # Persist results
    new_count = await save_posts(all_posts)

    # Update job
    job.status = JobStatus.COMPLETED
    job.total_results = len(all_posts)
    job.completed_at = datetime.utcnow()
    await save_job(job)

    # Webhook delivery
    webhook_url = request.webhook_url or settings.webhook_url
    if webhook_url:
        await dispatch_webhook(all_posts, job_id, webhook_url)

    logger.info(
        "Job %s completed: %d results (%d new) across %d platforms",
        job_id, len(all_posts), new_count, len(request.platforms),
    )

    return job
