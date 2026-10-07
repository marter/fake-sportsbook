from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    environment: str = "local"
    database_url: str = (
        "postgresql+psycopg://sportsbook:sportsbook@localhost:5433/fake_sportsbook"
    )
    jwt_secret_key: str = "change-me-in-env"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7
    cors_origins: list[str] = ["http://localhost:5174"]

    # Play money every new account starts with ($1,000.00).
    starting_balance_cents: int = 100_000
    # Registration closes once this many accounts exist. Keeps the public site to friends.
    max_users: int = 5

    # Email verification. New accounts must verify before betting; unverified accounts
    # are deleted after `unverified_account_ttl_hours` so they don't hold a sign-up slot.
    email_verification_required: bool = True
    email_backend: str = "console"  # "console" (logs the email), "resend", or "memory" (tests)
    resend_api_key: str = ""
    email_from: str = "Fake Sportsbook <no-reply@martinteran.me>"
    app_base_url: str = "http://localhost:5174"  # used to build links in emails
    verification_token_ttl_hours: int = 24
    unverified_account_ttl_hours: int = 48

    # The Odds API. With no key set, odds load from fixtures/nfl_odds.json instead.
    odds_api_key: str = ""
    odds_api_base_url: str = "https://api.the-odds-api.com/v4"
    odds_sport_key: str = "americanfootball_nfl"
    odds_bookmaker: str = "draftkings"
    # Odds are refetched at most this often. Each refetch costs 3 credits (3 markets), so
    # daily is ~90 of the free plan's 500 monthly credits.
    odds_cache_hours: int = 24
    # Settlement: start checking for a final score this long after kickoff, and call the
    # scores endpoint (2 credits) at most this often while any bet is waiting on a result.
    game_duration_minutes: int = 180
    scores_min_interval_minutes: int = 30
    # Stop spending credits on a game with no final score this long after kickoff (postponed,
    # cancelled...); it shows up on the admin page instead, where its bets can be voided.
    settlement_give_up_hours: int = 24
    # Skip score checks once the API reports fewer credits than this, so the daily odds
    # refresh still has room.
    scores_min_credits: int = 50
    # Background worker (app.worker): how often it refreshes odds and settles bets.
    worker_interval_seconds: int = 900


@lru_cache
def get_settings() -> Settings:
    return Settings()
