# Scrapify Labs

> **Microservice for scraping public citizen grievances, feedback, and sentiment from social media & government portals.**

Part of the **Local Governance Intelligence Platform** — Scrapify Labs collects, structures, and delivers public data so the main platform can prioritize issues, verify work, analyze sentiment, and generate transparent public updates.

## Quick Start

```bash
# Clone & setup
git clone <repo-url> && cd Scrapify
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your API keys

# Run
uvicorn src.main:app --reload --port 8000

# API docs at http://localhost:8000/docs
```

## Architecture

```
Scrapify Labs (FastAPI Microservice)
├── Pluggable Scrapers (Twitter, Reddit, YouTube, Instagram, Civic)
├── Unified Data Model (ScrapedPost)
├── SQLite Storage (swappable to Postgres)
├── Scheduled & On-demand Scraping
└── REST API + Webhook Integration
```

## Supported Platforms

| Platform | Library | Status |
|----------|---------|--------|
| Reddit | PRAW | ✅ Ready |
| YouTube | yt-dlp + Data API v3 | ✅ Ready |
| Twitter/X | twscrape | 🔧 Beta |
| Instagram | instaloader | 🔧 Beta |
| Gov/Civic | city-scrapers | 📋 Planned |

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/api/scrape` | Trigger a scrape job |
| `GET` | `/api/results` | Fetch scraped data (paginated) |
| `GET` | `/api/results/{platform}` | Platform-filtered results |
| `GET` | `/api/jobs` | List scrape jobs |
| `DELETE` | `/api/results/{id}` | Delete a result |

## Integration

Scrapify exposes three integration modes for the main governance platform:

1. **Pull** — `GET /api/results` to poll for new data
2. **Push** — Configure `WEBHOOK_URL` in `.env` for automatic callbacks
3. **On-demand** — `POST /api/scrape` for immediate scraping

## License

MIT
