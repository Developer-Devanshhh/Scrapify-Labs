"""
Scrapify Labs — YouTube Scraper
Uses yt-dlp for metadata extraction and YouTube Data API v3 for search + comments.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from datetime import datetime, timezone
from functools import partial

import httpx

from src.models import Platform, ScrapedPost
from src.scrapers.base import BaseScraper

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_COMMENTS_URL = "https://www.googleapis.com/youtube/v3/commentThreads"


class YouTubeScraper(BaseScraper):
    platform = Platform.YOUTUBE

    def is_configured(self) -> bool:
        return self.settings.youtube_configured

    async def scrape(
        self,
        keywords: list[str],
        max_results: int = 50,
    ) -> list[ScrapedPost]:
        """Search YouTube videos by keywords and extract metadata + comments."""
        posts: list[ScrapedPost] = []
        per_keyword = max(max_results // max(len(keywords), 1), 5)

        async with httpx.AsyncClient(timeout=30.0) as client:
            for keyword in keywords:
                try:
                    videos = await self._search_videos(client, keyword, per_keyword)
                    for video in videos:
                        post = await self._video_to_post(client, video, keyword)
                        if post:
                            posts.append(post)
                except Exception as e:
                    self.logger.error("YouTube search for '%s' failed: %s", keyword, e)

                if len(posts) >= max_results:
                    break

        return posts[:max_results]

    async def _search_videos(
        self, client: httpx.AsyncClient, keyword: str, max_results: int
    ) -> list[dict]:
        """Search for videos using YouTube Data API v3."""
        params = {
            "part": "snippet",
            "q": keyword,
            "type": "video",
            "order": "date",
            "maxResults": min(max_results, 50),
            "key": self.settings.youtube_api_key,
        }

        resp = await client.get(YOUTUBE_SEARCH_URL, params=params)
        resp.raise_for_status()
        data = resp.json()
        return data.get("items", [])

    async def _video_to_post(
        self, client: httpx.AsyncClient, video: dict, keyword: str
    ) -> ScrapedPost | None:
        """Convert a YouTube API video result to a ScrapedPost."""
        try:
            snippet = video.get("snippet", {})
            video_id = video.get("id", {}).get("videoId", "")

            if not video_id:
                return None

            # Get top comments (best-effort)
            top_comments = await self._get_comments(client, video_id, max_comments=5)

            published_at = snippet.get("publishedAt", "")
            timestamp = None
            if published_at:
                try:
                    timestamp = datetime.fromisoformat(
                        published_at.replace("Z", "+00:00")
                    )
                except (ValueError, TypeError):
                    pass

            return ScrapedPost(
                platform=Platform.YOUTUBE,
                source_url=f"https://www.youtube.com/watch?v={video_id}",
                author=snippet.get("channelTitle"),
                content=f"{snippet.get('title', '')}\n\n{snippet.get('description', '')}".strip(),
                media_urls=[
                    snippet.get("thumbnails", {}).get("high", {}).get("url", "")
                ],
                timestamp=timestamp,
                metadata={
                    "video_id": video_id,
                    "channel_id": snippet.get("channelId", ""),
                    "channel_title": snippet.get("channelTitle", ""),
                    "top_comments": top_comments,
                    "live_broadcast": snippet.get("liveBroadcastContent", ""),
                },
                keywords=[keyword],
            )
        except Exception as e:
            self.logger.error("Failed to convert video: %s", e)
            return None

    async def _get_comments(
        self, client: httpx.AsyncClient, video_id: str, max_comments: int = 5
    ) -> list[dict]:
        """Fetch top-level comments on a video."""
        try:
            params = {
                "part": "snippet",
                "videoId": video_id,
                "order": "relevance",
                "maxResults": max_comments,
                "key": self.settings.youtube_api_key,
            }
            resp = await client.get(YOUTUBE_COMMENTS_URL, params=params)
            if resp.status_code != 200:
                return []

            data = resp.json()
            comments = []
            for item in data.get("items", []):
                top = item.get("snippet", {}).get("topLevelComment", {})
                snip = top.get("snippet", {})
                comments.append({
                    "author": snip.get("authorDisplayName", ""),
                    "text": snip.get("textDisplay", ""),
                    "likes": snip.get("likeCount", 0),
                    "published_at": snip.get("publishedAt", ""),
                })
            return comments
        except Exception:
            return []


class YtDlpScraper(BaseScraper):
    """
    Alternative YouTube scraper using yt-dlp for extracting video metadata.
    Doesn't require an API key but is slower and rate-limited.
    Use this as a fallback when API quota is exhausted.
    """

    platform = Platform.YOUTUBE

    def is_configured(self) -> bool:
        # yt-dlp just needs to be installed
        try:
            subprocess.run(
                ["yt-dlp", "--version"],
                capture_output=True,
                timeout=5,
            )
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    async def scrape(
        self,
        keywords: list[str],
        max_results: int = 50,
    ) -> list[ScrapedPost]:
        """Search YouTube using yt-dlp and extract metadata."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, partial(self._scrape_sync, keywords, max_results)
        )

    def _scrape_sync(self, keywords: list[str], max_results: int) -> list[ScrapedPost]:
        posts: list[ScrapedPost] = []
        per_keyword = max(max_results // max(len(keywords), 1), 3)

        for keyword in keywords:
            try:
                search_url = f"ytsearch{per_keyword}:{keyword}"
                result = subprocess.run(
                    [
                        "yt-dlp",
                        "--dump-json",
                        "--no-download",
                        "--flat-playlist",
                        search_url,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )

                for line in result.stdout.strip().split("\n"):
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        post = ScrapedPost(
                            platform=Platform.YOUTUBE,
                            source_url=data.get("url", data.get("webpage_url", "")),
                            author=data.get("channel", data.get("uploader", "")),
                            content=data.get("title", ""),
                            media_urls=[data["thumbnail"]] if data.get("thumbnail") else [],
                            metadata={
                                "video_id": data.get("id", ""),
                                "duration": data.get("duration"),
                                "view_count": data.get("view_count"),
                            },
                            keywords=[keyword],
                        )
                        posts.append(post)
                    except json.JSONDecodeError:
                        continue

            except subprocess.TimeoutExpired:
                self.logger.warning("yt-dlp search timed out for '%s'", keyword)
            except Exception as e:
                self.logger.error("yt-dlp search failed for '%s': %s", keyword, e)

        return posts[:max_results]
