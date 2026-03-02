"""
Scrapify Labs — Threads Scraper via Apify
Uses Apify's Threads Scraper actor for reliable Threads.net scraping.
Falls back to Crawl4AI if Apify token is not set.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime

from src.config import Settings
from src.models import Platform, ScrapedPost
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class ThreadsScraper(BaseScraper):
    """Scrape Threads posts via Apify or Crawl4AI fallback."""

    platform = Platform.THREADS

    # Community Threads Scraper Actor
    ACTOR_ID = "red.cars~threads-scraper"

    def is_configured(self) -> bool:
        return True  # Crawl4AI fallback always available

    async def scrape(
        self,
        keywords: list[str],
        max_results: int = 50,
    ) -> list[ScrapedPost]:

        if self.settings.apify_api_token:
            return await self._scrape_apify(keywords, max_results)
        return await self._scrape_crawl4ai(keywords, max_results)

    async def _scrape_apify(
        self, keywords: list[str], max_results: int
    ) -> list[ScrapedPost]:
        """Scrape using Apify Threads Scraper actor."""
        from apify_client import ApifyClient

        client = ApifyClient(self.settings.apify_api_token)
        posts: list[ScrapedPost] = []

        for keyword in keywords:
            if len(posts) >= max_results:
                break

            try:
                run_input = {
                    "searchTerms": [keyword],
                    "maxPosts": min(max_results - len(posts), 15),
                }

                self.logger.info("Apify Threads: searching '%s'", keyword)
                run = client.actor(self.ACTOR_ID).call(run_input=run_input)

                for item in client.dataset(run["defaultDatasetId"]).iterate_items():
                    try:
                        post = ScrapedPost(
                            platform=Platform.THREADS,
                            source_url=item.get("url", item.get("postUrl", "")),
                            author=item.get("username", item.get("userName", "unknown")),
                            content=item.get("text", item.get("caption", "")),
                            media_urls=[
                                url for url in [item.get("imageUrl", "")]
                                if url
                            ],
                            timestamp=_parse_timestamp(
                                item.get("timestamp", item.get("createdAt"))
                            ),
                            metadata={
                                "likes": item.get("likesCount", item.get("likes", 0)),
                                "replies": item.get("repliesCount", item.get("replies", 0)),
                                "source": "apify",
                            },
                            keywords=[keyword],
                        )
                        posts.append(post)
                    except Exception as e:
                        self.logger.debug("Skipping Threads post: %s", e)

                    if len(posts) >= max_results:
                        break

            except Exception as e:
                self.logger.error("Apify Threads failed for '%s': %s", keyword, e)

        return posts[:max_results]

    async def _scrape_crawl4ai(
        self, keywords: list[str], max_results: int
    ) -> list[ScrapedPost]:
        """Fallback: Crawl4AI browser scraping for Threads."""
        try:
            from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
        except ImportError:
            self.logger.error("crawl4ai not installed")
            return []

        posts: list[ScrapedPost] = []
        browser_config = BrowserConfig(headless=True, verbose=False)

        for keyword in keywords:
            if len(posts) >= max_results:
                break

            tag = keyword.lstrip("#")
            search_url = f"https://www.threads.net/search?q={tag}&serp_type=default"

            try:
                self.logger.info("Crawl4AI Threads: searching '%s'", keyword)
                async with AsyncWebCrawler(config=browser_config) as crawler:
                    run_config = CrawlerRunConfig(
                        wait_until="networkidle",
                        page_timeout=30000,
                    )
                    result = await crawler.arun(url=search_url, config=run_config)

                    if not result.success:
                        continue

                    content = result.markdown or ""
                    chunks = re.split(r'\n---\n|\n#{1,3}\s|\n\n\n+', content)

                    for chunk in chunks:
                        if len(posts) >= max_results:
                            break
                        text = chunk.strip()
                        if len(text) < 20:
                            continue
                        if not any(k.lower() in text.lower() for k in keywords):
                            continue

                        post = ScrapedPost(
                            platform=Platform.THREADS,
                            source_url=search_url,
                            content=text[:2000],
                            timestamp=datetime.utcnow(),
                            metadata={"source": "crawl4ai", "keyword": keyword},
                            keywords=[keyword],
                        )
                        posts.append(post)

            except Exception as e:
                self.logger.error("Crawl4AI Threads failed: %s", e)

        return posts[:max_results]


def _parse_timestamp(ts: str | int | None) -> datetime | None:
    if not ts:
        return None
    try:
        if isinstance(ts, int):
            return datetime.utcfromtimestamp(ts)
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
