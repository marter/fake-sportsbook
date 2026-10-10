"""Fetches odds from The Odds API and caches them in Postgres, per sport.

`ensure_fresh_odds(db, sport)` runs when someone opens that sport's tab and from the background
worker, and only calls the API when the newest cached fetch is older than `odds_cache_hours`.
Out-of-season sports (per The Odds API's free /sports list) aren't fetched at all.
"""

import hashlib
import json
import logging
import math
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.game import Game, Market, OddsFetch, OddsLine
from app.sports import BY_API_KEY, BY_SLUG, FIXTURES_DIR, SPORTS, Sport

logger = logging.getLogger(__name__)

MARKETS = [m.value for m in Market]
ACTIVE_CACHE_TTL = timedelta(hours=6)
_active_cache: tuple[datetime, frozenset[str]] | None = None


def enabled_sports() -> list[Sport]:
    return [s for s in SPORTS if s.slug in get_settings().enabled_sports]


def fetch_active_sport_keys() -> frozenset[str]:
    """The Odds API keys of sports currently in season. This endpoint costs no credits."""
    settings = get_settings()
    response = httpx.get(
        f"{settings.odds_api_base_url}/sports",
        params={"apiKey": settings.odds_api_key},
        timeout=15,
    )
    response.raise_for_status()
    return frozenset(s["key"] for s in response.json() if s.get("active"))


def is_active(sport: Sport) -> bool:
    """In season? Without an API key, a sport is "in season" if it has a sample fixture file."""
    global _active_cache
    if not get_settings().odds_api_key:
        return sport.fixture_path.exists()
    now = datetime.now(UTC)
    if _active_cache is None or now - _active_cache[0] > ACTIVE_CACHE_TTL:
        try:
            _active_cache = (now, fetch_active_sport_keys())
        except httpx.HTTPError:
            logger.exception("Couldn't check which sports are in season")
            if _active_cache is None:
                return True  # assume in season rather than hide a league
    return sport.api_key in _active_cache[1]


