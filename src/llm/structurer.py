"""
Scrapify Labs — Gemini LLM Structurer
Uses Google Gemini Flash to convert raw scraped content into structured
governance intelligence with categories, urgency, sentiment, and location.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from src.config import Settings, get_settings
from src.llm.prompts import SYSTEM_PROMPT, BATCH_PROMPT_TEMPLATE, SINGLE_POST_TEMPLATE
from src.models import ScrapedPost

logger = logging.getLogger(__name__)

# Gemini Flash API endpoint (REST, free tier: 15 RPM)
GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.0-flash:generateContent"
)


async def structure_posts(
    posts: list[ScrapedPost],
    settings: Settings | None = None,
    batch_size: int = 10,
) -> list[ScrapedPost]:
    """
    Run LLM structuring on a list of scraped posts.
    Populates the `structured_data` field on each post.
    Returns the same posts with structured_data filled in.
    """
    settings = settings or get_settings()

    if not settings.gemini_api_key:
        logger.info("Gemini API key not set — skipping LLM structuring.")
        return posts

    city = settings.demo_city or "India"

    # Process in batches to minimize API calls
    for i in range(0, len(posts), batch_size):
        batch = posts[i : i + batch_size]
        try:
            structured = await _call_gemini_batch(batch, city, settings.gemini_api_key)
            for post, data in zip(batch, structured):
                post.structured_data = data
                # Also extract location from LLM if not already set
                if not post.location and data.get("location"):
                    post.location = data["location"]
        except Exception as e:
            logger.error("LLM batch structuring failed: %s", e)
            # Fall back to single-post processing
            for post in batch:
                try:
                    data = await _call_gemini_single(post, city, settings.gemini_api_key)
                    post.structured_data = data
                    if not post.location and data.get("location"):
                        post.location = data["location"]
                except Exception as inner_e:
                    logger.warning("LLM single-post failed for '%s': %s", post.id, inner_e)

    structured_count = sum(1 for p in posts if p.structured_data)
    logger.info("LLM structured %d / %d posts", structured_count, len(posts))
    return posts


async def _call_gemini_batch(
    posts: list[ScrapedPost], city: str, api_key: str
) -> list[dict[str, Any]]:
    """Call Gemini with a batch of posts. Returns list of structured dicts."""

    posts_text = "\n\n".join(
        f"Post {i+1} [{p.platform.value}] by @{p.author or 'unknown'}:\n{p.content[:500]}"
        for i, p in enumerate(posts)
    )

    prompt = BATCH_PROMPT_TEMPLATE.format(
        count=len(posts), city=city, posts_text=posts_text
    )

    raw = await _gemini_request(prompt, api_key)
    parsed = _parse_json_response(raw)

    if isinstance(parsed, list) and len(parsed) == len(posts):
        return parsed

    # If parsing failed or count mismatch, try to salvage
    if isinstance(parsed, list):
        # Pad or trim
        while len(parsed) < len(posts):
            parsed.append({})
        return parsed[:len(posts)]

    # Single dict returned instead of array
    if isinstance(parsed, dict):
        return [parsed] + [{}] * (len(posts) - 1)

    return [{}] * len(posts)


async def _call_gemini_single(
    post: ScrapedPost, city: str, api_key: str
) -> dict[str, Any]:
    """Call Gemini for a single post. Returns structured dict."""

    prompt = SINGLE_POST_TEMPLATE.format(
        city=city, content=post.content[:800]
    )

    raw = await _gemini_request(prompt, api_key)
    parsed = _parse_json_response(raw)

    if isinstance(parsed, dict):
        return parsed
    if isinstance(parsed, list) and parsed:
        return parsed[0]
    return {}


async def _gemini_request(prompt: str, api_key: str) -> str:
    """Send a request to Gemini Flash API and return the text response."""

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "systemInstruction": {
            "parts": [{"text": SYSTEM_PROMPT}]
        },
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 4096,
            "responseMimeType": "application/json",
        },
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{GEMINI_API_URL}?key={api_key}",
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()

    # Extract text from Gemini response
    candidates = data.get("candidates", [])
    if not candidates:
        raise ValueError("No candidates in Gemini response")

    parts = candidates[0].get("content", {}).get("parts", [])
    if not parts:
        raise ValueError("No parts in Gemini response")

    return parts[0].get("text", "")


def _parse_json_response(raw: str) -> Any:
    """Parse JSON from Gemini response, handling markdown code blocks."""
    text = raw.strip()

    # Strip markdown code blocks if present
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last lines (```json and ```)
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON array or object in the text
        for start_char, end_char in [("[", "]"), ("{", "}")]:
            start = text.find(start_char)
            end = text.rfind(end_char)
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    continue

        logger.warning("Could not parse Gemini JSON response: %s", text[:200])
        return {}
