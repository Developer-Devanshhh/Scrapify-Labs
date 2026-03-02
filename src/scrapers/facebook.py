"""
Scrapify Labs — Facebook Scraper via Apify
Uses Apify's Facebook Posts Scraper actor for reliable public Facebook scraping.
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


class FacebookScraper(BaseScraper):
    """Scrape public Facebook posts via Apify or Crawl4AI fallback."""

    platform = Platform.FACEBOOK

    # Official Apify Facebook Posts Scraper
    ACTOR_ID = "apify/facebook-posts-scraper"

    def is_configured(self) -> bool:
        return True  # Crawl4AI fallback always available

    async def scrape(
        self,
        keywords: list[str],
        max_results: int = 50,
    ) -> list[ScrapedPost]:

        # Use Apify if token is available
        if self.settings.apify_api_token:
            return await self._scrape_apify(keywords, max_results)

        # Fallback to Crawl4AI
        return await self._scrape_crawl4ai(keywords, max_results)

    async def _scrape_apify(
        self, keywords: list[str], max_results: int
    ) -> list[ScrapedPost]:
        """Scrape using Apify Facebook Posts Scraper actor."""
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

                self.logger.info("Apify Facebook: searching '%s'", keyword)
                run = client.actor(self.ACTOR_ID).call(run_input=run_input)

                for item in client.dataset(run["defaultDatasetId"]).iterate_items():
                    try:
                        post = ScrapedPost(
                            platform=Platform.FACEBOOK,
                            source_url=item.get("postUrl", item.get("url", "")),
                            author=item.get("pageName", item.get("userName", "unknown")),
                            content=item.get("text", item.get("postText", "")),
                            media_urls=[
                                url for url in [
                                    item.get("imageUrl", ""),
                                    item.get("videoUrl", ""),
                                ] if url
                            ],
                            timestamp=_parse_timestamp(item.get("time", item.get("date"))),
                            metadata={
                                "likes": item.get("likes", item.get("likesCount", 0)),
                                "comments": item.get("comments", item.get("commentsCount", 0)),
                                "shares": item.get("shares", item.get("sharesCount", 0)),
                                "source": "apify",
                            },
                            keywords=[keyword],
                        )
                        posts.append(post)
                    except Exception as e:
                        self.logger.debug("Skipping FB post: %s", e)

                    if len(posts) >= max_results:
                        break

            except Exception as e:
                self.logger.error("Apify Facebook failed for '%s': %s", keyword, e)

        return posts[:max_results]

    async def _scrape_crawl4ai(
        self, keywords: list[str], max_results: int
    ) -> list[ScrapedPost]:
        """Fallback: Crawl4AI browser scraping for Facebook public pages."""
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

            search_url = f"https://www.facebook.com/search/posts/?q={keyword}"

            try:
                self.logger.info("Crawl4AI Facebook: searching '%s'", keyword)
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
                        if len(text) < 30:
                            continue
                        if not any(k.lower() in text.lower() for k in keywords):
                            continue

                        post = ScrapedPost(
                            platform=Platform.FACEBOOK,
                            source_url=search_url,
                            content=text[:2000],
                            timestamp=datetime.utcnow(),
                            metadata={"source": "crawl4ai", "keyword": keyword},
                            keywords=[keyword],
                        )
                        posts.append(post)

            except Exception as e:
                self.logger.error("Crawl4AI Facebook failed: %s", e)

        return posts[:max_results]


def _parse_timestamp(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
