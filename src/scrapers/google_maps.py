"""
Scrapify Labs — Google Maps Reviews Scraper
Uses the official Google Places API to fetch hyper-local citizen complaints
from municipal offices, hospitals, parks, and government buildings.
"""

from __future__ import annotations

import logging
from datetime import datetime

import httpx

from src.models import Platform, ScrapedPost
from src.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# Chennai-specific places to scrape reviews from
CHENNAI_CIVIC_PLACES = [
    "Greater Chennai Corporation",
    "Chennai Metropolitan Water Supply",
    "Chennai Corporation Zone Office",
    "Chennai Traffic Police",
    "Government Hospital Chennai",
    "Chennai Municipal Office",
    "Chennai Smart City",
    "CMDA Chennai",
    "Chennai Collector Office",
    "Public Works Department Chennai",
]


class GoogleMapsScraper(BaseScraper):
    """Scrapes Google Maps reviews for civic locations using Places API."""

    platform = Platform.GOOGLE_MAPS

    def is_configured(self) -> bool:
        return bool(self.settings.google_maps_api_key)

    async def scrape(
        self, keywords: list[str], max_results: int = 10
    ) -> list[ScrapedPost]:
        if not self.is_configured():
            logger.warning("Google Maps API key not configured, skipping.")
            return []

        api_key = self.settings.google_maps_api_key
        demo_city = self.settings.demo_city or "Chennai"
        posts: list[ScrapedPost] = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Build search queries from keywords + civic places
            search_queries = []
            for kw in keywords:
                search_queries.append(f"{kw} {demo_city}")
            # Also search known civic places
            for place_name in CHENNAI_CIVIC_PLACES[:5]:
                search_queries.append(place_name)

            seen_place_ids: set[str] = set()

            for query in search_queries:
                if len(posts) >= max_results:
                    break

                try:
                    # Step 1: Search for places
                    search_resp = await client.get(
                        "https://maps.googleapis.com/maps/api/place/textsearch/json",
                        params={"query": query, "key": api_key},
                    )
                    search_data = search_resp.json()

                    if search_data.get("status") != "OK":
                        logger.debug("Places search for '%s': %s", query, search_data.get("status"))
                        continue

                    # Step 2: Get details + reviews for top results
                    for place in search_data.get("results", [])[:3]:
                        place_id = place.get("place_id")
                        if not place_id or place_id in seen_place_ids:
                            continue
                        seen_place_ids.add(place_id)

                        details_resp = await client.get(
                            "https://maps.googleapis.com/maps/api/place/details/json",
                            params={
                                "place_id": place_id,
                                "fields": "name,reviews,geometry,formatted_address,rating,url",
                                "key": api_key,
                            },
                        )
                        details = details_resp.json().get("result", {})

                        place_name = details.get("name", "Unknown Place")
                        geo = details.get("geometry", {}).get("location", {})
                        lat = geo.get("lat")
                        lng = geo.get("lng")
                        address = details.get("formatted_address", "")
                        place_url = details.get("url", "")

                        reviews = details.get("reviews", [])
                        if not reviews:
                            continue

                        for review in reviews:
                            if len(posts) >= max_results:
                                break

                            review_text = review.get("text", "").strip()
                            if not review_text:
                                continue

                            # Check if review is relevant to any keyword
                            review_lower = review_text.lower()
                            matched_kws = [
                                kw for kw in keywords
                                if kw.lower() in review_lower
                            ]
                            # Include all reviews for civic places even without keyword match
                            is_civic_place = any(
                                cp.lower() in query.lower()
                                for cp in CHENNAI_CIVIC_PLACES
                            )

                            if not matched_kws and not is_civic_place:
                                continue

                            # Parse review timestamp
                            ts = None
                            if review.get("time"):
                                try:
                                    ts = datetime.fromtimestamp(review["time"])
                                except (ValueError, OSError):
                                    pass

                            post = ScrapedPost(
                                platform=Platform.GOOGLE_MAPS,
                                source_url=place_url,
                                author=review.get("author_name", "Anonymous"),
                                content=f"[{place_name}] {review_text}",
                                location=address,
                                latitude=lat,
                                longitude=lng,
                                timestamp=ts,
                                metadata={
                                    "place_name": place_name,
                                    "place_id": place_id,
                                    "rating": review.get("rating"),
                                    "place_rating": details.get("rating"),
                                    "scraper": "google_places_api",
                                },
                                keywords=matched_kws or keywords[:1],
                            )
                            posts.append(post)

                except Exception as e:
                    logger.error("Google Maps error for '%s': %s", query, e)
                    continue

        logger.info("Google Maps scraped %d reviews for '%s'", len(posts), demo_city)
        return posts
