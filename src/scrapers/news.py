import asyncio
import httpx
from typing import AsyncGenerator
from datetime import datetime, timezone
import urllib.parse

from src.scrapers.base import BaseScraper
from src.models import ScrapedPost, Platform

class NewsScraper(BaseScraper):
    """
    Unified News Scraper that aggregates data from GNews, Currents API, and NewsData.io.
    Returns standardized ScrapedPost objects seamlessly.
    """

    platform: Platform = Platform.NEWS

    def is_configured(self) -> bool:
        return bool(self.settings.gnews_api_key or self.settings.currents_api_key or self.settings.newsdata_api_key)

    async def scrape(self, keywords: list[str], max_results: int = 10) -> list[ScrapedPost]:
        query = " ".join(keywords)
        async with httpx.AsyncClient(timeout=15.0) as client:
            tasks = []
            
            # GNews Task
            if self.settings.gnews_api_key:
                tasks.append(self._fetch_gnews(client, query, max_results))
            
            # Currents API Task
            if self.settings.currents_api_key:
                tasks.append(self._fetch_currents(client, query, max_results))
                
            # NewsData Task
            if self.settings.newsdata_api_key:
                tasks.append(self._fetch_newsdata(client, query, max_results))
                
            if not tasks:
                self.logger.warning("No News APIs configured. Skipping news scrape.")
                return []

            # Execute all news API queries concurrently
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            seen_urls = set()
            final_posts = []

            for api_result in results:
                if isinstance(api_result, Exception):
                    self.logger.error(f"Error from news API: {str(api_result)}")
                    continue
                    
                for post in api_result:
                    if len(final_posts) >= max_results:
                        break
                    
                    if post.source_url not in seen_urls:
                        final_posts.append(post)
                        seen_urls.add(post.source_url)
                        
                if len(final_posts) >= max_results:
                        break
                        
            return final_posts

    async def _fetch_gnews(self, client: httpx.AsyncClient, keyword: str, limit: int) -> list[ScrapedPost]:
        encoded_q = urllib.parse.quote(keyword)
        url = f"https://gnews.io/api/v4/search?q={encoded_q}&token={self.settings.gnews_api_key}&max={limit}&lang=en"
        
        posts = []
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            
            for article in data.get("articles", []):
                content = f"{article.get('title', '')}\n\n{article.get('description', '')}"
                author = article.get("source", {}).get("name", "GNews Source")
                
                dt_str = article.get("publishedAt")
                try:
                    dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00")) if dt_str else datetime.now(timezone.utc)
                except Exception:
                    dt = datetime.now(timezone.utc)
                    
                posts.append(ScrapedPost(
                    platform=self.platform,
                    author=author,
                    content=content.strip(),
                    source_url=article.get("url", ""),
                    timestamp=dt
                ))
        except Exception as e:
             self.logger.error(f"GNews API failed: {e}")
        return posts

    async def _fetch_currents(self, client: httpx.AsyncClient, keyword: str, limit: int) -> list[ScrapedPost]:
        encoded_q = urllib.parse.quote(keyword)
        url = f"https://api.currentsapi.services/v1/search?keywords={encoded_q}&language=en&apiKey={self.settings.currents_api_key}&limit={limit}"
        
        posts = []
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            
            for article in data.get("news", []):
                content = f"{article.get('title', '')}\n\n{article.get('description', '')}"
                author = article.get("author") or "Currents Source"
                
                dt_str = article.get("published")
                try:
                    # format: 2026-03-12 10:11:00 +0000
                     dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S %z") if dt_str else datetime.now(timezone.utc)
                except Exception:
                     dt = datetime.now(timezone.utc)
                     
                posts.append(ScrapedPost(
                    platform=self.platform,
                    author=author,
                    content=content.strip(),
                    source_url=article.get("url", ""),
                    timestamp=dt
                ))
        except Exception as e:
            self.logger.error(f"Currents API failed: {e}")
        return posts

    async def _fetch_newsdata(self, client: httpx.AsyncClient, keyword: str, limit: int) -> list[ScrapedPost]:
        encoded_q = urllib.parse.quote(keyword)
        url = f"https://newsdata.io/api/1/news?apikey={self.settings.newsdata_api_key}&q={encoded_q}&language=en"
        
        posts = []
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            
            # API returns a max array; we take up to 'limit'
            for idx, article in enumerate(data.get("results", [])):
                if idx >= limit:
                     break
                
                # Combine title and description as content
                content = f"{article.get('title', '')}\n\n{article.get('description', '')}"
                
                creators = article.get("creator")
                author = creators[0] if creators and isinstance(creators, list) else article.get("source_id", "NewsData Source")
                
                dt_str = article.get("pubDate")
                try:
                     # format: 2026-03-12 10:00:00
                     dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc) if dt_str else datetime.now(timezone.utc)
                except Exception:
                     dt = datetime.now(timezone.utc)
                     
                posts.append(ScrapedPost(
                    platform=self.platform,
                    author=author,
                    content=content.strip(),
                    source_url=article.get("link", ""),
                    timestamp=dt
                ))
        except Exception as e:
            self.logger.error(f"NewsData API failed: {e}")
        return posts
