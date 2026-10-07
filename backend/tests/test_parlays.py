from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.bet import BetLeg, LegResult
from app.models.game import Game
from app.services.odds_math import parlay_payout_cents, payout_cents
from tests.test_bets import balance, leg_payload


def test_parlay_payout_math() -> None:
    # $10 on three picks at -150, -110, -110: 10 * 5/3 * 21/11 * 21/11 = $60.74
    assert parlay_payout_cents(1_000, [-150, -110, -110]) == 6_074
    assert parlay_payout_cents(1_000, [-110, -110, -150]) == 6_074  # order doesn't matter
    assert parlay_payout_cents(1_000, [100, 100]) == 4_000  # two even-money picks: 4x
    for stake, price in [(1_000, -110), (2_500, 150), (100, -250)]:
        assert parlay_payout_cents(stake, [price]) == payout_cents(stake, price)


def nfl_games(client: TestClient, headers: dict[str, str]) -> list[dict[str, Any]]:
    return client.get("/api/games?sport=nfl", headers=headers).json()["games"]


def h2h(game: dict[str, Any], team: str | None = None) -> dict[str, Any]:
    team = team or game["home_team"]
    line = next(
        x for x in game["odds_lines"] if x["market"] == "h2h" and x["outcome"] == team
    )
    return {**line, "game": game}


def place_parlay(client, headers, lines, stake=1_000):
    return client.post(
        "/api/bets",
        json={"legs": [leg_payload(line) for line in lines], "stake_cents": stake},
        headers=headers,
    )


def test_place_parlay(client: TestClient, auth_headers: dict[str, str]) -> None:
    games = nfl_games(client, auth_headers)
    picks = [h2h(g) for g in games[:3]]
    response = place_parlay(client, auth_headers, picks)
    assert response.status_code == 201, response.text
    bet = response.json()["bet"]
    assert len(bet["legs"]) == 3
    expected = parlay_payout_cents(1_000, [p["price_american"] for p in picks])
    assert bet["potential_payout_cents"] == expected
    assert balance(client, auth_headers) == 99_000


def test_parlay_rules(client: TestClient, db: Session, auth_headers: dict[str, str]) -> None:
    games = nfl_games(client, auth_headers)
    same_game = place_parlay(
        client, auth_headers, [h2h(games[0]), h2h(games[0], games[0]["away_team"])]
    )
    assert same_game.status_code == 400
    assert "one pick per game" in same_game.json()["detail"]

    too_many = place_parlay(client, auth_headers, [h2h(games[0])] * 9)
    assert too_many.status_code == 422

    moved = [h2h(g) for g in games[:3]]
    stale = {
        "legs": [leg_payload(line) for line in moved],
        "stake_cents": 1_000,
    }
    stale["legs"][1]["expected_price_american"] += 7
    conflict = client.post("/api/bets", json=stale, headers=auth_headers)
    assert conflict.status_code == 409
    assert [c["odds_line_id"] for c in conflict.json()["detail"]["changes"]] == [moved[1]["id"]]

    started = db.get(Game, games[2]["id"])
    assert started is not None
    started.commence_time = datetime.now(UTC) - timedelta(minutes=5)
    db.commit()
    late = place_parlay(client, auth_headers, [h2h(g) for g in games[:3]])
    assert late.status_code == 400
    assert "already started" in late.json()["detail"]
    assert balance(client, auth_headers) == 100_000


def finish(db: Session, game_id: str, home: int, away: int) -> None:
    game = db.get(Game, game_id)
    assert game is not None
    game.commence_time = datetime.now(UTC) - timedelta(hours=4)
    game.completed, game.home_score, game.away_score = True, home, away
    db.commit()


def settled(client: TestClient, headers: dict[str, str]) -> list[dict[str, Any]]:
    return client.get("/api/bets?state=settled", headers=headers).json()


def test_parlay_loses_as_soon_as_one_leg_loses(
    client: TestClient, db: Session, auth_headers: dict[str, str]
) -> None:
    games = nfl_games(client, auth_headers)
    bet = place_parlay(client, auth_headers, [h2h(g) for g in games[:3]]).json()["bet"]
    finish(db, games[0]["id"], home=10, away=20)  # first pick (home team) loses

    [result] = settled(client, auth_headers)
    assert (result["id"], result["status"], result["payout_cents"]) == (bet["id"], "lost", 0)
    results = [leg["result"] for leg in result["legs"]]
    assert results.count("lost") == 1 and results.count("pending") == 2
    assert balance(client, auth_headers) == 99_000


def test_parlay_waits_for_every_leg_then_pays(
    client: TestClient, db: Session, auth_headers: dict[str, str]
) -> None:
    games = nfl_games(client, auth_headers)
    picks = [h2h(g) for g in games[:3]]
    bet = place_parlay(client, auth_headers, picks).json()["bet"]

    finish(db, games[0]["id"], home=30, away=10)
    assert settled(client, auth_headers) == []
    first_leg = db.query(BetLeg).filter(BetLeg.game_id == games[0]["id"]).one()
    assert first_leg.result == LegResult.WON  # graded and saved while the parlay is open

    finish(db, games[1]["id"], home=24, away=17)
    finish(db, games[2]["id"], home=21, away=3)
    [result] = settled(client, auth_headers)
    assert result["status"] == "won"
    assert result["payout_cents"] == bet["potential_payout_cents"]
    assert balance(client, auth_headers) == 99_000 + bet["potential_payout_cents"]


def test_pushed_leg_drops_out(
    client: TestClient, db: Session, auth_headers: dict[str, str]
) -> None:
    games = nfl_games(client, auth_headers)
    picks = [h2h(g) for g in games[:3]]
    place_parlay(client, auth_headers, picks)
    finish(db, games[0]["id"], home=20, away=20)  # NFL tie: moneyline pushes
    finish(db, games[1]["id"], home=24, away=17)
    finish(db, games[2]["id"], home=21, away=3)

    [result] = settled(client, auth_headers)
    assert result["status"] == "won"
    expected = parlay_payout_cents(1_000, [p["price_american"] for p in picks[1:]])
    assert result["payout_cents"] == expected


@pytest.mark.parametrize("ties", [2, 3])
def test_all_or_all_but_one_pushed(
    client: TestClient, db: Session, auth_headers: dict[str, str], ties: int
) -> None:
    games = nfl_games(client, auth_headers)
    picks = [h2h(g) for g in games[:3]]
    place_parlay(client, auth_headers, picks)
    for i, game in enumerate(games[:3]):
        if i < ties:
            finish(db, game["id"], home=17, away=17)
        else:
            finish(db, game["id"], home=27, away=3)
    [result] = settled(client, auth_headers)
    if ties == 3:
        assert (result["status"], result["payout_cents"]) == ("push", 1_000)
    else:
        assert result["payout_cents"] == payout_cents(1_000, picks[2]["price_american"])
