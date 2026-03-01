"""
Scrapify Labs — Twitter/X Scraper via Apify (free tier)
Uses the Apify Tweet Scraper actor for scalable Twitter scraping.
Falls back gracefully when Apify credits are exhausted.
"""

from __future__ import annotations

import logging
from datetime import datetime

from src.config import Settings
from src.models import Platform, ScrapedPost
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class ApifyTwitterScraper(BaseScraper):
    """Scrape Twitter/X via Apify's free-tier Tweet Scraper actor."""

    platform = Platform.TWITTER

    # Apify actor ID for the community Tweet Scraper V2
    ACTOR_ID = "61RPP7dywgiy0JPD0"

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
                    "searchTerms": [keyword],
                    "maxTweets": min(max_results - len(posts), 20),
                    "sort": "Latest",
                }

                self.logger.info("Apify Twitter: searching '%s'", keyword)
                run = client.actor(self.ACTOR_ID).call(run_input=run_input)

                for item in client.dataset(run["defaultDatasetId"]).iterate_items():
                    try:
                        post = ScrapedPost(
                            platform=Platform.TWITTER,
                            source_url=item.get("url", ""),
                            author=f"@{item.get('author', {}).get('userName', 'unknown')}",
                            content=item.get("text", ""),
                            media_urls=[
                                m.get("url", "")
                                for m in item.get("media", [])
                                if m.get("url")
                            ],
                            timestamp=_parse_timestamp(item.get("createdAt")),
                            metadata={
                                "likes": item.get("likeCount", 0),
                                "retweets": item.get("retweetCount", 0),
                                "replies": item.get("replyCount", 0),
                                "views": item.get("viewCount", 0),
                            },
                            keywords=[keyword],
                        )
                        posts.append(post)
                    except Exception as e:
                        self.logger.debug("Skipping tweet: %s", e)

                    if len(posts) >= max_results:
                        break

            except Exception as e:
                self.logger.error("Apify Twitter failed for '%s': %s", keyword, e)

        return posts[:max_results]


def _parse_timestamp(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
