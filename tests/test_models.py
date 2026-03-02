"""
Tests for Scrapify Labs data models.
"""

from datetime import datetime, timezone

from src.models import (
    HealthResponse,
    JobStatus,
    Platform,
    ResultsResponse,
    ScrapedPost,
    ScrapeJob,
    ScrapeRequest,
)


class TestScrapedPost:
    def test_deterministic_id(self):
        """Same platform + URL + content should produce the same ID."""
        post1 = ScrapedPost(
            platform=Platform.REDDIT,
            source_url="https://reddit.com/r/test/1",
            content="Test content about potholes",
        )
        post2 = ScrapedPost(
            platform=Platform.REDDIT,
            source_url="https://reddit.com/r/test/1",
            content="Test content about potholes",
        )
        assert post1.id == post2.id

    def test_different_content_different_id(self):
        """Different content should produce different IDs."""
        post1 = ScrapedPost(
            platform=Platform.REDDIT,
            source_url="https://reddit.com/r/test/1",
            content="Content A",
        )
        post2 = ScrapedPost(
            platform=Platform.REDDIT,
            source_url="https://reddit.com/r/test/1",
            content="Content B",
        )
        assert post1.id != post2.id

    def test_default_fields(self):
        """Defaults should be sensible."""
        post = ScrapedPost(platform=Platform.TWITTER, content="Hello")
        assert post.source_url == ""
        assert post.media_urls == []
        assert post.keywords == []
        assert post.metadata == {}
        assert isinstance(post.scraped_at, datetime)

    def test_full_post(self):
        """Full post with all fields."""
        post = ScrapedPost(
            platform=Platform.YOUTUBE,
            source_url="https://youtube.com/watch?v=abc",
            author="TestChannel",
            content="Video about road issues",
            media_urls=["https://img.youtube.com/thumb.jpg"],
            location="New Delhi",
            timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
            metadata={"video_id": "abc", "views": 1000},
            keywords=["road", "pothole"],
        )
        assert post.platform == Platform.YOUTUBE
        assert post.author == "TestChannel"
        assert len(post.media_urls) == 1
        assert post.metadata["views"] == 1000


class TestScrapeRequest:
    def test_valid_request(self):
        req = ScrapeRequest(
            keywords=["pothole", "water"],
            platforms=[Platform.REDDIT, Platform.YOUTUBE],
            max_results=100,
        )
        assert len(req.keywords) == 2
        assert req.max_results == 100

    def test_default_platform(self):
        req = ScrapeRequest(keywords=["test"])
        assert Platform.REDDIT in req.platforms

    def test_webhook_optional(self):
        req = ScrapeRequest(keywords=["test"])
        assert req.webhook_url is None


class TestScrapeJob:
    def test_default_status(self):
        job = ScrapeJob(job_id="test-123")
        assert job.status == JobStatus.PENDING
        assert job.total_results == 0
        assert job.error is None


class TestHealthResponse:
    def test_defaults(self):
        health = HealthResponse()
        assert health.status == "ok"
        assert health.service == "ScrapifyLabs"
