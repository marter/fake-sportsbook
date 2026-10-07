from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from app import worker
from app.core.config import get_settings
from app.models.bet import Bet, BetStatus
from app.models.game import OddsFetch, OddsLine
from app.services import odds
from tests.test_settlement import final_score, place, start_game


def score_fetch_count(db: Session) -> int:
    scores = select(func.count()).select_from(OddsFetch).where(OddsFetch.kind == "scores")
    return db.scalar(scores) or 0


def test_odds_changes_dont_affect_placed_bets(
    client: TestClient, db: Session, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    bet, line, game = place(client, auth_headers, "h2h", 0, 10_000)
    promised = bet["potential_payout_cents"]

    # The line moves a lot after the bet (e.g. the next daily refresh).
    db.execute(update(OddsLine).where(OddsLine.id == line["id"]).values(price_american=-900))
    db.commit()

    start_game(db, game["id"])
    home_won = line["outcome"] == game["home_team"]
    final_score(monkeypatch, 30 if home_won else 10, 10 if home_won else 30)
    settled = client.get("/api/bets?state=settled", headers=auth_headers).json()[0]
    assert settled["status"] == "won"
    assert settled["legs"][0]["price_american"] == line["price_american"]
    assert settled["payout_cents"] == promised


def test_worker_cycle_refreshes_odds_and_settles(
    client: TestClient,
    db: Session,
    engine,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(worker, "SessionLocal", sessionmaker(bind=engine))
    bet, line, game = place(client, auth_headers, "h2h", 0, 1_000)
    start_game(db, game["id"])
    final_score(monkeypatch, 20, 17)
    # Make the odds cache stale so the cycle refreshes it. The real feed has dropped the
    # finished game by then (fixture mode would instead move it back into the future).
    db.execute(update(OddsFetch).values(fetched_at=datetime.now(UTC) - timedelta(days=2)))
    db.commit()
    monkeypatch.setattr(odds, "load_fixture_events", lambda sport, now: [])

    worker.run_once()

    db.expire_all()
    assert db.get(Bet, bet["id"]).status != BetStatus.PENDING
    latest = odds.latest_fetch(db, "americanfootball_nfl")
    assert latest is not None and datetime.now(UTC) - latest.fetched_at < timedelta(minutes=1)


def test_worker_cycle_with_nothing_due_spends_nothing(
    db: Session, engine, client: TestClient, auth_headers: dict[str, str], monkeypatch
) -> None:
    monkeypatch.setattr(worker, "SessionLocal", sessionmaker(bind=engine))
    calls = final_score(monkeypatch, 1, 0)
    worker.run_once()  # first cycle loads each in-season sport's odds once
    in_season = db.scalar(select(func.count()).select_from(OddsFetch))
    worker.run_once()
    assert calls == []
    assert db.scalar(select(func.count()).select_from(OddsFetch)) == in_season
    assert in_season == 3  # sample data exists for NFL, NBA and MLB; WNBA counts as off-season


def test_gives_up_after_a_day_and_lists_game_for_admin(
    client: TestClient, db: Session, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    bet, _, game = place(client, auth_headers, "h2h", 0, 1_000)
    start_game(db, game["id"], minutes_ago=25 * 60)  # postponed: no final score after 25h
    calls = final_score(monkeypatch, 1, 0)

    client.get("/api/bets", headers=auth_headers)
    assert calls == []
    assert score_fetch_count(db) == 0

    me = db.scalars(select(Bet.user_id).where(Bet.id == bet["id"])).one()
    from app.models.user import User

    db.get(User, me).is_admin = True
    db.commit()
    stuck = client.get("/api/admin/stuck-games", headers=auth_headers).json()
    assert [g["game_id"] for g in stuck] == [game["id"]]
    assert [b["bet_id"] for b in stuck[0]["open_bets"]] == [bet["id"]]

    # Voiding the bet clears it from the list.
    client.post(f"/api/admin/bets/{bet['id']}/void", json={}, headers=auth_headers)
    assert client.get("/api/admin/stuck-games", headers=auth_headers).json() == []


def test_stuck_games_is_admin_only(client: TestClient, auth_headers: dict[str, str]) -> None:
    assert client.get("/api/admin/stuck-games", headers=auth_headers).status_code == 403


@pytest.mark.parametrize(("credits_left", "expect_fetch"), [(10, False), (200, True)])
def test_score_checks_pause_when_low_on_credits(
    client: TestClient,
    db: Session,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    credits_left: int,
    expect_fetch: bool,
) -> None:
    _, _, game = place(client, auth_headers, "h2h", 0, 1_000)
    start_game(db, game["id"])
    db.add(
        OddsFetch(
            sport_key="americanfootball_nfl",
            kind="odds",
            fetched_at=datetime.now(UTC),
            source="api",
            event_count=10,
            requests_remaining=credits_left,
        )
    )
    db.commit()
    monkeypatch.setattr(get_settings(), "odds_api_key", "test-key")
    calls: list[int] = []

    def fake_scores(sport):
        calls.append(1)
        return [], credits_left - 2

    monkeypatch.setattr(odds, "fetch_scores_from_api", fake_scores)
    client.get("/api/bets", headers=auth_headers)
    assert bool(calls) is expect_fetch
