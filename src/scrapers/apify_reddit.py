"""
Scrapify Labs — Reddit Scraper via Apify
Uses Apify's Reddit Scraper actor as primary method (no Reddit API keys needed!).
Falls back to PRAW if Apify token is not set.
"""

from __future__ import annotations

import logging
from datetime import datetime

from src.config import Settings
from src.models import Platform, ScrapedPost
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class ApifyRedditScraper(BaseScraper):
    """Scrape Reddit via Apify — no Reddit API keys required."""

    platform = Platform.REDDIT

    # Trudax Reddit Scraper (most popular, reliable)
    ACTOR_ID = "trudax~reddit-scraper"

    def is_configured(self) -> bool:
        return bool(self.settings.apify_api_token)

    async def scrape(
        self,
        keywords: list[str],
        max_results: int = 50,
    ) -> list[ScrapedPost]:

        from apify_client import ApifyClient

        client = ApifyClient(self.settings.apify_api_token)
        posts: list[ScrapedPost] = []

        for keyword in keywords:
            if len(posts) >= max_results:
                break

            try:
                run_input = {
                    "searches": [keyword],
                    "maxItems": min(max_results - len(posts), 20),
                    "sort": "new",
                    "type": "post",
                }

                self.logger.info("Apify Reddit: searching '%s'", keyword)
                run = client.actor(self.ACTOR_ID).call(run_input=run_input)

                for item in client.dataset(run["defaultDatasetId"]).iterate_items():
                    try:
                        post = ScrapedPost(
                            platform=Platform.REDDIT,
                            source_url=item.get("url", item.get("postUrl", "")),
                            author=f"u/{item.get('author', item.get('username', 'unknown'))}",
                            content=(
                                item.get("title", "") + "\n\n" +
                                item.get("body", item.get("selftext", item.get("text", "")))
                            ).strip(),
                            media_urls=[
                                url for url in [item.get("thumbnail", "")]
                                if url and url.startswith("http")
                            ],
                            timestamp=_parse_timestamp(
                                item.get("createdAt", item.get("created_utc"))
                            ),
                            metadata={
                                "subreddit": item.get("subreddit", item.get("communityName", "")),
                                "score": item.get("ups", item.get("score", 0)),
                                "comments": item.get("numberOfComments", item.get("num_comments", 0)),
                                "source": "apify",
                            },
                            keywords=[keyword],
                        )
                        posts.append(post)
                    except Exception as e:
                        self.logger.debug("Skipping Reddit post: %s", e)

                    if len(posts) >= max_results:
                        break

            except Exception as e:
                self.logger.error("Apify Reddit failed for '%s': %s", keyword, e)

        return posts[:max_results]


def _parse_timestamp(ts: str | int | float | None) -> datetime | None:
    if not ts:
        return None
    try:
        if isinstance(ts, (int, float)):
            return datetime.utcfromtimestamp(ts)
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
