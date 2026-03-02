"""
Scrapify Labs — Instagram Scraper
Uses instaloader for scraping public Instagram posts, profiles, and hashtags.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from functools import partial

from src.models import Platform, ScrapedPost
from src.scrapers.base import BaseScraper


class InstagramScraper(BaseScraper):
    platform = Platform.INSTAGRAM

    def is_configured(self) -> bool:
        # instaloader works for public data without login
        try:
            import instaloader  # noqa: F401
            return True
        except ImportError:
            return False

    async def scrape(
        self,
        keywords: list[str],
        max_results: int = 50,
    ) -> list[ScrapedPost]:
        """Scrape Instagram public hashtag posts."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, partial(self._scrape_sync, keywords, max_results)
        )

    def _scrape_sync(self, keywords: list[str], max_results: int) -> list[ScrapedPost]:
        """Synchronous Instagram scraping via instaloader."""
        try:
            import instaloader
        except ImportError:
            self.logger.error("instaloader not installed. Run: pip install instaloader")
            return []

        loader = instaloader.Instaloader(
            download_pictures=False,
            download_videos=False,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
            quiet=True,
        )

        # Optional login for higher rate limits
        if self.settings.instagram_username and self.settings.instagram_password:
            try:
                loader.login(
                    self.settings.instagram_username,
                    self.settings.instagram_password,
                )
                self.logger.info("Logged into Instagram as %s", self.settings.instagram_username)
            except Exception as e:
                self.logger.warning("Instagram login failed (continuing without): %s", e)

        posts: list[ScrapedPost] = []
        per_keyword = max(max_results // max(len(keywords), 1), 5)

        for keyword in keywords:
            try:
                # Clean hashtag (remove # if present)
                tag = keyword.strip().lstrip("#").replace(" ", "")
                if not tag:
                    continue

                hashtag = instaloader.Hashtag.from_name(loader.context, tag)
                count = 0

                for ig_post in hashtag.get_posts():
                    if count >= per_keyword:
                        break

                    media_urls = []
                    if ig_post.url:
                        media_urls.append(ig_post.url)

                    # Get location if available
                    location = None
                    if ig_post.location:
                        location = ig_post.location.name if hasattr(ig_post.location, "name") else str(ig_post.location)

                    post = ScrapedPost(
                        platform=Platform.INSTAGRAM,
                        source_url=f"https://www.instagram.com/p/{ig_post.shortcode}/",
                        author=ig_post.owner_username if hasattr(ig_post, "owner_username") else None,
                        content=ig_post.caption or "",
                        media_urls=media_urls,
                        location=location,
                        timestamp=ig_post.date_utc.replace(tzinfo=timezone.utc)
                        if ig_post.date_utc
                        else None,
                        metadata={
                            "shortcode": ig_post.shortcode,
                            "likes": ig_post.likes,
                            "comments": ig_post.comments,
                            "is_video": ig_post.is_video,
                            "hashtags": list(ig_post.caption_hashtags) if ig_post.caption_hashtags else [],
                            "mentions": list(ig_post.caption_mentions) if ig_post.caption_mentions else [],
                        },
                        keywords=[keyword],
                    )
                    posts.append(post)
                    count += 1

                    if len(posts) >= max_results:
                        break

            except Exception as e:
                self.logger.error("Instagram scrape for '#%s' failed: %s", keyword, e)

        return posts[:max_results]
