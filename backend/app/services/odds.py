"""Fetches NFL odds from The Odds API and caches them in Postgres.

There's no background worker: `ensure_fresh_odds` runs when someone loads the games list and
only calls the API when the newest cached fetch is older than `odds_cache_hours`.
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.game import Game, Market, OddsFetch, OddsLine

logger = logging.getLogger(__name__)

FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "nfl_odds.json"
MARKETS = [m.value for m in Market]


def fetch_events_from_api() -> tuple[list[dict[str, Any]], int | None]:
    """Returns The Odds API's events and the remaining-request count from its headers."""
    settings = get_settings()
    response = httpx.get(
        f"{settings.odds_api_base_url}/sports/{settings.odds_sport_key}/odds",
        params={
            "apiKey": settings.odds_api_key,
            "bookmakers": settings.odds_bookmaker,
            "markets": ",".join(MARKETS),
            "oddsFormat": "american",
            "dateFormat": "iso",
        },
        timeout=15,
    )
    response.raise_for_status()
    remaining = response.headers.get("x-requests-remaining")
    return response.json(), int(float(remaining)) if remaining else None


def load_fixture_events(now: datetime) -> list[dict[str, Any]]:
    """Loads saved sample events, shifted so the earliest game kicks off a day from `now`."""
    events: list[dict[str, Any]] = json.loads(FIXTURE_PATH.read_text())
    earliest = min(_parse_time(e["commence_time"]) for e in events)
    shift = (now + timedelta(days=1)).replace(minute=0, second=0, microsecond=0) - earliest
    for event in events:
        shifted = _parse_time(event["commence_time"]) + shift
        event["commence_time"] = shifted.isoformat()
    return events


def upsert_events(db: Session, events: list[dict[str, Any]], bookmaker: str) -> None:
    """Inserts or updates games and their lines. Games missing from the feed are left alone."""
    for event in events:
        game_id = db.execute(
            insert(Game)
            .values(
                external_id=event["id"],
                sport_key=event["sport_key"],
                home_team=event["home_team"],
                away_team=event["away_team"],
                commence_time=_parse_time(event["commence_time"]),
            )
            .on_conflict_do_update(
                index_elements=[Game.external_id],
                set_={
                    "home_team": event["home_team"],
                    "away_team": event["away_team"],
                    "commence_time": _parse_time(event["commence_time"]),
                    "updated_at": func.now(),
                },
            )
            .returning(Game.id)
        ).scalar_one()

        book = next((b for b in event.get("bookmakers", []) if b["key"] == bookmaker), None)
        if book is None:
            continue
        for market in book["markets"]:
            if market["key"] not in MARKETS:
                continue
            for outcome in market["outcomes"]:
                db.execute(
                    insert(OddsLine)
                    .values(
                        game_id=game_id,
                        market=Market(market["key"]),
                        outcome=outcome["name"],
                        price_american=outcome["price"],
                        point=outcome.get("point"),
                        bookmaker=bookmaker,
                    )
                    .on_conflict_do_update(
                        constraint="uq_odds_line_game_market_outcome",
                        set_={
                            "price_american": outcome["price"],
                            "point": outcome.get("point"),
                            "bookmaker": bookmaker,
                            "updated_at": func.now(),
                        },
                    )
                )


def latest_fetch(db: Session, sport_key: str) -> OddsFetch | None:
    return db.scalars(
        select(OddsFetch)
        .where(OddsFetch.sport_key == sport_key)
        .order_by(OddsFetch.fetched_at.desc())
        .limit(1)
    ).first()


def ensure_fresh_odds(db: Session, *, force: bool = False) -> OddsFetch | None:
    """Refetches odds if the cache is stale (or `force`), then returns the latest fetch.

    A Postgres advisory lock makes concurrent requests wait for one fetch instead of each
    spending API credits.
    """
    settings = get_settings()
    now = datetime.now(UTC)
    ttl = timedelta(hours=settings.odds_cache_hours)

    cached = latest_fetch(db, settings.odds_sport_key)
    if not force and cached is not None and now - cached.fetched_at < ttl:
        return cached

    db.execute(text("SELECT pg_advisory_xact_lock(hashtext('odds_fetch'))"))
    cached = latest_fetch(db, settings.odds_sport_key)  # another request may have just fetched
    if not force and cached is not None and now - cached.fetched_at < ttl:
        db.commit()
        return cached

    if settings.odds_api_key:
        try:
            events, remaining = fetch_events_from_api()
        except httpx.HTTPError:
            # Serve stale odds rather than break the games list.
            logger.exception("The Odds API request failed; serving cached odds")
            db.commit()
            return cached
        source = "api"
    else:
        events, remaining = load_fixture_events(now), None
        source = "fixture"

    upsert_events(db, events, settings.odds_bookmaker)
    fetch = OddsFetch(
        sport_key=settings.odds_sport_key,
        fetched_at=now,
        source=source,
        event_count=len(events),
        requests_remaining=remaining,
    )
    db.add(fetch)
    db.commit()
    return fetch


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


if __name__ == "__main__":
    # Force a refresh now: `uv run python -m app.services.odds`
    # (or `docker compose exec backend python -m app.services.odds`).
    from app.core.db import SessionLocal

    with SessionLocal() as session:
        result = ensure_fresh_odds(session, force=True)
        assert result is not None
        print(
            f"Loaded {result.event_count} games from {result.source}"
            + (f"; {result.requests_remaining} API credits left" if result.source == "api" else "")
        )
