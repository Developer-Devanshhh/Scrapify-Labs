"""
Scrapify Labs — Webhook Dispatcher
Sends scrape results to the main governance platform via HTTP callbacks.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import datetime

import httpx

from src.config import get_settings
from src.models import ScrapedPost

logger = logging.getLogger(__name__)


async def dispatch_webhook(
    posts: list[ScrapedPost],
    job_id: str,
    webhook_url: str | None = None,
) -> bool:
    """
    Send scrape results to a webhook URL.

    Args:
        posts: List of scraped posts to deliver.
        job_id: The job ID that produced these results.
        webhook_url: Override URL (falls back to config WEBHOOK_URL).

    Returns:
        True if delivery succeeded, False otherwise.
    """
    settings = get_settings()
    url = webhook_url or settings.webhook_url

    if not url:
        logger.debug("No webhook URL configured — skipping delivery")
        return False

    payload = {
        "event": "scrape.completed",
        "job_id": job_id,
        "timestamp": datetime.utcnow().isoformat(),
        "total_results": len(posts),
        "results": [post.model_dump(mode="json") for post in posts],
    }

    payload_bytes = json.dumps(payload, default=str).encode()

    # Sign the payload if a secret is configured
    headers = {"Content-Type": "application/json"}
    if settings.webhook_secret:
        signature = hmac.new(
            settings.webhook_secret.encode(),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()
        headers["X-Scrapify-Signature"] = f"sha256={signature}"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, content=payload_bytes, headers=headers)

            if resp.status_code < 300:
                logger.info(
                    "Webhook delivered to %s — %d results, status %d",
                    url, len(posts), resp.status_code,
                )
                return True
            else:
                logger.warning(
                    "Webhook delivery failed — %s returned %d: %s",
                    url, resp.status_code, resp.text[:200],
                )
                return False

    except httpx.TimeoutException:
        logger.error("Webhook delivery timed out: %s", url)
        return False
    except Exception as e:
        logger.error("Webhook delivery error: %s", e)
        return False
