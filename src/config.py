"""
Scrapify Labs — Configuration Management
Uses pydantic-settings for type-safe env variable loading.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from .env file and environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────────────────────────
    app_name: str = "ScrapifyLabs"
    app_env: str = "development"
    app_port: int = 8000
    app_log_level: str = "INFO"

    # ── Database ─────────────────────────────────────────────────────────
    database_url: str = "sqlite+aiosqlite:///./scrapify.db"

    # ── Reddit (PRAW) ────────────────────────────────────────────────────
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "ScrapifyLabs/1.0"

    # ── YouTube Data API v3 ──────────────────────────────────────────────
    youtube_api_key: str = ""

    # ── Twitter/X (twscrape or Playwright) ────────────────────────────
    twitter_accounts: str = ""  # username:pass:email:email_pass per line
    twitter_auth_token: str = ""  # browser cookie for Playwright fallback
    twitter_ct0: str = ""  # browser cookie for Playwright fallback

    # ── Instagram (instaloader or Playwright) ─────────────────────────
    instagram_username: str = ""
    instagram_password: str = ""
    instagram_session_id: str = ""  # browser cookie for Playwright fallback

    # ── Apify (free tier — social media at scale) ─────────────────────────
    apify_api_token: str = ""

    # ── Webhook Integration ──────────────────────────────────────────────
    webhook_url: str = ""
    webhook_secret: str = ""

    # ── Scheduler ────────────────────────────────────────────────────────
    scrape_interval_minutes: int = 60

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def reddit_configured(self) -> bool:
        return bool(self.reddit_client_id and self.reddit_client_secret)

    @property
    def youtube_configured(self) -> bool:
        return bool(self.youtube_api_key)

    @property
    def twitter_configured(self) -> bool:
        return bool(self.twitter_accounts or self.twitter_auth_token)

    @property
    def instagram_configured(self) -> bool:
        return True  # Playwright fallback always available


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance — call this instead of constructing Settings()."""
    return Settings()
