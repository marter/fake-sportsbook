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

    # The Odds API. With no key set, odds load from fixtures/nfl_odds.json instead.
    odds_api_key: str = ""
    odds_api_base_url: str = "https://api.the-odds-api.com/v4"
    odds_sport_key: str = "americanfootball_nfl"
    odds_bookmaker: str = "draftkings"
    # Odds are refetched at most this often. Each refetch costs 3 credits (3 markets).
    odds_cache_hours: int = 24 * 7


@lru_cache
def get_settings() -> Settings:
    return Settings()
