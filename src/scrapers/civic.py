"""
Scrapify Labs — Civic/Government Scraper
Scrapes public government meeting agendas, minutes, and civic data.
Uses BeautifulSoup + httpx for general civic site scraping.
Can be extended with city-scrapers spiders for specific municipalities.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

from src.models import Platform, ScrapedPost
from src.scrapers.base import BaseScraper

# Example civic data sources (extend per municipality)
DEFAULT_CIVIC_SOURCES = [
    {
        "name": "Example Municipal Portal",
        "url": "https://example.gov/public-notices",
        "type": "notices",
    },
]


class CivicScraper(BaseScraper):
    """
    General-purpose civic data scraper.

    This is a template — customize `sources` with actual municipal portal URLs
    for your target region. For US city councils, consider using the
    city-scrapers framework (https://github.com/City-Bureau/city-scrapers) instead.
    """

    platform = Platform.CIVIC

    def __init__(self, settings, sources: list[dict] | None = None):
        super().__init__(settings)
        self.sources = sources or DEFAULT_CIVIC_SOURCES

    def is_configured(self) -> bool:
        # Always configured — just needs URLs
        return len(self.sources) > 0

    async def scrape(
        self,
        keywords: list[str],
        max_results: int = 50,
    ) -> list[ScrapedPost]:
        """Scrape civic portals for public notices matching keywords."""
        posts: list[ScrapedPost] = []

        async with httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": "ScrapifyLabs/1.0 (civic-data-research)"
            },
        ) as client:
            for source in self.sources:
                try:
                    source_posts = await self._scrape_source(
                        client, source, keywords, max_results - len(posts)
                    )
                    posts.extend(source_posts)
                except Exception as e:
                    self.logger.error(
                        "Failed to scrape %s: %s", source.get("name", "unknown"), e
                    )

                if len(posts) >= max_results:
                    break

        return posts[:max_results]

    async def _scrape_source(
        self,
        client: httpx.AsyncClient,
        source: dict,
        keywords: list[str],
        limit: int,
    ) -> list[ScrapedPost]:
        """Scrape a single civic source URL."""
        url = source.get("url", "")
        if not url or url.startswith("https://example"):
            self.logger.debug("Skipping placeholder source: %s", source.get("name"))
            return []

        resp = await client.get(url)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "lxml")
        posts: list[ScrapedPost] = []

        # Generic extraction: look for article-like elements
        containers = soup.find_all(
            ["article", "div", "li"],
            class_=lambda c: c and any(
                term in (c if isinstance(c, str) else " ".join(c)).lower()
                for term in ["notice", "agenda", "minutes", "post", "item", "entry"]
            ),
        )

        # Fallback: just get all paragraphs if no structured containers
        if not containers:
            containers = soup.find_all("p")

        for container in containers[:limit]:
            text = container.get_text(strip=True, separator=" ")
            if not text or len(text) < 20:
                continue

            # Filter by keywords
            matched_keywords = [
                k for k in keywords if k.lower() in text.lower()
            ]
            if keywords and not matched_keywords:
                continue

            # Try to find a link
            link = container.find("a", href=True)
            source_url = ""
            if link:
                href = link["href"]
                if href.startswith("http"):
                    source_url = href
                elif href.startswith("/"):
                    from urllib.parse import urlparse
                    parsed = urlparse(url)
                    source_url = f"{parsed.scheme}://{parsed.netloc}{href}"

            # Try to find a date
            date_el = container.find(["time", "span", "div"], class_=lambda c: c and "date" in str(c).lower())
            timestamp = None
            if date_el:
                try:
                    timestamp = datetime.fromisoformat(
                        date_el.get("datetime", date_el.get_text(strip=True))
                    )
                except (ValueError, TypeError):
                    pass

            post = ScrapedPost(
                platform=Platform.CIVIC,
                source_url=source_url or url,
                author=source.get("name"),
                content=text[:2000],  # Cap content length
                timestamp=timestamp,
                metadata={
                    "source_name": source.get("name", ""),
                    "source_type": source.get("type", "general"),
                    "original_url": url,
                },
                keywords=matched_keywords or keywords,
            )
            posts.append(post)

        return posts