def fetch_events_from_api(sport: Sport) -> tuple[list[dict[str, Any]], int | None]:
    """Returns The Odds API's events and the remaining-request count from its headers."""
    settings = get_settings()
    response = httpx.get(
        f"{settings.odds_api_base_url}/sports/{sport.api_key}/odds",
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


def fetch_props_from_api(sport: Sport, event_id: str) -> tuple[dict[str, Any], int | None]:
    """One game's player props. Costs 1 credit per prop market."""
    settings = get_settings()
    response = httpx.get(
        f"{settings.odds_api_base_url}/sports/{sport.api_key}/events/{event_id}/odds",
        params={
            "apiKey": settings.odds_api_key,
            "bookmakers": settings.odds_bookmaker,
            "markets": ",".join(m.key for m in sport.prop_markets),
            "oddsFormat": "american",
            "dateFormat": "iso",
        },
        timeout=15,
    )
    response.raise_for_status()
    remaining = response.headers.get("x-requests-remaining")
    return response.json(), int(float(remaining)) if remaining else None


def fixture_props(sport: Sport, game: Game) -> dict[str, Any]:
    """Made-up but stable props, in the API's event shape, from a sample roster (dev only)."""
    path = FIXTURES_DIR / f"{sport.slug}_players.json"
    roster: dict[str, list[str]] = json.loads(path.read_text()) if path.exists() else {}
    outcomes: dict[str, list[dict[str, Any]]] = {m.key: [] for m in sport.prop_markets}
    for team in (game.away_team, game.home_team):
        players = roster.get(team, [])
        for i, player in enumerate(players):
            seed = int(hashlib.sha256(f"{game.external_id}:{player}".encode()).hexdigest(), 16)
            if i == 0 and "player_pass_yds" in outcomes:  # the first listed player is the QB
                line = 175.5 + seed % 100
                for side in ("Over", "Under"):
                    outcomes["player_pass_yds"].append(
                        {"name": side, "description": player, "price": -112, "point": line}
                    )
            if "player_anytime_td" in outcomes:
                # Running backs (listed second) are favorites to score; everyone else is plus money.
                price = -140 + (seed % 4) * 10 if i == 1 else 110 + (seed % 30) * 10
                outcomes["player_anytime_td"].append(
                    {"name": "Yes", "description": player, "price": price}
                )
    return {
        "id": game.external_id,
        "bookmakers": [
            {
                "key": get_settings().odds_bookmaker,
                "markets": [{"key": k, "outcomes": v} for k, v in outcomes.items() if v],
            }
        ],
    }


def low_on_credits(db: Session) -> bool:
    """True if the most recent API call reported fewer credits left than the floor."""
    last_api_call = db.scalars(
        select(OddsFetch)
        .where(OddsFetch.source == "api", OddsFetch.requests_remaining.is_not(None))
        .order_by(OddsFetch.fetched_at.desc())
        .limit(1)
    ).first()
    return (
        last_api_call is not None
        and last_api_call.requests_remaining is not None
        and last_api_call.requests_remaining < get_settings().scores_min_credits
    )


def props_unavailable_reason(game: Game, now: datetime) -> str | None:
    """Why this game's props can't be fetched or shown right now, or None if they can."""
    sport = BY_API_KEY.get(game.sport_key)
    if sport is None or not sport.prop_markets:
        return f"No player props for {sport.name if sport else 'this league'} yet."
    if game.completed or game.commence_time <= now:
        return "This game has started, so props are closed."
    if game.commence_time - now > timedelta(hours=get_settings().props_window_hours):
        return "Player props open about two days before kickoff."
    return None


def ensure_props(db: Session, game: Game) -> None:
    """Fetches the game's player props the first time they're asked for, once per game.

    Props cost a credit per market per game, so they're never fetched until someone looks,
    never more than once, and never when credits are low. Odds lock at placement, so an
    older prop line is fine for play money.
    """
    settings = get_settings()
    now = datetime.now(UTC)
    if game.props_fetched_at is not None or props_unavailable_reason(game, now):
        return
    sport = BY_API_KEY[game.sport_key]

    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"props:{game.id}"}
    )
    db.refresh(game)
    if game.props_fetched_at is not None:  # another request just fetched them
        db.commit()
        return

    if settings.odds_api_key:
        if low_on_credits(db):
            logger.warning("Skipping props for %s: low on API credits", game.external_id)
            db.commit()
            return
        try:
            event, remaining = fetch_props_from_api(sport, game.external_id)
        except httpx.HTTPError:
            logger.exception("Props request for %s failed", game.external_id)
            db.commit()
            return
        source = "api"
    else:
        event, remaining = fixture_props(sport, game), None
        source = "fixture"

    upsert_lines(db, game.id, event, settings.odds_bookmaker, {m.key for m in sport.prop_markets})
    game.props_fetched_at = now
    db.add(
        OddsFetch(
            sport_key=sport.api_key,
            kind="props",
            fetched_at=now,
            source=source,
            event_count=1,
            requests_remaining=remaining,
        )
    )
    db.commit()


def fetch_scores_from_api(sport: Sport) -> tuple[list[dict[str, Any]], int | None]:
    """Returns recent and upcoming games with scores (completed ones from the last 3 days).

    Costs 2 credits per call because of `daysFrom`.
    """
    settings = get_settings()
    response = httpx.get(
        f"{settings.odds_api_base_url}/sports/{sport.api_key}/scores",
        params={"apiKey": settings.odds_api_key, "daysFrom": 3, "dateFormat": "iso"},
        timeout=15,
    )
    response.raise_for_status()
    remaining = response.headers.get("x-requests-remaining")
    return response.json(), int(float(remaining)) if remaining else None


def load_fixture_events(sport: Sport, now: datetime) -> list[dict[str, Any]]:
    """Loads saved sample events, moved forward by whole weeks so they're upcoming.

    Shifting by whole weeks keeps each game on its real weekday and kickoff time
    (Sunday 1pm stays Sunday 1pm, Thursday night stays Thursday night).
    """
    if not sport.fixture_path.exists():
        return []
    events: list[dict[str, Any]] = json.loads(sport.fixture_path.read_text())
    earliest = min(_parse_time(e["commence_time"]) for e in events)
    week = timedelta(weeks=1)
    weeks_behind = max(0, math.ceil((now - earliest) / week))
    shift = weeks_behind * week
    for event in events:
        shifted = _parse_time(event["commence_time"]) + shift
        event["commence_time"] = shifted.isoformat()
    return events


