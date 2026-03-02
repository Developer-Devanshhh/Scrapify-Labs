"""
Scrapify Labs — Instagram Scraper (Playwright Stealth)
Uses a real Chromium browser with stealth to bypass bot detection.
Scrapes Instagram hashtag/explore pages for public posts matching keywords.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone

from src.models import Platform, ScrapedPost
from src.scrapers.base import BaseScraper


class InstagramPlaywrightScraper(BaseScraper):
    platform = Platform.INSTAGRAM

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
        """Scrape Instagram hashtag pages using Playwright stealth browser."""
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

            # Apply stealth to the context
            stealth = Stealth()
            await stealth.apply_stealth_async(context)

            # Inject session cookie if available
            session_id = self.settings.instagram_session_id if hasattr(self.settings, 'instagram_session_id') else ""
            if session_id:
                await context.add_cookies([
                    {"name": "sessionid", "value": session_id, "domain": ".instagram.com", "path": "/"},
                ])
            elif self.settings.instagram_username and self.settings.instagram_password:
                # Try to login via browser
                login_page = await context.new_page()
                try:
                    await login_page.goto("https://www.instagram.com/accounts/login/", wait_until="domcontentloaded", timeout=30000)
                    await login_page.wait_for_selector('input[name="username"]', timeout=10000)
                    await login_page.fill('input[name="username"]', self.settings.instagram_username)
                    await login_page.fill('input[name="password"]', self.settings.instagram_password)
                    await login_page.click('button[type="submit"]')
                    await asyncio.sleep(5)
                    self.logger.info("Logged into Instagram via Playwright as %s", self.settings.instagram_username)
                except Exception as e:
                    self.logger.warning("Instagram Playwright login failed: %s", e)
                await login_page.close()

            page = await context.new_page()

            for keyword in keywords:
                try:
                    tag = keyword.strip().lstrip("#").replace(" ", "")
                    if not tag:
                        continue

                    hashtag_url = f"https://www.instagram.com/explore/tags/{tag}/"
                    self.logger.info("Navigating to Instagram hashtag: #%s", tag)
                    await page.goto(hashtag_url, wait_until="domcontentloaded", timeout=30000)

                    # Wait for posts to appear
                    try:
                        await page.wait_for_selector("a[href*='/p/']", timeout=15000)
                    except Exception:
                        self.logger.warning("No posts found or page blocked for '#%s'", tag)
                        continue

                    # Scroll a bit to load more posts
                    for _ in range(2):
                        await page.evaluate("window.scrollBy(0, 800)")
                        await asyncio.sleep(1)

                    # Extract post links
                    post_links = await page.query_selector_all("a[href*='/p/']")
                    count = 0

                    for link_el in post_links:
                        if count >= per_keyword:
                            break

                        try:
                            href = await link_el.get_attribute("href")
                            if not href or "/p/" not in href:
                                continue

                            shortcode = href.split("/p/")[1].rstrip("/")
                            post_url = f"https://www.instagram.com/p/{shortcode}/"

                            # Navigate to the individual post to get details
                            post_page = await context.new_page()
                            await post_page.goto(post_url, wait_until="domcontentloaded", timeout=20000)
                            await asyncio.sleep(2)

                            # Extract caption
                            content = ""
                            try:
                                meta_desc = await post_page.query_selector('meta[property="og:title"]')
                                if meta_desc:
                                    content = await meta_desc.get_attribute("content") or ""
                            except Exception:
                                pass

                            if not content:
                                try:
                                    caption_el = await post_page.query_selector("h1")
                                    if caption_el:
                                        content = await caption_el.inner_text()
                                except Exception:
                                    pass

                            # Extract author
                            author = ""
                            try:
                                author_el = await post_page.query_selector('meta[property="og:title"]')
                                if author_el:
                                    title = await author_el.get_attribute("content") or ""
                                    if "on Instagram" in title:
                                        author = title.split("on Instagram")[0].strip()
                                    elif "@" in title:
                                        author = title.split("@")[0].strip()
                            except Exception:
                                pass

                            # Extract image
                            media_urls = []
                            try:
                                og_image = await post_page.query_selector('meta[property="og:image"]')
                                if og_image:
                                    img_url = await og_image.get_attribute("content")
                                    if img_url:
                                        media_urls.append(img_url)
                            except Exception:
                                pass

                            # Extract timestamp
                            timestamp = None
                            try:
                                time_el = await post_page.query_selector("time")
                                if time_el:
                                    dt_str = await time_el.get_attribute("datetime")
                                    if dt_str:
                                        timestamp = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                            except Exception:
                                pass

                            await post_page.close()

                            if content or media_urls:
                                post = ScrapedPost(
                                    platform=Platform.INSTAGRAM,
                                    source_url=post_url,
                                    author=author or "unknown",
                                    content=content or f"Instagram post #{tag}",
                                    media_urls=media_urls,
                                    timestamp=timestamp,
                                    metadata={"shortcode": shortcode, "hashtag": tag},
                                    keywords=[keyword],
                                )
                                posts.append(post)
                                count += 1

                        except Exception as e:
                            self.logger.debug("Failed to extract Instagram post: %s", e)
                            continue

                    self.logger.info("Extracted %d Instagram posts for '#%s'", count, tag)

                except Exception as e:
                    self.logger.error("Instagram Playwright scrape failed for '#%s': %s", tag, e)

                if len(posts) >= max_results:
                    break

            await browser.close()

        return posts[:max_results]
