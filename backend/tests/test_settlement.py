import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.db import get_db
from app.main import app
from app.models.bet import Bet, BetLeg, BetStatus, LegResult
from app.models.game import Game, Market, OddsFetch
from app.models.ledger import LedgerEntry, LedgerKind
from app.services import odds, settlement
from tests.test_bets import balance, bet_payload

H, A = "Home Team", "Away Team"


@pytest.mark.parametrize(
    ("market", "outcome", "point", "home", "away", "expected"),
    [
        # moneyline
        (Market.H2H, H, None, 24, 17, LegResult.WON),
        (Market.H2H, A, None, 24, 17, LegResult.LOST),
        (Market.H2H, A, None, 20, 20, LegResult.PUSH),  # NFL tie
        # spreads: home favored by 3.5
        (Market.SPREADS, H, -3.5, 24, 20, LegResult.WON),
        (Market.SPREADS, H, -3.5, 24, 21, LegResult.LOST),
        (Market.SPREADS, A, 3.5, 24, 21, LegResult.WON),  # underdog covers in a loss
        (Market.SPREADS, H, -3.0, 24, 21, LegResult.PUSH),
        (Market.SPREADS, A, 3.0, 24, 21, LegResult.PUSH),
        (Market.SPREADS, A, 6.5, 17, 20, LegResult.WON),  # underdog wins outright
        # totals
        (Market.TOTALS, "Over", 44.5, 24, 21, LegResult.WON),
        (Market.TOTALS, "Under", 44.5, 24, 21, LegResult.LOST),
        (Market.TOTALS, "Under", 45.0, 24, 21, LegResult.PUSH),
        (Market.TOTALS, "Over", 45.0, 24, 21, LegResult.PUSH),
        (Market.TOTALS, "Under", 47.5, 24, 21, LegResult.WON),
    ],
)
def test_grade_leg(
    market: Market, outcome: str, point: float | None, home: int, away: int, expected: LegResult
) -> None:
    assert settlement.grade_leg(market, outcome, point, H, A, home, away) == expected


def test_grade_leg_rejects_unknown_team() -> None:
    with pytest.raises(ValueError):
        settlement.grade_leg(Market.H2H, "Someone Else", None, H, A, 1, 0)


# --- End-to-end ----------------------------------------------------------------------------


def start_game(db: Session, game_id: str, minutes_ago: int = 240) -> Game:
    game = db.get(Game, game_id)
    assert game is not None
    game.commence_time = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    db.commit()
    return game


def final_score(monkeypatch: pytest.MonkeyPatch, home: int, away: int) -> list[int]:
    """Makes fixture-mode scoring return this result. Returns a list that counts fetches."""
    calls: list[int] = []

    def fake(games: list[Game]) -> list[dict[str, Any]]:
        calls.append(1)
        return [
            {
                "id": g.external_id,
                "completed": True,
                "scores": [
                    {"name": g.home_team, "score": str(home)},
                    {"name": g.away_team, "score": str(away)},
                ],
            }
            for g in games
        ]

    monkeypatch.setattr(settlement, "fixture_scores", fake)
    return calls


def ledger_kinds(client: TestClient, headers: dict[str, str]) -> list[str]:
    return [e["kind"] for e in client.get("/api/wallet/ledger", headers=headers).json()]


