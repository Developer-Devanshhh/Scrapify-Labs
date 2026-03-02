"""
Scrapify Labs — Base Scraper Interface
All platform scrapers inherit from BaseScraper and implement the scrape() method.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from src.config import Settings
from src.models import Platform, ScrapedPost


class BaseScraper(ABC):
    """
    Abstract base class for all platform scrapers.

    Each scraper must:
    1. Set `platform` to the appropriate Platform enum value
    2. Implement `scrape(keywords, max_results)` returning a list of ScrapedPost
    3. Implement `is_configured()` returning whether required credentials are set
    """

    platform: Platform = Platform.OTHER

    def __init__(self, settings: Settings):
        self.settings = settings
        self.logger = logging.getLogger(f"scraper.{self.platform.value}")

    @abstractmethod
    async def scrape(
        self,
        keywords: list[str],
        max_results: int = 50,
    ) -> list[ScrapedPost]:
        """
        Scrape public posts matching the given keywords.

        Args:
            keywords: Search terms to look for.
            max_results: Maximum number of posts to return.

        Returns:
            List of ScrapedPost objects.
        """
        ...

    @abstractmethod
    def is_configured(self) -> bool:
        """Check if necessary API keys / credentials are available."""
        ...

    async def safe_scrape(
        self,
        keywords: list[str],
        max_results: int = 50,
    ) -> list[ScrapedPost]:
        """
        Wrapper around scrape() that catches and logs exceptions.
        Use this in production flows to prevent one failing scraper from
        killing the entire job.
        """
        if not self.is_configured():
            self.logger.warning(
                "%s scraper is not configured — skipping", self.platform.value
            )
            return []

        try:
            self.logger.info(
                "Starting %s scrape: keywords=%s max=%d",
                self.platform.value,
                keywords,
                max_results,
            )
            results = await self.scrape(keywords, max_results)
            self.logger.info(
                "%s scrape completed: %d results", self.platform.value, len(results)
            )
            return results
        except Exception as e:
            self.logger.error(
                "%s scrape failed: %s", self.platform.value, str(e), exc_info=True
            )
            return []
