from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.game import Game
from app.models.ledger import LedgerEntry
from app.models.user import User
from app.services.odds_math import payout_cents


@pytest.mark.parametrize(
    ("stake", "price", "expected"),
    [
        (10_000, 150, 25_000),  # $100 at +150 pays $250
        (11_000, -110, 21_000),  # $110 at -110 pays $210
        (1_000, -110, 1_909),  # $10 at -110 wins $9.09 (rounded down)
        (100, 100, 200),  # even money
        (2_500, -250, 3_500),
    ],
)
def test_payout_cents(stake: int, price: int, expected: int) -> None:
    assert payout_cents(stake, price) == expected


def test_payout_rejects_invalid_odds() -> None:
    with pytest.raises(ValueError):
        payout_cents(1_000, 50)


def first_line(client: TestClient, headers: dict[str, str], market: str = "h2h") -> dict[str, Any]:
    game = client.get("/api/games", headers=headers).json()["games"][0]
    line = next(line for line in game["odds_lines"] if line["market"] == market)
    return {**line, "game_id": game["id"]}


def leg_payload(line: dict[str, Any]) -> dict[str, Any]:
    return {
        "odds_line_id": line["id"],
        "expected_price_american": line["price_american"],
        "expected_point": line["point"],
    }


def bet_payload(line: dict[str, Any], stake_cents: int = 1_000) -> dict[str, Any]:
    """A single bet on one line."""
    return {"legs": [leg_payload(line)], "stake_cents": stake_cents}


def balance(client: TestClient, headers: dict[str, str]) -> int:
    return client.get("/api/auth/me", headers=headers).json()["balance_cents"]


def test_place_bet_debits_balance_and_records_ledger(
    client: TestClient, db: Session, auth_headers: dict[str, str]
) -> None:
    line = first_line(client, auth_headers, "spreads")
    response = client.post("/api/bets", json=bet_payload(line, 2_500), headers=auth_headers)
    assert response.status_code == 201, response.text
    body = response.json()

    assert body["balance_cents"] == 100_000 - 2_500
    assert balance(client, auth_headers) == 97_500
    bet = body["bet"]
    assert bet["status"] == "pending"
    assert bet["potential_payout_cents"] == payout_cents(2_500, line["price_american"])
    leg = bet["legs"][0]
    assert leg["market"] == "spreads"
    assert (leg["outcome"], leg["point"]) == (line["outcome"], line["point"])
    assert leg["game"]["id"] == line["game_id"]

    ledger = client.get("/api/wallet/ledger", headers=auth_headers).json()
    assert [e["kind"] for e in ledger] == ["bet_stake", "signup_bonus"]
    assert ledger[0]["amount_cents"] == -2_500
    assert ledger[0]["balance_after_cents"] == 97_500
    user = db.scalars(select(User)).one()
    ledger_sum = db.scalar(
        select(func.sum(LedgerEntry.amount_cents)).where(LedgerEntry.user_id == user.id)
    )
    assert ledger_sum == user.balance_cents

    open_bets = client.get("/api/bets?state=open", headers=auth_headers).json()
    assert [b["id"] for b in open_bets] == [bet["id"]]
    assert client.get("/api/bets?state=settled", headers=auth_headers).json() == []


def test_stake_limits(client: TestClient, auth_headers: dict[str, str]) -> None:
    line = first_line(client, auth_headers)
    too_small = client.post("/api/bets", json=bet_payload(line, 99), headers=auth_headers)
    assert too_small.status_code == 422
    too_big = client.post("/api/bets", json=bet_payload(line, 100_001), headers=auth_headers)
    assert too_big.status_code == 400
    assert balance(client, auth_headers) == 100_000

    all_in = client.post("/api/bets", json=bet_payload(line, 100_000), headers=auth_headers)
    assert all_in.status_code == 201
    assert balance(client, auth_headers) == 0


def test_moved_line_is_rejected_with_new_price(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    line = first_line(client, auth_headers)
    stale = bet_payload(line)
    stale["legs"][0]["expected_price_american"] = line["price_american"] + 5
    response = client.post("/api/bets", json=stale, headers=auth_headers)
    assert response.status_code == 409
    [change] = response.json()["detail"]["changes"]
    assert change == {
        "odds_line_id": line["id"],
        "price_american": line["price_american"],
        "point": line["point"],
    }
    assert balance(client, auth_headers) == 100_000


def test_cannot_bet_on_started_game(
    client: TestClient, db: Session, auth_headers: dict[str, str]
) -> None:
    line = first_line(client, auth_headers)
    game = db.get(Game, line["game_id"])
    assert game is not None
    game.commence_time = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()

    response = client.post("/api/bets", json=bet_payload(line), headers=auth_headers)
    assert response.status_code == 400
    assert balance(client, auth_headers) == 100_000


def test_bets_are_private(client: TestClient, auth_headers: dict[str, str]) -> None:
    line = first_line(client, auth_headers)
    client.post("/api/bets", json=bet_payload(line), headers=auth_headers)

    other = client.post(
        "/api/auth/register",
        json={"email": "other@example.com", "password": "hunter22!", "display_name": "Other"},
    ).json()["access_token"]
    other_headers = {"Authorization": f"Bearer {other}"}
    assert client.get("/api/bets", headers=other_headers).json() == []
    assert len(client.get("/api/wallet/ledger", headers=other_headers).json()) == 1


def test_concurrent_bets_cannot_overspend(
    client: TestClient, engine, auth_headers: dict[str, str]
) -> None:
    """Five simultaneous all-in bets, each in its own DB session: exactly one may succeed."""
    from concurrent.futures import ThreadPoolExecutor

    from sqlalchemy.orm import sessionmaker

    from app.core.db import get_db
    from app.main import app

    line = first_line(client, auth_headers)
    Session_ = sessionmaker(bind=engine)

    def per_request_session():
        session = Session_()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = per_request_session

    def place(_: int) -> int:
        return client.post(
            "/api/bets", json=bet_payload(line, 100_000), headers=auth_headers
        ).status_code

    with ThreadPoolExecutor(max_workers=5) as pool:
        codes = sorted(pool.map(place, range(5)))

    assert codes == [201, 400, 400, 400, 400]
    assert balance(client, auth_headers) == 0


def test_cannot_bet_on_a_finished_game(
    client: TestClient, db: Session, auth_headers: dict[str, str]
) -> None:
    """Even if a finished game somehow shows a future kickoff, it can't be bet on or listed."""
    line = first_line(client, auth_headers)
    game = db.get(Game, line["game_id"])
    assert game is not None
    game.completed, game.home_score, game.away_score = True, 21, 14
    db.commit()

    response = client.post("/api/bets", json=bet_payload(line), headers=auth_headers)
    assert response.status_code == 400
    listed = {g["id"] for g in client.get("/api/games", headers=auth_headers).json()["games"]}
    assert line["game_id"] not in listed
    assert balance(client, auth_headers) == 100_000