def place(client: TestClient, headers: dict[str, str], market: str, side: int, stake: int):
    """Places a bet on the first game's `market`, choosing line `side` (0 or 1)."""
    game = client.get("/api/games", headers=headers).json()["games"][0]
    lines = [line for line in game["odds_lines"] if line["market"] == market]
    line = {**lines[side], "game_id": game["id"]}
    response = client.post("/api/bets", json=bet_payload(line, stake), headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["bet"], line, game


def test_winning_bet_is_paid(
    client: TestClient, db: Session, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    bet, line, game = place(client, auth_headers, "h2h", 0, 10_000)
    start_game(db, game["id"])
    winner_is_home = line["outcome"] == game["home_team"]
    final_score(monkeypatch, 30 if winner_is_home else 10, 10 if winner_is_home else 30)

    assert client.get("/api/bets?state=open", headers=auth_headers).json() == []
    settled = client.get("/api/bets?state=settled", headers=auth_headers).json()
    assert [b["id"] for b in settled] == [bet["id"]]
    assert settled[0]["status"] == "won"
    assert settled[0]["payout_cents"] == bet["potential_payout_cents"]
    assert settled[0]["legs"][0]["result"] == "won"
    assert settled[0]["legs"][0]["game"]["completed"] is True

    assert balance(client, auth_headers) == 100_000 - 10_000 + bet["potential_payout_cents"]
    assert ledger_kinds(client, auth_headers) == ["bet_payout", "bet_stake", "signup_bonus"]


def test_losing_bet_pays_nothing(
    client: TestClient, db: Session, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    bet, line, game = place(client, auth_headers, "h2h", 0, 10_000)
    start_game(db, game["id"])
    picked_home = line["outcome"] == game["home_team"]
    final_score(monkeypatch, 10 if picked_home else 30, 30 if picked_home else 10)

    settled = client.get("/api/bets?state=settled", headers=auth_headers).json()
    assert (settled[0]["status"], settled[0]["payout_cents"]) == ("lost", 0)
    assert balance(client, auth_headers) == 90_000
    assert ledger_kinds(client, auth_headers) == ["bet_stake", "signup_bonus"]


def test_push_refunds_stake(
    client: TestClient, db: Session, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    bet, line, game = place(client, auth_headers, "totals", 0, 5_000)
    start_game(db, game["id"])
    total = int(line["point"]) if float(line["point"]).is_integer() else None
    if total is None:  # half-point total can't push; force a whole-number line
        db.execute(update(BetLeg).values(point=44.0))
        db.commit()
        total = 44
    final_score(monkeypatch, total - 20, 20)

    settled = client.get("/api/bets?state=settled", headers=auth_headers).json()
    assert (settled[0]["status"], settled[0]["payout_cents"]) == ("push", 5_000)
    assert balance(client, auth_headers) == 100_000
    assert ledger_kinds(client, auth_headers)[0] == "bet_refund"


def test_nothing_fetched_until_game_should_be_over(
    client: TestClient, db: Session, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, game = place(client, auth_headers, "h2h", 0, 1_000)
    start_game(db, game["id"], minutes_ago=60)
    calls = final_score(monkeypatch, 20, 10)

    client.get("/api/bets", headers=auth_headers)
    client.get("/api/games", headers=auth_headers)
    assert calls == []
    score_fetches = select(func.count()).select_from(OddsFetch).where(OddsFetch.kind == "scores")
    assert db.scalar(score_fetches) == 0


def test_scores_fetch_is_throttled_while_game_unfinished(
    client: TestClient, db: Session, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, game = place(client, auth_headers, "h2h", 0, 1_000)
    start_game(db, game["id"])
    calls: list[int] = []

    def still_playing(games: list[Game]) -> list[dict[str, Any]]:
        calls.append(1)
        return [{"id": g.external_id, "completed": False, "scores": None} for g in games]

    monkeypatch.setattr(settlement, "fixture_scores", still_playing)
    for _ in range(3):
        client.get("/api/bets", headers=auth_headers)
    assert len(calls) == 1

    db.execute(
        update(OddsFetch)
        .where(OddsFetch.kind == "scores")
        .values(fetched_at=datetime.now(UTC) - timedelta(minutes=31))
    )
    db.commit()
    client.get("/api/bets", headers=auth_headers)
    assert len(calls) == 2
    # The odds cache is untouched by score fetches.
    assert odds.latest_fetch(db, get_settings().odds_sport_key).kind == "odds"


def test_api_failure_leaves_bets_open(
    client: TestClient, db: Session, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, game = place(client, auth_headers, "h2h", 0, 1_000)
    start_game(db, game["id"])
    monkeypatch.setattr(get_settings(), "odds_api_key", "test-key")

    def down():
        raise httpx.ConnectError("down")

    monkeypatch.setattr(odds, "fetch_scores_from_api", down)
    response = client.get("/api/bets?state=open", headers=auth_headers)
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_api_mode_uses_scores_endpoint(
    client: TestClient, db: Session, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, line, game = place(client, auth_headers, "h2h", 0, 1_000)
    db_game = start_game(db, game["id"])
    monkeypatch.setattr(get_settings(), "odds_api_key", "test-key")
    events = [
        {
            "id": db_game.external_id,
            "completed": True,
            "scores": [
                {"name": db_game.home_team, "score": "27"},
                {"name": db_game.away_team, "score": "13"},
            ],
        },
        {"id": "someone-elses-game", "completed": True, "scores": []},
    ]
    monkeypatch.setattr(odds, "fetch_scores_from_api", lambda: (events, 450))

    settled = client.get("/api/bets?state=settled", headers=auth_headers).json()
    expected = "won" if line["outcome"] == db_game.home_team else "lost"
    assert settled[0]["status"] == expected
    fetch = db.scalars(select(OddsFetch).where(OddsFetch.kind == "scores")).one()
    assert (fetch.source, fetch.requests_remaining) == ("api", 450)


def test_bet_on_already_final_game_still_settles(
    client: TestClient, db: Session, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, game = place(client, auth_headers, "h2h", 0, 1_000)
    db_game = start_game(db, game["id"])
    db_game.completed, db_game.home_score, db_game.away_score = True, 21, 14
    db.commit()
    calls = final_score(monkeypatch, 0, 0)

    settled = client.get("/api/bets?state=settled", headers=auth_headers).json()
    assert len(settled) == 1
    assert calls == []  # nothing left to fetch


def test_concurrent_settlement_pays_once(
    client: TestClient,
    db: Session,
    engine,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Five simultaneous page loads on separate DB sessions: the bet is paid exactly once.

    The game is already final, so no request writes to the games table, and only the
    settlement locks (not an incidental row lock on the game) can prevent a double payout.
    """
    bet, line, game = place(client, auth_headers, "h2h", 0, 10_000)
    db_game = start_game(db, game["id"])
    home_won = line["outcome"] == game["home_team"]
    db_game.completed = True
    db_game.home_score, db_game.away_score = (30, 10) if home_won else (10, 30)
    db.commit()

    # Slow grading down so all five requests are mid-settlement at once; without the locks,
    # each would pay the bet.
    real_grade = settlement.grade_leg

    def slow_grade(*args: Any) -> LegResult:
        time.sleep(0.2)
        return real_grade(*args)

    monkeypatch.setattr(settlement, "grade_leg", slow_grade)

    Session_ = sessionmaker(bind=engine)

    def per_request_session():
        session = Session_()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = per_request_session
    with ThreadPoolExecutor(max_workers=5) as pool:
        codes = list(
            pool.map(lambda _: client.get("/api/bets", headers=auth_headers).status_code, range(5))
        )
    assert codes == [200] * 5

    with Session_() as fresh:
        payouts = fresh.scalar(
            select(func.count())
            .select_from(LedgerEntry)
            .where(LedgerEntry.kind == LedgerKind.BET_PAYOUT)
        )
        assert payouts == 1
        assert fresh.get(Bet, bet["id"]).status == BetStatus.WON
