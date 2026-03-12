"""
Scrapify Labs — Scraper Manager v3
Orchestrates scraper selection, concurrent execution, city-scoping,
LLM structuring, and result collection.
"""

from __future__ import annotations

import asyncio
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
from src.scrapers.google_maps import GoogleMapsScraper
from src.scrapers.news import NewsScraper

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

    if platform == Platform.GOOGLE_MAPS:
        return GoogleMapsScraper(settings)

    if platform == Platform.NEWS:
        return NewsScraper(settings)

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
        "google_maps": settings.google_maps_configured,
    }

    for name, is_ready in checks.items():
        if is_ready:
            configured.append(name)

    return configured


def _scope_keywords(keywords: list[str], settings: Settings) -> list[str]:
    """Prepend demo city name to keywords for city-focused scraping."""
    city = settings.demo_city
    if not city:
        return keywords

    scoped = []
    for kw in keywords:
        # Don't double-add city if user already included it
        if city.lower() not in kw.lower():
            scoped.append(f"{kw} {city}")
        else:
            scoped.append(kw)
    return scoped


async def _scrape_platform(
    platform: Platform,
    keywords: list[str],
    max_results: int,
    settings: Settings,
) -> list[ScrapedPost]:
    """Scrape a single platform. Used as a concurrent task."""
    try:
        scraper = get_scraper(platform, settings)
        posts = await scraper.safe_scrape(
            keywords=keywords,
            max_results=max_results,
        )
        return posts
    except ValueError as e:
        logger.warning("Skipping platform: %s", e)
        return []
    except Exception as e:
        logger.error("Scraper error for %s: %s", platform.value, e)
        return []


async def run_scrape_job(request: ScrapeRequest) -> ScrapeJob:
    """
    Execute a full scrape job across requested platforms.

    v3 Improvements:
    1. City-scoped keyword injection
    2. Concurrent platform scraping (asyncio.gather)
    3. Post-scrape LLM structuring via Gemini
    4. Geo-tagged results
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

    # Step 1: Scope keywords to demo city
    scoped_keywords = _scope_keywords(request.keywords, settings)
    logger.info(
        "Job %s: scraping %d platforms with keywords %s",
        job_id, len(request.platforms), scoped_keywords,
    )

    # Step 2: Run all platform scrapers CONCURRENTLY
    tasks = [
        _scrape_platform(platform, scoped_keywords, request.max_results, settings)
        for platform in request.platforms
    ]
    results = await asyncio.gather(*tasks)
    all_posts: list[ScrapedPost] = []
    for platform_posts in results:
        all_posts.extend(platform_posts)

    # Step 3: LLM structuring (if Gemini is configured)
    if settings.gemini_configured and all_posts:
        try:
            from src.llm.structurer import structure_posts
            all_posts = await structure_posts(all_posts, settings)
        except Exception as e:
            logger.error("LLM structuring failed: %s", e)

    # Step 4: Persist results
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
