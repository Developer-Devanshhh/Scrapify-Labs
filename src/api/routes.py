"""
Scrapify Labs — API Routes
REST endpoints for triggering scrapes, fetching results, and managing jobs.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from src.database import delete_post, get_jobs, get_posts
from src.models import (
    HealthResponse,
    JobStatus,
    Platform,
    ResultsResponse,
    ScrapeJob,
    ScrapeRequest,
)
from src.scraper_manager import get_configured_platforms, run_scrape_job

logger = logging.getLogger(__name__)
router = APIRouter()

# Track app start time for uptime
_start_time = time.time()


# ── Health ───────────────────────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """Health check endpoint for monitoring."""
    return HealthResponse(
        status="ok",
        uptime_seconds=round(time.time() - _start_time, 2),
        configured_platforms=get_configured_platforms(),
    )


# ── Scrape Jobs ──────────────────────────────────────────────────────────

@router.post("/api/scrape", response_model=ScrapeJob, tags=["Scraping"])
async def trigger_scrape(request: ScrapeRequest, background_tasks: BackgroundTasks):
    """
    Trigger a new scrape job.

    The scrape runs in the background. Use `/api/jobs` to monitor progress
    and `/api/results` to fetch results.
    """
    logger.info(
        "Scrape requested: keywords=%s platforms=%s",
        request.keywords,
        [p.value for p in request.platforms],
    )

    # For small jobs, run synchronously; for large ones, background
    if len(request.platforms) <= 1 and request.max_results <= 20:
        job = await run_scrape_job(request)
        return job
    else:
        # Run in background and return job immediately
        job = ScrapeJob(
            job_id="pending",
            status=JobStatus.PENDING,
            platforms=request.platforms,
            keywords=request.keywords,
        )
        background_tasks.add_task(run_scrape_job, request)
        return job


@router.get("/api/jobs", response_model=list[ScrapeJob], tags=["Scraping"])
async def list_jobs(
    limit: int = Query(default=20, ge=1, le=100, description="Max jobs to return"),
):
    """List recent scrape jobs."""
    return await get_jobs(limit=limit)


# ── Results ──────────────────────────────────────────────────────────────

@router.get("/api/results", response_model=ResultsResponse, tags=["Results"])
async def list_results(
    platform: Platform | None = Query(default=None, description="Filter by platform"),
    keyword: str | None = Query(default=None, description="Search in content"),
    since: datetime | None = Query(default=None, description="Filter posts after this date"),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=50, ge=1, le=200, description="Results per page"),
):
    """
    Fetch scraped results with optional filters.

    Supports filtering by platform, keyword search in content, and date range.
    Results are paginated and ordered by scrape time (newest first).
    """
    posts, total = await get_posts(
        platform=platform,
        keyword=keyword,
        since=since,
        page=page,
        page_size=page_size,
    )
    return ResultsResponse(
        total=total,
        page=page,
        page_size=page_size,
        results=posts,
    )


@router.get(
    "/api/results/{platform}",
    response_model=ResultsResponse,
    tags=["Results"],
)
async def list_results_by_platform(
    platform: Platform,
    keyword: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
):
    """Fetch results filtered by a specific platform."""
    posts, total = await get_posts(
        platform=platform,
        keyword=keyword,
        since=since,
        page=page,
        page_size=page_size,
    )
    return ResultsResponse(
        total=total,
        page=page,
        page_size=page_size,
        results=posts,
    )


@router.delete("/api/results/{post_id}", tags=["Results"])
async def remove_result(post_id: str):
    """Delete a specific scraped result by ID."""
    deleted = await delete_post(post_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Post not found")
    return {"deleted": True, "id": post_id}


# ── Platforms ────────────────────────────────────────────────────────────

@router.get("/api/platforms", tags=["System"])
async def list_platforms():
    """List all supported platforms and their configuration status."""
    configured = get_configured_platforms()
    all_platforms = [p.value for p in Platform if p != Platform.OTHER]

    return {
        "platforms": [
            {
                "name": p,
                "configured": p in configured,
                "status": "ready" if p in configured else "needs_config",
            }
            for p in all_platforms
        ]
    }
