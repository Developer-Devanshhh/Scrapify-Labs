"""
Scrapify Labs — Main Application
FastAPI entry point with lifespan management.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import router
from src.config import get_settings
from src.database import close_db, init_db
from src.scheduler import start_scheduler, stop_scheduler

# ── Logging ──────────────────────────────────────────────────────────────

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.app_log_level.upper(), logging.INFO),
    format="%(asctime)s │ %(name)-25s │ %(levelname)-7s │ %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("scrapify")


# ── Lifespan ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    # Startup
    logger.info("🚀 Starting Scrapify Labs v0.1.0")
    await init_db()

    if settings.scrape_interval_minutes > 0:
        start_scheduler()
    else:
        logger.info("Scheduler disabled (interval = 0)")

    logger.info("✅ Scrapify Labs ready — http://localhost:%d/docs", settings.app_port)

    yield

    # Shutdown
    logger.info("Shutting down Scrapify Labs...")
    stop_scheduler()
    await close_db()
    logger.info("👋 Goodbye!")


# ── App ──────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Scrapify Labs",
    description=(
        "Microservice for scraping public citizen grievances, feedback, and sentiment "
        "from social media & government portals. Part of the Local Governance "
        "Intelligence Platform."
    ),
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — allow the main governance platform to call this service
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount all routes
app.include_router(router)
