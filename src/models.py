"""
Scrapify Labs — Unified Data Models
Every scraper outputs data conforming to these Pydantic schemas.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, computed_field


# ── Enums ────────────────────────────────────────────────────────────────

class Platform(str, Enum):
    TWITTER = "twitter"
    REDDIT = "reddit"
    YOUTUBE = "youtube"
    INSTAGRAM = "instagram"
    FACEBOOK = "facebook"
    THREADS = "threads"
    CIVIC = "civic"
    OTHER = "other"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ── Core Data Model ─────────────────────────────────────────────────────

class ScrapedPost(BaseModel):
    """Unified schema for all scraped content across platforms."""

    platform: Platform
    source_url: str = ""
    author: str | None = None
    content: str = ""
    media_urls: list[str] = Field(default_factory=list)
    location: str | None = None
    timestamp: datetime | None = None
    scraped_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict = Field(default_factory=dict)
    keywords: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def id(self) -> str:
        """Deterministic ID based on platform + source_url + content hash."""
        raw = f"{self.platform.value}:{self.source_url}:{self.content[:200]}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ── API Request / Response Models ────────────────────────────────────────

class ScrapeRequest(BaseModel):
    """Request to trigger a scrape job."""

    keywords: list[str] = Field(..., min_length=1, description="Search keywords")
    platforms: list[Platform] = Field(
        default_factory=lambda: [Platform.REDDIT],
        description="Platforms to scrape",
    )
    max_results: int = Field(default=50, ge=1, le=500, description="Max results per platform")
    webhook_url: str | None = Field(default=None, description="Optional callback URL")


class ScrapeJob(BaseModel):
    """Represents a running or completed scrape job."""

    job_id: str
    status: JobStatus = JobStatus.PENDING
    platforms: list[Platform] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    total_results: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    error: str | None = None


class ResultsResponse(BaseModel):
    """Paginated response for scraped results."""

    total: int
    page: int
    page_size: int
    results: list[ScrapedPost]


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
    service: str = "ScrapifyLabs"
    version: str = "0.1.0"
    uptime_seconds: float = 0.0
    configured_platforms: list[str] = Field(default_factory=list)