def upsert_events(
    db: Session, events: list[dict[str, Any]], bookmaker: str, *, reset_results: bool = False
) -> None:
    """Inserts or updates games and their lines. Games missing from the feed are left alone.

    `reset_results` clears any final score on the updated games. Only fixture mode needs it: it
    moves sample games back into the future, and a game finished in an earlier dev session
    would otherwise reappear as upcoming but already final.
    """
    reset = {"completed": False, "home_score": None, "away_score": None} if reset_results else {}
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
                    **reset,
                },
            )
            .returning(Game.id)
        ).scalar_one()

        upsert_lines(db, game_id, event, bookmaker, set(MARKETS))


def upsert_lines(
    db: Session, game_id: Any, event: dict[str, Any], bookmaker: str, markets: set[str]
) -> None:
    """Inserts or updates one game's lines for the given markets from an API event."""
    book = next((b for b in event.get("bookmakers", []) if b["key"] == bookmaker), None)
    if book is None:
        return
    for market in book["markets"]:
        if market["key"] not in markets:
            continue
        for outcome in market["outcomes"]:
            db.execute(
                insert(OddsLine)
                .values(
                    game_id=game_id,
                    market=market["key"],
                    outcome=outcome["name"],
                    participant=outcome.get("description", ""),
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


def latest_fetch(db: Session, sport_key: str, kind: str = "odds") -> OddsFetch | None:
    return db.scalars(
        select(OddsFetch)
        .where(OddsFetch.sport_key == sport_key, OddsFetch.kind == kind)
        .order_by(OddsFetch.fetched_at.desc())
        .limit(1)
    ).first()


def ensure_fresh_odds(db: Session, sport: Sport, *, force: bool = False) -> OddsFetch | None:
    """Refetches the sport's odds if the cache is stale (or `force`) and the sport is in season,
    then returns its latest fetch.

    A Postgres advisory lock per sport makes concurrent requests wait for one fetch instead of
    each spending API credits.
    """
    settings = get_settings()
    now = datetime.now(UTC)
    ttl = timedelta(hours=settings.odds_cache_hours)

    cached = latest_fetch(db, sport.api_key)
    if not force and cached is not None and now - cached.fetched_at < ttl:
        return cached
    if not force and not is_active(sport):
        return cached

    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"odds_fetch:{sport.slug}"}
    )
    cached = latest_fetch(db, sport.api_key)  # another request may have just fetched
    if not force and cached is not None and now - cached.fetched_at < ttl:
        db.commit()
        return cached

    if settings.odds_api_key:
        try:
            events, remaining = fetch_events_from_api(sport)
        except httpx.HTTPError:
            # Serve stale odds rather than break the games list.
            logger.exception("The Odds API request failed; serving cached odds")
            db.commit()
            return cached
        source = "api"
    else:
        events, remaining = load_fixture_events(sport, now), None
        source = "fixture"

    upsert_events(db, events, settings.odds_bookmaker, reset_results=source == "fixture")
    fetch = OddsFetch(
        sport_key=sport.api_key,
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
    # Force a refresh now: `uv run python -m app.services.odds [nfl nba ...]` (default: every
    # in-season sport). In production: `docker compose exec backend python -m app.services.odds`.
    import sys

    from app.core.db import SessionLocal

    chosen = [BY_SLUG[s] for s in sys.argv[1:]] or [s for s in enabled_sports() if is_active(s)]
    with SessionLocal() as session:
        for sport in chosen:
            result = ensure_fresh_odds(session, sport, force=True)
            assert result is not None
            left = result.requests_remaining
            credits = f"; {left} credits left" if result.source == "api" else ""
            print(f"{sport.name}: {result.event_count} games from {result.source}{credits}")
