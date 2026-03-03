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
from src.scrapers.facebook import FacebookScraper
from src.scrapers.threads import ThreadsScraper

logger = logging.getLogger(__name__)


def get_scraper(platform: Platform, settings: Settings) -> BaseScraper:
    """Factory: return the right scraper instance for a platform.

    Priority order:
      1. Apify actors (if token is set — uses free $5/mo credits)
      2. Playwright stealth (free, uses browser cookies)
      3. Original library scrapers (twscrape, instaloader, etc.)
    """

    if platform == Platform.TWITTER:
        # Priority 1: Apify (scalable, maintained)
        if settings.apify_api_token:
            from src.scrapers.apify_twitter import ApifyTwitterScraper
            return ApifyTwitterScraper(settings)
        # Priority 2: Playwright stealth (free, uses cookies)
        from src.scrapers.twitter_playwright import TwitterPlaywrightScraper
        scraper = TwitterPlaywrightScraper(settings)
        if scraper.is_configured():
            return scraper
        # Priority 3: twscrape
        from src.scrapers.twitter import TwitterScraper
        return TwitterScraper(settings)

    if platform == Platform.INSTAGRAM:
        # Priority 1: Apify
        if settings.apify_api_token:
            from src.scrapers.apify_instagram import ApifyInstagramScraper
            return ApifyInstagramScraper(settings)
        # Priority 2: Playwright stealth
        from src.scrapers.instagram_playwright import InstagramPlaywrightScraper
        scraper = InstagramPlaywrightScraper(settings)
        if scraper.is_configured():
            return scraper
        # Priority 3: instaloader
        from src.scrapers.instagram import InstagramScraper
        return InstagramScraper(settings)

    if platform == Platform.FACEBOOK:
        return FacebookScraper(settings)

    if platform == Platform.THREADS:
        return ThreadsScraper(settings)

    if platform == Platform.CIVIC:
        # Use Crawl4AI India civic scraper for richer results
        from src.scrapers.india_civic import IndiaCivicScraper
        return IndiaCivicScraper(settings)

    if platform == Platform.REDDIT:
        # Priority 1: Apify (no API keys needed!)
        if settings.apify_api_token:
            from src.scrapers.apify_reddit import ApifyRedditScraper
            return ApifyRedditScraper(settings)
        # Priority 2: PRAW (needs Reddit API keys)
        return RedditScraper(settings)



    scrapers: dict[Platform, type[BaseScraper]] = {
        Platform.YOUTUBE: YouTubeScraper,
    }
    cls = scrapers.get(platform)
    if not cls:
        raise ValueError(f"No scraper available for platform: {platform}")
    return cls(settings)


def get_configured_platforms(settings: Settings | None = None) -> list[str]:
    """Return list of platforms with valid configuration."""
    settings = settings or get_settings()
    configured = []

    has_apify = bool(settings.apify_api_token)

    checks = {
        "twitter": settings.twitter_configured or has_apify,
        "instagram": True,       # Playwright fallback always available
        "facebook": True,        # Crawl4AI + Apify fallback
        "threads": True,         # Crawl4AI + Apify fallback
        "youtube": settings.youtube_configured,
        "reddit": settings.reddit_configured or has_apify,
        "civic": True,           # Crawl4AI always available
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
