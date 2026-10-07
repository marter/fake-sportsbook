from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.bet import Bet, BetLeg, BetStatus
from app.models.game import Game, Market
from app.models.user import User


def register(client: TestClient, email: str, name: str) -> dict[str, str]:
    token = client.post(
        "/api/auth/register",
        json={"email": email, "password": "hunter22!", "display_name": name},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def add_bet(db: Session, email: str, game: Game, stake: int, status: BetStatus, payout: int | None):
    """Inserts a bet directly in a given state (placement and settlement are tested elsewhere)."""
    user = db.scalars(select(User).where(User.email == email)).one()
    db.add(
        Bet(
            user_id=user.id,
            stake_cents=stake,
            potential_payout_cents=stake * 2,
            status=status,
            payout_cents=payout,
            legs=[
                BetLeg(
                    game_id=game.id,
                    market=Market.H2H,
                    outcome=game.home_team,
                    price_american=100,
                )
            ],
        )
    )
    db.commit()


def make_game(db: Session, completed: bool = True) -> Game:
    game = Game(
        external_id=f"lb-game-{completed}",
        sport_key="americanfootball_nfl",
        home_team="Home Team",
        away_team="Away Team",
        commence_time=datetime.now(UTC) + (timedelta(0) if completed else timedelta(days=2)),
        completed=completed,
        home_score=21 if completed else None,
        away_score=14 if completed else None,
    )
    db.add(game)
    db.commit()
    return game


def test_leaderboard_ranks_by_settled_profit(client: TestClient, db: Session) -> None:
    ana = register(client, "ana@example.com", "Ana")
    register(client, "ben@example.com", "Ben")
    register(client, "cy@example.com", "Cy")
    register(client, "dee@example.com", "Dee")
    game = make_game(db)

    # Ana: won $10 profit, lost $5, pushed $3 -> +$5, 1-1-1
    add_bet(db, "ana@example.com", game, 1_000, BetStatus.WON, 2_000)
    add_bet(db, "ana@example.com", game, 500, BetStatus.LOST, 0)
    add_bet(db, "ana@example.com", game, 300, BetStatus.PUSH, 300)
    # Ben: one big win (+$20) and an open bet on an upcoming game that doesn't count yet
    add_bet(db, "ben@example.com", game, 2_000, BetStatus.WON, 4_000)
    add_bet(db, "ben@example.com", make_game(db, completed=False), 9_999, BetStatus.PENDING, None)
    # Cy: lost $10. Dee: no bets, but an admin gave them a fortune (doesn't count).
    add_bet(db, "cy@example.com", game, 1_000, BetStatus.LOST, 0)
    dee = db.scalars(select(User).where(User.email == "dee@example.com")).one()
    dee.balance_cents += 100_000_000
    db.commit()

    board = client.get("/api/leaderboard", headers=ana).json()
    assert [(r["rank"], r["display_name"], r["profit_cents"]) for r in board] == [
        (1, "Ben", 2_000),
        (2, "Ana", 500),
        (3, "Dee", 0),
        (4, "Cy", -1_000),
    ]
    ana_row = board[1]
    assert (ana_row["wins"], ana_row["losses"], ana_row["pushes"]) == (1, 1, 1)
    assert ana_row["staked_cents"] == 1_800
    assert board[0]["open_bets"] == 1
    assert "email" not in board[0]


def test_ties_share_a_rank(client: TestClient, db: Session) -> None:
    headers = register(client, "ana@example.com", "Ana")
    register(client, "ben@example.com", "Ben")
    register(client, "cy@example.com", "Cy")
    game = make_game(db)
    add_bet(db, "ana@example.com", game, 1_000, BetStatus.WON, 2_000)
    add_bet(db, "ben@example.com", game, 1_000, BetStatus.WON, 2_000)

    board = client.get("/api/leaderboard", headers=headers).json()
    assert [(r["rank"], r["display_name"]) for r in board] == [(1, "Ana"), (1, "Ben"), (3, "Cy")]


def test_leaderboard_requires_auth(client: TestClient) -> None:
    assert client.get("/api/leaderboard").status_code == 401
