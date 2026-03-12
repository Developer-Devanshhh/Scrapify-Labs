# Integration & Scaling Guide — Scrapify Labs v3

This guide explains how to control the Scrapify microservice via its API from your main governance platform and provides details on platform reliability without Apify.

---

## 1. Controlling the Microservice via API

Your main governance platform (or any external app) can control Scrapify entirely through these REST endpoints:

| Method | Endpoint       | What it does                                 |
| ------ | -------------- | -------------------------------------------- |
| `POST` | `/api/scrape`  | **Trigger** a scrape job (the core command)  |
| `GET`  | `/api/results` | **Retrieve** stored results with filters     |
| `GET`  | `/api/jobs`    | **List** all past scrape jobs & their status |
| `GET`  | `/health`      | **Health check** — is the service alive?     |

### Example: Triggering a Scrape

```json
POST http://localhost:8000/api/scrape
{
  "keywords": ["pothole", "water supply", "garbage"],
  "platforms": ["google_maps", "civic", "twitter", "reddit"],
  "max_results": 10,
  "webhook_url": "https://your-main-app.com/api/scrapify-callback"
}
```

### Example: Fetching Enriched Results

```bash
curl "http://localhost:8000/api/results?platform=google_maps&page_size=20"
```

Each result will contain:

- `content`, `author`, `platform`, `source_url`
- `latitude`, `longitude`, `location` (geo-tagged)
- `structured_data` → `{ category, urgency, sentiment, summary, action_needed }` (AI enriched)

### Integration Pattern

```
Your Governance App  ──POST /api/scrape──▶  Scrapify (this microservice)
                                                │
                                          scrapes + Gemini enriches
                                                │
                     ◀──webhook callback────────┘  (or poll GET /api/results)
```

---

## 2. Apify Alternatives & Platform Reliability

If you remove `APIFY_API_TOKEN` from your `.env`, the system automatically falls back to local engines. 6 of 8 platforms work completely free without Apify.

### Fallback Matrix

| Platform        | With Apify (Cloud) | Without Apify (Local Fallback)      |
| --------------- | ------------------ | ----------------------------------- |
| **Twitter**     | Apify actor        | → Playwright Stealth (your cookies) |
| **Instagram**   | Apify actor        | → Playwright Stealth (your session) |
| **Facebook**    | Apify actor        | → Crawl4AI (limited extraction)     |
| **Threads**     | Apify actor        | → Crawl4AI (limited extraction)     |
| **Reddit**      | Apify actor        | → PRAW (Official API, free)         |
| **YouTube**     | —                  | YouTube Data API v3 (always free)   |
| **Google Maps** | —                  | Places API (your credits)           |
| **Civic**       | —                  | Crawl4AI (Always open-source/free)  |

### Other Paid Alternatives

- **ScraperAPI**: Best for rotating proxies if Playwright gets blocked.
- **SocialData.tools**: Extremely reliable paid alternative for Twitter specifically.
- **Bright Data**: Heavy-duty enterprise scraping infrastructure.

---
