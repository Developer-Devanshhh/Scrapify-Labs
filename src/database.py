"""
Scrapify Labs — Database Layer
Async SQLAlchemy + SQLite for storing scraped posts and job records.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Sequence

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    String,
    Text,
    create_engine,
    desc,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from src.config import get_settings
from src.models import JobStatus, Platform, ScrapedPost, ScrapeJob

logger = logging.getLogger(__name__)


# ── ORM Base ─────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


class PostRow(Base):
    """SQLAlchemy model for scraped posts."""

    __tablename__ = "posts"

    id = Column(String(16), primary_key=True)
    platform = Column(String(20), nullable=False, index=True)
    source_url = Column(Text, default="")
    author = Column(String(255), nullable=True)
    content = Column(Text, default="")
    media_urls = Column(Text, default="[]")  # JSON array
    location = Column(String(255), nullable=True)
    timestamp = Column(DateTime, nullable=True)
    scraped_at = Column(DateTime, default=datetime.utcnow)
    metadata_json = Column(Text, default="{}")  # JSON dict
    keywords = Column(Text, default="[]")  # JSON array


class JobRow(Base):
    """SQLAlchemy model for scrape jobs."""

    __tablename__ = "jobs"

    job_id = Column(String(36), primary_key=True)
    status = Column(String(20), default="pending", index=True)
    platforms = Column(Text, default="[]")
    keywords = Column(Text, default="[]")
    total_results = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    error = Column(Text, nullable=True)


# ── Engine & Session ─────────────────────────────────────────────────────

_engine = None
_session_factory = None


async def init_db() -> None:
    """Initialize the database engine and create tables."""
    global _engine, _session_factory

    settings = get_settings()
    _engine = create_async_engine(settings.database_url, echo=False)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("Database initialized at %s", settings.database_url)


async def get_session() -> AsyncSession:
    """Get an async database session."""
    if _session_factory is None:
        await init_db()
    return _session_factory()


async def close_db() -> None:
    """Close the database engine."""
    global _engine
    if _engine:
        await _engine.dispose()
        _engine = None


# ── CRUD Helpers ─────────────────────────────────────────────────────────

async def save_posts(posts: list[ScrapedPost]) -> int:
    """Save a list of ScrapedPost objects. Returns count of new inserts."""
    if not posts:
        return 0

    session = await get_session()
    inserted = 0

    try:
        async with session.begin():
            for post in posts:
                existing = await session.get(PostRow, post.id)
                if existing:
                    continue

                row = PostRow(
                    id=post.id,
                    platform=post.platform.value,
                    source_url=post.source_url,
                    author=post.author,
                    content=post.content,
                    media_urls=json.dumps(post.media_urls),
                    location=post.location,
                    timestamp=post.timestamp,
                    scraped_at=post.scraped_at,
                    metadata_json=json.dumps(post.metadata),
                    keywords=json.dumps(post.keywords),
                )
                session.add(row)
                inserted += 1
    finally:
        await session.close()

    logger.info("Saved %d new posts (of %d total)", inserted, len(posts))
    return inserted


async def get_posts(
    platform: Platform | None = None,
    keyword: str | None = None,
    since: datetime | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[ScrapedPost], int]:
    """Fetch posts with filters. Returns (posts, total_count)."""
    session = await get_session()

    try:
        query = select(PostRow)
        count_query = select(PostRow)

        if platform:
            query = query.where(PostRow.platform == platform.value)
            count_query = count_query.where(PostRow.platform == platform.value)

        if since:
            query = query.where(PostRow.scraped_at >= since)
            count_query = count_query.where(PostRow.scraped_at >= since)

        if keyword:
            query = query.where(PostRow.content.ilike(f"%{keyword}%"))
            count_query = count_query.where(PostRow.content.ilike(f"%{keyword}%"))

        # Count
        result = await session.execute(count_query)
        total = len(result.all())

        # Paginate
        offset = (page - 1) * page_size
        query = query.order_by(desc(PostRow.scraped_at)).offset(offset).limit(page_size)
        result = await session.execute(query)
        rows: Sequence[PostRow] = result.scalars().all()

        posts = [_row_to_post(row) for row in rows]
        return posts, total
    finally:
        await session.close()


async def delete_post(post_id: str) -> bool:
    """Delete a post by ID. Returns True if deleted."""
    session = await get_session()
    try:
        async with session.begin():
            row = await session.get(PostRow, post_id)
            if row:
                await session.delete(row)
                return True
            return False
    finally:
        await session.close()


# ── Job CRUD ─────────────────────────────────────────────────────────────

async def save_job(job: ScrapeJob) -> None:
    """Create or update a scrape job record."""
    session = await get_session()
    try:
        async with session.begin():
            existing = await session.get(JobRow, job.job_id)
            if existing:
                existing.status = job.status.value
                existing.total_results = job.total_results
                existing.completed_at = job.completed_at
                existing.error = job.error
            else:
                row = JobRow(
                    job_id=job.job_id,
                    status=job.status.value,
                    platforms=json.dumps([p.value for p in job.platforms]),
                    keywords=json.dumps(job.keywords),
                    total_results=job.total_results,
                    created_at=job.created_at,
                    completed_at=job.completed_at,
                    error=job.error,
                )
                session.add(row)
    finally:
        await session.close()


async def get_jobs(limit: int = 20) -> list[ScrapeJob]:
    """Get recent jobs ordered by creation time."""
    session = await get_session()
    try:
        query = select(JobRow).order_by(desc(JobRow.created_at)).limit(limit)
        result = await session.execute(query)
        rows = result.scalars().all()
        return [_row_to_job(row) for row in rows]
    finally:
        await session.close()


# ── Converters ───────────────────────────────────────────────────────────

def _row_to_post(row: PostRow) -> ScrapedPost:
    return ScrapedPost(
        platform=Platform(row.platform),
        source_url=row.source_url or "",
        author=row.author,
        content=row.content or "",
        media_urls=json.loads(row.media_urls or "[]"),
        location=row.location,
        timestamp=row.timestamp,
        scraped_at=row.scraped_at,
        metadata=json.loads(row.metadata_json or "{}"),
        keywords=json.loads(row.keywords or "[]"),
    )


def _row_to_job(row: JobRow) -> ScrapeJob:
    return ScrapeJob(
        job_id=row.job_id,
        status=JobStatus(row.status),
        platforms=[Platform(p) for p in json.loads(row.platforms or "[]")],
        keywords=json.loads(row.keywords or "[]"),
        total_results=row.total_results or 0,
        created_at=row.created_at,
        completed_at=row.completed_at,
        error=row.error,
    )
