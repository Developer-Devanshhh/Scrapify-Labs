"""
Scrapify Labs — Indian Civic/Government Scraper via Crawl4AI
Scrapes Indian government portals, municipal corporation sites,
and public data portals for civic data.

Uses Crawl4AI (open-source) for AI-powered web crawling.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime

from src.config import Settings
from src.models import Platform, ScrapedPost
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# Indian government data sources — all publicly accessible
INDIA_CIVIC_SOURCES = [
    {
        "name": "Open Government Data India",
        "url": "https://data.gov.in/search?title={keyword}",
        "type": "open_data",
    },
    {
        "name": "MyGov India",
        "url": "https://www.mygov.in/search/node/{keyword}",
        "type": "citizen_engagement",
    },
    {
        "name": "CPGRAMS Grievances",
        "url": "https://pgportal.gov.in/",
        "type": "grievances",
    },
    {
        "name": "Smart Cities India",
        "url": "https://smartcities.gov.in/",
        "type": "smart_cities",
    },
    {
        "name": "Swachh Bharat Mission",
        "url": "https://sbm.gov.in/sbmdashboard/",
        "type": "sanitation",
    },
    {
        "name": "India Environmental Portal",
        "url": "https://www.indiaenvironmentportal.org.in/search/node/{keyword}",
        "type": "environment",
    },
]


class IndiaCivicScraper(BaseScraper):
    """
    Crawl4AI-powered scraper for Indian government and civic portals.
    Handles messy, inconsistent HTML layouts typical of Indian government sites.
    """

    platform = Platform.CIVIC

    def __init__(self, settings: Settings, sources: list[dict] | None = None):
        super().__init__(settings)
        self.sources = sources or INDIA_CIVIC_SOURCES

    def is_configured(self) -> bool:
        return True  # Crawl4AI is always available (open-source)

    async def scrape(
        self,
        keywords: list[str],
        max_results: int = 50,
    ) -> list[ScrapedPost]:

        try:
            from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
        except ImportError:
            self.logger.error("crawl4ai not installed — pip install crawl4ai")
            return []

        posts: list[ScrapedPost] = []
        browser_config = BrowserConfig(headless=True, verbose=False)

        async with AsyncWebCrawler(config=browser_config) as crawler:
            for source in self.sources:
                if len(posts) >= max_results:
                    break

                for keyword in keywords:
                    if len(posts) >= max_results:
                        break

                    url = source["url"].format(keyword=keyword)
                    self.logger.info(
                        "Crawl4AI India Civic: %s → %s", source["name"], url
                    )

                    try:
                        run_config = CrawlerRunConfig(
                            wait_until="domcontentloaded",
                            page_timeout=30000,
                        )
                        result = await crawler.arun(
                            url=url,
                            config=run_config,
                        )

                        if not result.success:
                            self.logger.warning(
                                "Crawl failed for %s: %s",
                                source["name"],
                                result.error_message,
                            )
                            continue

                        content = result.markdown or ""
                        if not content or len(content) < 50:
                            continue

                        # Extract relevant sections
                        extracted = _extract_relevant_content(
                            content, keywords, source
                        )
                        posts.extend(extracted[: max_results - len(posts)])

                    except Exception as e:
                        self.logger.error(
                            "Crawl4AI error for %s: %s", source["name"], e
                        )

        return posts[:max_results]


def _extract_relevant_content(
    markdown: str,
    keywords: list[str],
    source: dict,
) -> list[ScrapedPost]:
    """Parse crawled markdown into ScrapedPost objects, filtering by keywords."""
    posts: list[ScrapedPost] = []

    # Split into sections
    sections = re.split(r"\n---\n|\n#{1,3}\s|\n\n\n+", markdown)

    for section in sections:
        text = section.strip()
        if len(text) < 30:
            continue

        # Check keyword relevance
        matched = [k for k in keywords if k.lower() in text.lower()]
        if not matched:
            continue

        # Try to extract links
        links = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", text)
        source_url = links[0][1] if links else source.get("url", "")

        # Try to extract dates
        timestamp = _extract_date(text)

        post = ScrapedPost(
            platform=Platform.CIVIC,
            source_url=source_url,
            author=source.get("name", "Indian Government"),
            content=text[:2000],
            timestamp=timestamp,
            metadata={
                "source_name": source.get("name", ""),
                "source_type": source.get("type", "civic"),
                "scraper": "crawl4ai",
            },
            keywords=matched,
        )
        posts.append(post)

    return posts


def _extract_date(text: str) -> datetime | None:
    """Try to find a date in the text."""
    patterns = [
        r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"(\d{4}-\d{2}-\d{2})",
        r"(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                from dateutil.parser import parse as dateparse

                return dateparse(match.group(1))
            except Exception:
                pass
    return None
