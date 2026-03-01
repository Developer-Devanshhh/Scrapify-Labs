"""
Scrapify Labs — Instagram Scraper via Apify (free tier)
Uses the Apify Instagram Hashtag Scraper actor.
"""

from __future__ import annotations

import logging
from datetime import datetime

from src.config import Settings
from src.models import Platform, ScrapedPost
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class ApifyInstagramScraper(BaseScraper):
    """Scrape Instagram hashtags via Apify's free-tier actor."""

    platform = Platform.INSTAGRAM

    # Apify actor ID for Instagram Hashtag Scraper
    ACTOR_ID = "reGe1ST3OBgYZSsZJ"

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

            tag = keyword.lstrip("#")

            try:
                run_input = {
                    "hashtags": [tag],
                    "resultsLimit": min(max_results - len(posts), 20),
                }

                self.logger.info("Apify Instagram: searching '#%s'", tag)
                run = client.actor(self.ACTOR_ID).call(run_input=run_input)

                for item in client.dataset(run["defaultDatasetId"]).iterate_items():
                    try:
                        post = ScrapedPost(
                            platform=Platform.INSTAGRAM,
                            source_url=item.get("url", f"https://www.instagram.com/p/{item.get('shortCode', '')}/"),
                            author=item.get("ownerUsername", "unknown"),
                            content=item.get("caption", ""),
                            media_urls=[item.get("displayUrl", "")] if item.get("displayUrl") else [],
                            timestamp=_parse_timestamp(item.get("timestamp")),
                            metadata={
                                "likes": item.get("likesCount", 0),
                                "comments": item.get("commentsCount", 0),
                                "shortcode": item.get("shortCode", ""),
                                "hashtag": tag,
                            },
                            keywords=[keyword],
                        )
                        posts.append(post)
                    except Exception as e:
                        self.logger.debug("Skipping post: %s", e)

                    if len(posts) >= max_results:
                        break

            except Exception as e:
                self.logger.error("Apify Instagram failed for '#%s': %s", tag, e)

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
