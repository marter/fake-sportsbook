import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.game import Game, OddsFetch, OddsLine
from app.services import odds
from app.sports import BY_SLUG

NFL = BY_SLUG["nfl"]


def count(db: Session, model: type) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


def test_games_loads_fixture_when_no_api_key(
    client: TestClient, db: Session, auth_headers: dict[str, str]
) -> None:
    response = client.get("/api/games", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body["games"]) == 8
    assert body["odds_updated_at"] is not None

    game = body["games"][0]
    markets = sorted({line["market"] for line in game["odds_lines"]})
    assert markets == ["h2h", "spreads", "totals"]
    assert len(game["odds_lines"]) == 6
    assert datetime.fromisoformat(game["commence_time"]) > datetime.now(UTC)
    assert db.scalars(select(OddsFetch)).one().source == "fixture"


def test_games_requires_auth(client: TestClient) -> None:
    assert client.get("/api/games").status_code == 401


def test_cache_is_reused_within_ttl(
    client: TestClient, db: Session, auth_headers: dict[str, str]
) -> None:
    client.get("/api/games", headers=auth_headers)
    client.get("/api/games", headers=auth_headers)
    assert count(db, OddsFetch) == 1


def test_stale_cache_refetches_without_duplicating(
    client: TestClient, db: Session, auth_headers: dict[str, str]
) -> None:
    client.get("/api/games", headers=auth_headers)
    db.execute(update(OddsFetch).values(fetched_at=datetime.now(UTC) - timedelta(days=8)))
    db.commit()

    client.get("/api/games", headers=auth_headers)
    assert count(db, OddsFetch) == 2
    assert count(db, Game) == 8
    assert count(db, OddsLine) == 48


def test_api_mode_fetches_once_and_updates_prices(
    client: TestClient, db: Session, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "odds_api_key", "test-key")
    events = odds.load_fixture_events(NFL, datetime.now(UTC))
    calls: list[int] = []

    def fake_fetch(sport):
        calls.append(1)
        return events, 497

    monkeypatch.setattr(odds, "fetch_events_from_api", fake_fetch)
    client.get("/api/games", headers=auth_headers)
    client.get("/api/games", headers=auth_headers)
    assert len(calls) == 1
    fetch = db.scalars(select(OddsFetch)).one()
    assert (fetch.source, fetch.requests_remaining) == ("api", 497)

    # A forced refresh with a moved line updates the existing row in place.
    events[0]["bookmakers"][0]["markets"][0]["outcomes"][0]["price"] = 999
    odds.ensure_fresh_odds(db, NFL, force=True)
    assert len(calls) == 2
    assert count(db, OddsLine) == 48
    assert db.scalar(select(func.max(OddsLine.price_american))) == 999


def test_api_failure_serves_stale_cache(
    client: TestClient, db: Session, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    client.get("/api/games", headers=auth_headers)  # seed from fixture
    db.execute(update(OddsFetch).values(fetched_at=datetime.now(UTC) - timedelta(days=8)))
    db.commit()

    monkeypatch.setattr(get_settings(), "odds_api_key", "test-key")

    def failing_fetch(sport):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(odds, "fetch_events_from_api", failing_fetch)
    response = client.get("/api/games", headers=auth_headers)
    assert response.status_code == 200
    assert len(response.json()["games"]) == 8
    assert count(db, OddsFetch) == 1


def test_started_games_are_hidden(
    client: TestClient, db: Session, auth_headers: dict[str, str]
) -> None:
    client.get("/api/games", headers=auth_headers)
    first = db.scalars(select(Game).order_by(Game.commence_time)).first()
    assert first is not None
    first.commence_time = datetime.now(UTC) - timedelta(minutes=5)
    db.commit()

    games = client.get("/api/games", headers=auth_headers).json()["games"]
    assert len(games) == 7
    assert str(first.id) not in {g["id"] for g in games}


@pytest.mark.parametrize("days_later", [0, 3, 9, 40])
def test_fixture_keeps_real_weekdays(days_later: int) -> None:
    fixture = json.loads(NFL.fixture_path.read_text())
    originals = [odds._parse_time(e["commence_time"]) for e in fixture]
    now = min(originals) - timedelta(days=2) + timedelta(days=days_later)

    shifted = [odds._parse_time(e["commence_time"]) for e in odds.load_fixture_events(NFL, now)]
    for before, after in zip(originals, shifted, strict=True):
        assert (after - before) % timedelta(weeks=1) == timedelta(0)
    assert min(shifted) > now - timedelta(weeks=1)
    assert max(shifted) > now


def test_fixture_reload_clears_stale_results(
    client: TestClient, db: Session, auth_headers: dict[str, str]
) -> None:
    client.get("/api/games", headers=auth_headers)
    game = db.scalars(select(Game)).first()
    assert game is not None
    game.completed, game.home_score, game.away_score = True, 3, 0
    db.commit()

    odds.ensure_fresh_odds(db, NFL, force=True)
    db.refresh(game)
    assert (game.completed, game.home_score, game.away_score) == (False, None, None)
