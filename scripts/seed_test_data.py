"""
Seed script — populate the database with sample scraped posts for testing.
Usage: python -m scripts.seed_test_data
"""

import asyncio
from datetime import datetime, timedelta, timezone

from src.database import init_db, save_posts
from src.models import Platform, ScrapedPost


SAMPLE_POSTS = [
    ScrapedPost(
        platform=Platform.REDDIT,
        source_url="https://reddit.com/r/india/comments/example1",
        author="concerned_citizen_42",
        content="The pothole on MG Road has been there for 3 months now. Multiple accidents have happened. When will the municipal corporation fix this? #roads #safety",
        location="Bangalore, Karnataka",
        timestamp=datetime.now(timezone.utc) - timedelta(hours=6),
        metadata={"subreddit": "india", "score": 234, "num_comments": 45},
        keywords=["pothole", "road repair"],
    ),
    ScrapedPost(
        platform=Platform.REDDIT,
        source_url="https://reddit.com/r/mumbai/comments/example2",
        author="mumbai_resident",
        content="Water supply has been cut for the 4th day in a row in Andheri West. No notice from BMC. Families are struggling with young children.",
        location="Mumbai, Maharashtra",
        timestamp=datetime.now(timezone.utc) - timedelta(hours=12),
        metadata={"subreddit": "mumbai", "score": 567, "num_comments": 89},
        keywords=["water supply"],
    ),
    ScrapedPost(
        platform=Platform.TWITTER,
        source_url="https://x.com/citizen123/status/example3",
        author="citizen123",
        content="@MunicipalCorp garbage piling up near the school in Sector 15. Health hazard for children! Please take action immediately. #SwachhBharat #civic",
        timestamp=datetime.now(timezone.utc) - timedelta(hours=2),
        metadata={"likes": 89, "retweets": 34, "views": 5600},
        keywords=["garbage"],
    ),
    ScrapedPost(
        platform=Platform.YOUTUBE,
        source_url="https://youtube.com/watch?v=example4",
        author="LocalNewsChannel",
        content="Electricity outage affects 50,000 homes in South Delhi — residents protest outside power office",
        media_urls=["https://img.youtube.com/vi/example4/hqdefault.jpg"],
        timestamp=datetime.now(timezone.utc) - timedelta(days=1),
        metadata={"video_id": "example4", "views": 12000, "top_comments": []},
        keywords=["electricity"],
    ),
    ScrapedPost(
        platform=Platform.INSTAGRAM,
        source_url="https://instagram.com/p/example5",
        author="street_reporter",
        content="Broken streetlights on NH48 service road. Accidents waiting to happen every night. Tagged @smartcity_initiative #urbanissues #safety #infrastructure",
        media_urls=["https://instagram.com/media/example5.jpg"],
        location="Gurugram, Haryana",
        timestamp=datetime.now(timezone.utc) - timedelta(hours=18),
        metadata={"likes": 156, "comments": 23, "is_video": False},
        keywords=["road repair"],
    ),
    ScrapedPost(
        platform=Platform.CIVIC,
        source_url="https://example.gov/notices/2025-budget",
        author="Municipal Corporation",
        content="Public Notice: Annual budget hearing for infrastructure development FY 2025-26. Citizens are invited to submit their grievances and suggestions online.",
        timestamp=datetime.now(timezone.utc) - timedelta(days=3),
        metadata={"source_name": "Municipal Portal", "source_type": "notices"},
        keywords=["municipal", "civic complaint"],
    ),
]


async def main():
    await init_db()
    count = await save_posts(SAMPLE_POSTS)
    print(f"✅ Seeded {count} sample posts into the database")


if __name__ == "__main__":
    asyncio.run(main())
