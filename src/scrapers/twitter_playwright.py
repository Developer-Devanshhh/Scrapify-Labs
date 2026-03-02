"""
Scrapify Labs — Twitter Scraper (Playwright Stealth)
Uses a real Chromium browser with stealth to bypass Cloudflare/bot detection.
Scrapes Twitter/X search results for public tweets matching keywords.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone

from src.models import Platform, ScrapedPost
from src.scrapers.base import BaseScraper


class TwitterPlaywrightScraper(BaseScraper):
    platform = Platform.TWITTER

    def is_configured(self) -> bool:
        try:
            from playwright.async_api import async_playwright  # noqa: F401
            return True
        except ImportError:
            return False

    async def scrape(
        self,
        keywords: list[str],
        max_results: int = 50,
    ) -> list[ScrapedPost]:
        """Scrape Twitter using Playwright stealth browser."""
        from playwright.async_api import async_playwright
        from playwright_stealth import Stealth

        posts: list[ScrapedPost] = []
        per_keyword = max(max_results // max(len(keywords), 1), 5)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            )

            # Inject auth cookies if available
            auth_token = self.settings.twitter_auth_token if hasattr(self.settings, 'twitter_auth_token') else ""
            ct0 = self.settings.twitter_ct0 if hasattr(self.settings, 'twitter_ct0') else ""

            if auth_token and ct0:
                await context.add_cookies([
                    {"name": "auth_token", "value": auth_token, "domain": ".x.com", "path": "/"},
                    {"name": "ct0", "value": ct0, "domain": ".x.com", "path": "/"},
                ])

            # Apply stealth to the context
            stealth = Stealth()
            await stealth.apply_stealth_async(context)

            page = await context.new_page()

            for keyword in keywords:
                try:
                    query = keyword.replace(" ", "%20")
                    search_url = f"https://x.com/search?q={query}&src=typed_query&f=live"

                    self.logger.info("Navigating to Twitter search: %s", keyword)
                    await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)

                    # Wait for tweets to appear
                    try:
                        await page.wait_for_selector('[data-testid="tweet"]', timeout=15000)
                    except Exception:
                        self.logger.warning("No tweets found or page blocked for '%s'", keyword)
                        continue

                    # Scroll a bit to load more tweets
                    for _ in range(2):
                        await page.evaluate("window.scrollBy(0, 800)")
                        await asyncio.sleep(1)

                    # Extract tweet elements
                    tweet_elements = await page.query_selector_all('[data-testid="tweet"]')
                    count = 0

                    for tweet_el in tweet_elements:
                        if count >= per_keyword:
                            break

                        try:
                            # Extract text content
                            text_el = await tweet_el.query_selector('[data-testid="tweetText"]')
                            content = await text_el.inner_text() if text_el else ""
                            if not content:
                                continue

                            # Extract author
                            user_el = await tweet_el.query_selector('[data-testid="User-Name"]')
                            author = ""
                            if user_el:
                                spans = await user_el.query_selector_all("span")
                                for span in spans:
                                    txt = await span.inner_text()
                                    if txt.startswith("@"):
                                        author = txt
                                        break

                            # Extract tweet URL
                            time_el = await tweet_el.query_selector("time")
                            tweet_url = ""
                            timestamp = None
                            if time_el:
                                parent_a = await time_el.query_selector("xpath=..")
                                if parent_a:
                                    href = await parent_a.get_attribute("href")
                                    if href:
                                        tweet_url = f"https://x.com{href}"
                                dt_str = await time_el.get_attribute("datetime")
                                if dt_str:
                                    timestamp = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))

                            # Extract engagement metrics
                            metrics = {}
                            for metric_name in ["reply", "retweet", "like"]:
                                metric_el = await tweet_el.query_selector(f'[data-testid="{metric_name}"]')
                                if metric_el:
                                    metric_text = await metric_el.inner_text()
                                    try:
                                        metrics[metric_name + "s"] = int(metric_text.replace(",", "")) if metric_text.strip() else 0
                                    except ValueError:
                                        metrics[metric_name + "s"] = 0

                            # Extract media
                            media_urls = []
                            images = await tweet_el.query_selector_all('img[src*="pbs.twimg.com"]')
                            for img in images:
                                src = await img.get_attribute("src")
                                if src and "profile" not in src:
                                    media_urls.append(src)

                            post = ScrapedPost(
                                platform=Platform.TWITTER,
                                source_url=tweet_url or f"https://x.com/search?q={query}",
                                author=author or "unknown",
                                content=content,
                                media_urls=media_urls,
                                timestamp=timestamp,
                                metadata=metrics,
                                keywords=[keyword],
                            )
                            posts.append(post)
                            count += 1

                        except Exception as e:
                            self.logger.debug("Failed to extract tweet: %s", e)
                            continue

                    self.logger.info("Extracted %d tweets for '%s'", count, keyword)

                except Exception as e:
                    self.logger.error("Twitter Playwright scrape failed for '%s': %s", keyword, e)

                if len(posts) >= max_results:
                    break

            await browser.close()

        return posts[:max_results]
