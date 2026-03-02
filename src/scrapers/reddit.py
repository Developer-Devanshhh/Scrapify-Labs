"""
Scrapify Labs — Reddit Scraper
Uses PRAW (Python Reddit API Wrapper) to scrape public posts and comments.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from functools import partial

import praw

from src.models import Platform, ScrapedPost
from src.scrapers.base import BaseScraper


class RedditScraper(BaseScraper):
    platform = Platform.REDDIT

    def is_configured(self) -> bool:
        return self.settings.reddit_configured

    async def scrape(
        self,
        keywords: list[str],
        max_results: int = 50,
    ) -> list[ScrapedPost]:
        """Scrape Reddit for posts matching keywords across relevant subreddits."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, partial(self._scrape_sync, keywords, max_results)
        )

    def _scrape_sync(self, keywords: list[str], max_results: int) -> list[ScrapedPost]:
        """Synchronous Reddit scraping via PRAW."""
        reddit = praw.Reddit(
            client_id=self.settings.reddit_client_id,
            client_secret=self.settings.reddit_client_secret,
            user_agent=self.settings.reddit_user_agent,
        )

        posts: list[ScrapedPost] = []
        query = " OR ".join(keywords)
        per_keyword_limit = max(max_results // max(len(keywords), 1), 10)

        try:
            # Search across all of Reddit
            for submission in reddit.subreddit("all").search(
                query, sort="new", time_filter="week", limit=per_keyword_limit
            ):
                post = ScrapedPost(
                    platform=Platform.REDDIT,
                    source_url=f"https://reddit.com{submission.permalink}",
                    author=str(submission.author) if submission.author else None,
                    content=f"{submission.title}\n\n{submission.selftext}".strip(),
                    media_urls=self._extract_media(submission),
                    timestamp=datetime.fromtimestamp(
                        submission.created_utc, tz=timezone.utc
                    ),
                    metadata={
                        "subreddit": str(submission.subreddit),
                        "score": submission.score,
                        "num_comments": submission.num_comments,
                        "upvote_ratio": submission.upvote_ratio,
                        "flair": submission.link_flair_text,
                        "is_self": submission.is_self,
                    },
                    keywords=[k for k in keywords if k.lower() in
                              (submission.title + submission.selftext).lower()],
                )
                posts.append(post)

                if len(posts) >= max_results:
                    break

        except Exception as e:
            self.logger.error("Reddit search failed: %s", e)

        return posts

    @staticmethod
    def _extract_media(submission) -> list[str]:
        """Extract media URLs from a Reddit submission."""
        media_urls = []

        # Direct image/video links
        if hasattr(submission, "url") and submission.url:
            url = submission.url
            if any(ext in url for ext in [".jpg", ".png", ".gif", ".mp4", ".webm"]):
                media_urls.append(url)

        # Reddit-hosted images
        if hasattr(submission, "preview") and submission.preview:
            try:
                images = submission.preview.get("images", [])
                for img in images:
                    source = img.get("source", {})
                    if source.get("url"):
                        media_urls.append(source["url"].replace("&amp;", "&"))
            except (AttributeError, KeyError):
                pass

        return media_urls
