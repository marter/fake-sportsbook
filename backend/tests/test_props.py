from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.bet import Bet, BetStatus
from app.models.game import Game, OddsFetch
from app.services import odds
from tests.test_bets import leg_payload


def nfl_game(client: TestClient, headers: dict[str, str], db: Session, hours: float = 24) -> Game:
    """The first sample NFL game, moved to kick off `hours` from now."""
    first = client.get("/api/games?sport=nfl", headers=headers).json()["games"][0]
    game = db.get(Game, first["id"])
    assert game is not None
    game.commence_time = datetime.now(UTC) + timedelta(hours=hours)
    db.commit()
    return game


def props(client: TestClient, headers: dict[str, str], game_id: Any) -> dict[str, Any]:
    response = client.get(f"/api/games/{game_id}/props", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def prop_fetches(db: Session) -> int:
    count = select(func.count()).select_from(OddsFetch).where(OddsFetch.kind == "props")
    return db.scalar(count) or 0


def test_props_load_once_with_both_markets(
    client: TestClient, db: Session, auth_headers: dict[str, str]
) -> None:
    game = nfl_game(client, auth_headers, db)
    body = props(client, auth_headers, game.id)
    assert body["unavailable_reason"] is None
    assert [m["key"] for m in body["markets"]] == ["player_anytime_td", "player_pass_yds"]

    by_market: dict[str, list[dict]] = {}
    for line in body["lines"]:
        by_market.setdefault(line["market"], []).append(line)
    td = by_market["player_anytime_td"]
    assert td and all(line["outcome"] == "Yes" and line["participant"] for line in td)
    pass_yds = by_market["player_pass_yds"]
    assert {line["outcome"] for line in pass_yds} == {"Over", "Under"}
    assert len({line["participant"] for line in pass_yds}) == 2  # one QB per team

    props(client, auth_headers, game.id)
    assert prop_fetches(db) == 1  # fetched once, then served from the database

    listed = client.get("/api/games?sport=nfl", headers=auth_headers).json()["games"]
    listed_game = next(g for g in listed if g["id"] == str(game.id))
    assert listed_game["has_props"] is True
    assert {line["market"] for line in listed_game["odds_lines"]} == {"h2h", "spreads", "totals"}


def test_props_not_fetched_too_early(
    client: TestClient, db: Session, auth_headers: dict[str, str]
) -> None:
    game = nfl_game(client, auth_headers, db, hours=72)
    body = props(client, auth_headers, game.id)
    assert "two days before kickoff" in body["unavailable_reason"]
    assert body["lines"] == []
    assert prop_fetches(db) == 0


def test_no_props_for_leagues_without_them(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    game = client.get("/api/games?sport=nba", headers=auth_headers).json()["games"][0]
    assert game["has_props"] is False
    body = props(client, auth_headers, game["id"])
    assert "No player props for NBA" in body["unavailable_reason"]


def api_mode(monkeypatch: pytest.MonkeyPatch, credits_left: int = 400) -> list[str]:
    monkeypatch.setattr(get_settings(), "odds_api_key", "test-key")
    calls: list[str] = []

    def fake(sport, event_id):
        calls.append(event_id)
        return {
            "id": event_id,
            "bookmakers": [
                {
                    "key": "draftkings",
                    "markets": [
                        {
                            "key": "player_anytime_td",
                            "outcomes": [
                                {"name": "Yes", "description": "Some Player", "price": 150}
                            ],
                        }
                    ],
                }
            ],
        }, credits_left

    monkeypatch.setattr(odds, "fetch_props_from_api", fake)
    return calls


def test_api_mode_fetches_once_and_logs_credits(
    client: TestClient, db: Session, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    game = nfl_game(client, auth_headers, db)
    calls = api_mode(monkeypatch)
    props(client, auth_headers, game.id)
    props(client, auth_headers, game.id)
    assert calls == [game.external_id]
    fetch = db.scalars(select(OddsFetch).where(OddsFetch.kind == "props")).one()
    assert (fetch.source, fetch.requests_remaining) == ("api", 400)


def test_low_credits_skip_props(
    client: TestClient, db: Session, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    game = nfl_game(client, auth_headers, db)
    db.add(
        OddsFetch(
            sport_key="americanfootball_nfl",
            kind="odds",
            fetched_at=datetime.now(UTC),
            source="api",
            event_count=1,
            requests_remaining=20,
        )
    )
    db.commit()
    calls = api_mode(monkeypatch)
    assert props(client, auth_headers, game.id)["lines"] == []
    assert calls == []


def test_api_failure_retries_next_time(
    client: TestClient, db: Session, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    game = nfl_game(client, auth_headers, db)
    monkeypatch.setattr(get_settings(), "odds_api_key", "test-key")

    def down(sport, event_id):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(odds, "fetch_props_from_api", down)
    assert props(client, auth_headers, game.id)["lines"] == []
    db.refresh(game)
    assert game.props_fetched_at is None  # not marked as fetched, so it retries

    calls = api_mode(monkeypatch)
    assert len(props(client, auth_headers, game.id)["lines"]) == 1
    assert calls == [game.external_id]


def test_bet_on_a_prop(client: TestClient, db: Session, auth_headers: dict[str, str]) -> None:
    game = nfl_game(client, auth_headers, db)
    body = props(client, auth_headers, game.id)
    over = next(
        line
        for line in body["lines"]
        if line["market"] == "player_pass_yds" and line["outcome"] == "Over"
    )
    placed = client.post(
        "/api/bets", json={"legs": [leg_payload(over)], "stake_cents": 1_000}, headers=auth_headers
    )
    assert placed.status_code == 201, placed.text
    leg = placed.json()["bet"]["legs"][0]
    assert (leg["market"], leg["participant"], leg["point"]) == (
        "player_pass_yds",
        over["participant"],
        over["point"],
    )

    # A prop is the one pick for its game in a parlay.
    spread = next(line for line in body["game"]["odds_lines"] if line["market"] == "spreads")
    same_game = client.post(
        "/api/bets",
        json={"legs": [leg_payload(over), leg_payload(spread)], "stake_cents": 1_000},
        headers=auth_headers,
    )
    assert same_game.status_code == 400

    # Until prop grading exists, a finished game leaves prop bets open instead of crashing.
    game.commence_time = datetime.now(UTC) - timedelta(hours=4)
    game.completed, game.home_score, game.away_score = True, 24, 17
    db.commit()
    assert client.get("/api/bets?state=settled", headers=auth_headers).json() == []
    bet = db.scalars(select(Bet)).one()
    assert bet.status == BetStatus.PENDING
