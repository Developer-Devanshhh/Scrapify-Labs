"""
Scrapify Labs — Twitter/X Scraper
Uses twscrape for scraping public tweets without official API access.
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.models import Platform, ScrapedPost
from src.scrapers.base import BaseScraper


class TwitterScraper(BaseScraper):
    platform = Platform.TWITTER

    def is_configured(self) -> bool:
        return self.settings.twitter_configured

    async def scrape(
        self,
        keywords: list[str],
        max_results: int = 50,
    ) -> list[ScrapedPost]:
        """Scrape recent tweets matching keywords using twscrape."""
        try:
            from twscrape import API as TwAPI
            from twscrape import gather
        except ImportError:
            self.logger.error("twscrape not installed. Run: pip install twscrape")
            return []

        api = TwAPI()

        # Add accounts from config (username:password:email:email_password)
        accounts_str = self.settings.twitter_accounts.strip()
        if accounts_str:
            for line in accounts_str.split("\n"):
                parts = line.strip().split(":")
                if len(parts) >= 4:
                    await api.pool.add_account(
                        parts[0], parts[1], parts[2], parts[3]
                    )
            await api.pool.login_all()

        posts: list[ScrapedPost] = []
        per_keyword = max(max_results // max(len(keywords), 1), 10)

        for keyword in keywords:
            try:
                tweets = await gather(api.search(keyword, limit=per_keyword))

                for tweet in tweets:
                    media_urls = []
                    if hasattr(tweet, "media") and tweet.media:
                        media_urls = [
                            m.get("media_url_https", "")
                            for m in (tweet.media if isinstance(tweet.media, list) else [])
                            if isinstance(m, dict) and m.get("media_url_https")
                        ]

                    post = ScrapedPost(
                        platform=Platform.TWITTER,
                        source_url=f"https://x.com/{tweet.user.username}/status/{tweet.id}"
                        if hasattr(tweet, "user") and tweet.user
                        else "",
                        author=tweet.user.username
                        if hasattr(tweet, "user") and tweet.user
                        else None,
                        content=tweet.rawContent
                        if hasattr(tweet, "rawContent")
                        else str(tweet),
                        media_urls=media_urls,
                        location=tweet.place.full_name
                        if hasattr(tweet, "place") and tweet.place
                        else None,
                        timestamp=tweet.date
                        if hasattr(tweet, "date")
                        else datetime.now(timezone.utc),
                        metadata={
                            "tweet_id": str(tweet.id),
                            "likes": getattr(tweet, "likeCount", 0),
                            "retweets": getattr(tweet, "retweetCount", 0),
                            "replies": getattr(tweet, "replyCount", 0),
                            "views": getattr(tweet, "viewCount", 0),
                            "lang": getattr(tweet, "lang", ""),
                            "hashtags": [
                                h.get("text", "")
                                for h in (getattr(tweet, "hashtags", []) or [])
                                if isinstance(h, dict)
                            ],
                        },
                        keywords=[keyword],
                    )
                    posts.append(post)

                    if len(posts) >= max_results:
                        break

            except Exception as e:
                self.logger.error("Twitter search for '%s' failed: %s", keyword, e)

        return posts[:max_results]
