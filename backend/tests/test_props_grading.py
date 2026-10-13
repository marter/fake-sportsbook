import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.bet import Bet, BetStatus, LegResult
from app.models.game import Game, OddsLine
from app.models.user import User
from app.services import props_grading, settlement
from app.services.odds_math import parlay_payout_cents, payout_cents
from app.services.props_grading import grade_prop, normalize_name, parse_box_score

FIXTURES = Path(__file__).parent / "fixtures"
SCOREBOARD = json.loads((FIXTURES / "espn_nfl_scoreboard_20261004.json").read_text())
SUMMARY = json.loads((FIXTURES / "espn_nfl_summary_colts_commanders.json").read_text())
ESPN_EVENT = "401872965"  # Indianapolis Colts at Washington Commanders, Oct 4 2026 (IND 30-13)


def test_normalize_name() -> None:
    assert normalize_name("Marvin Harrison Jr.") == normalize_name("marvin harrison")
    assert normalize_name("A.J. Brown") == normalize_name("AJ Brown")
    assert normalize_name("Kenneth Walker III") == "kenneth walker"
    assert normalize_name("Amon-Ra St. Brown") == "amon ra st brown"


def test_parse_real_box_score() -> None:
    box = parse_box_score(SUMMARY)
    assert box.stat("player_pass_yds", "Daniel Jones") == 143
    assert box.stat("player_anytime_td", "Jonathan Taylor") == 2  # two rushing TDs
    assert box.stat("player_anytime_td", "Daniel Jones") == 1  # a rushing TD; passing doesn't count
    assert box.stat("player_anytime_td", "Treylon Burks") == 1  # receiving TD
    assert box.stat("player_pass_yds", "Athan Kaliakmanis") == 186
    assert box.stat("player_pass_yds", "Patrick Mahomes") is None  # not in this game


@pytest.mark.parametrize(
    ("market", "outcome", "point", "stat", "expected"),
    [
        ("player_pass_yds", "Over", 150.5, 143, LegResult.LOST),
        ("player_pass_yds", "Under", 150.5, 143, LegResult.WON),
        ("player_pass_yds", "Over", 143.0, 143, LegResult.PUSH),
        ("player_pass_yds", "Under", 143.0, 143, LegResult.PUSH),
        ("player_pass_yds", "Over", 120.5, 0, LegResult.LOST),  # played, no passes
        ("player_anytime_td", "Yes", None, 2, LegResult.WON),
        ("player_anytime_td", "Yes", None, 0, LegResult.LOST),
        ("player_anytime_td", "Yes", None, None, LegResult.VOID),  # didn't play
        ("player_pass_yds", "Over", 250.5, None, LegResult.VOID),
    ],
)
def test_grade_prop(market, outcome, point, stat, expected) -> None:
    assert grade_prop(market, outcome, point, stat) == expected


def fake_espn(monkeypatch: pytest.MonkeyPatch, *, completed: bool = True) -> list[str]:
    calls: list[str] = []

    def fake(path: str, params: dict[str, str]) -> dict[str, Any]:
        calls.append(f"{path}?{params}")
        if path.endswith("/scoreboard"):
            # Answer for any date: tests move the game's kickoff to "a few hours ago".
            board = json.loads(json.dumps(SCOREBOARD))
            for event in board["events"]:
                event["status"]["type"]["completed"] = completed
            return board
        assert params == {"event": ESPN_EVENT}
        return SUMMARY

    monkeypatch.setattr(props_grading, "fetch_espn", fake)
    return calls


def colts_commanders(commence: str = "2026-10-04T17:00:00+00:00") -> Game:
    return Game(
        external_id="odds-colts-commanders",
        sport_key="americanfootball_nfl",
        home_team="Washington Commanders",
        away_team="Indianapolis Colts",
        commence_time=datetime.fromisoformat(commence),
    )


def test_find_espn_event(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_espn(monkeypatch)
    assert props_grading.find_espn_event(colts_commanders(), "football/nfl") == ESPN_EVENT
    # 8:20pm ET is already the next day in UTC; the Eastern date still matches.
    late = colts_commanders("2026-10-05T00:20:00+00:00")
    assert props_grading.find_espn_event(late, "football/nfl") == ESPN_EVENT
    other = colts_commanders()
    other.home_team = "Kansas City Chiefs"
    assert props_grading.find_espn_event(other, "football/nfl") is None


def test_espn_not_final_yet(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_espn(monkeypatch, completed=False)
    assert props_grading.find_espn_event(colts_commanders(), "football/nfl") is None


# --- End to end: bets placed on props, graded from the real box score ----------------------


def setup_game(db: Session) -> tuple[Game, dict[str, OddsLine]]:
    """The Colts-Commanders game with props, scheduled in the future so bets can be placed."""
    game = colts_commanders()
    game.commence_time = datetime.now(UTC) + timedelta(hours=6)
    db.add(game)
    db.flush()
    specs = {
        "jones_over": ("player_pass_yds", "Over", "Daniel Jones", -112, 150.5),
        "kaliakmanis_over": ("player_pass_yds", "Over", "Athan Kaliakmanis", -112, 175.5),
        "taylor_td": ("player_anytime_td", "Yes", "Jonathan Taylor", -150, None),
        "warren_td": ("player_anytime_td", "Yes", "Tyler Warren", 200, None),
        "mahomes_over": ("player_pass_yds", "Over", "Patrick Mahomes", -112, 250.5),
    }
    lines = {}
    for name, (market, outcome, player, price, point) in specs.items():
        line = OddsLine(
            game_id=game.id,
            market=market,
            outcome=outcome,
            participant=player,
            price_american=price,
            point=point,
            bookmaker="draftkings",
        )
        db.add(line)
        lines[name] = line
    db.commit()
    return game, lines


def bet(client: TestClient, headers: dict[str, str], lines: list[OddsLine], stake: int) -> dict:
    response = client.post(
        "/api/bets",
        json={
            "legs": [
                {
                    "odds_line_id": str(line.id),
                    "expected_price_american": line.price_american,
                    "expected_point": line.point,
                }
                for line in lines
            ],
            "stake_cents": stake,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["bet"]


def finish(db: Session, game: Game, hours_ago: float = 4) -> None:
    game.commence_time = datetime.now(UTC) - timedelta(hours=hours_ago)
    game.completed, game.home_score, game.away_score = True, 13, 30
    db.commit()


def status_of(db: Session, bet_id: str) -> tuple[BetStatus, int | None]:
    db.expire_all()
    row = db.get(Bet, bet_id)
    assert row is not None
    return row.status, row.payout_cents


def test_props_graded_and_paid(
    client: TestClient, db: Session, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    game, lines = setup_game(db)
    lost = bet(client, auth_headers, [lines["jones_over"]], 1_000)  # 143 yds: loses
    won = bet(client, auth_headers, [lines["kaliakmanis_over"]], 1_000)  # 186 yds: wins
    td = bet(client, auth_headers, [lines["taylor_td"]], 1_500)  # 2 TDs: wins
    no_td = bet(client, auth_headers, [lines["warren_td"]], 500)  # 0 TDs: loses
    dnp = bet(client, auth_headers, [lines["mahomes_over"]], 700)  # not in the game: void
    finish(db, game)

    # Page loads don't touch props; the worker/CLI grading pass does.
    client.get("/api/bets", headers=auth_headers)
    assert status_of(db, lost["id"])[0] == BetStatus.PENDING

    fake_espn(monkeypatch)
    settlement.grade_props_and_settle(db)
    assert status_of(db, lost["id"]) == (BetStatus.LOST, 0)
    assert status_of(db, won["id"]) == (BetStatus.WON, payout_cents(1_000, -112))
    assert status_of(db, td["id"]) == (BetStatus.WON, payout_cents(1_500, -150))
    assert status_of(db, no_td["id"]) == (BetStatus.LOST, 0)
    assert status_of(db, dnp["id"]) == (BetStatus.VOID, 700)

    user = db.scalars(select(User)).one()
    expected = (
        100_000 - 1_000 - 1_000 - 1_500 - 500 - 700
        + payout_cents(1_000, -112) + payout_cents(1_500, -150) + 700
    )
    assert user.balance_cents == expected


def test_parlay_with_a_voided_prop(
    client: TestClient, db: Session, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A voided leg drops out like a push. (Two legs from one game are only allowed here
    because the lines are inserted directly; it's the grading being tested.)"""
    game, lines = setup_game(db)
    other = Game(
        external_id="other-game",
        sport_key="americanfootball_nfl",
        home_team="Home",
        away_team="Away",
        commence_time=datetime.now(UTC) + timedelta(hours=6),
    )
    db.add(other)
    db.flush()
    other_line = OddsLine(
        game_id=other.id,
        market="h2h",
        outcome="Home",
        participant="",
        price_american=100,
        point=None,
        bookmaker="draftkings",
    )
    db.add(other_line)
    db.commit()
    parlay = bet(client, auth_headers, [lines["mahomes_over"], other_line], 1_000)
    finish(db, game)
    other.commence_time = datetime.now(UTC) - timedelta(hours=4)
    other.completed, other.home_score, other.away_score = True, 20, 10
    db.commit()

    fake_espn(monkeypatch)
    settlement.settle_if_due(db)  # grades the game leg (won)
    settlement.grade_props_and_settle(db)  # voids the prop and settles
    assert status_of(db, parlay["id"]) == (BetStatus.WON, parlay_payout_cents(1_000, [100]))


def test_espn_down_leaves_legs_for_admin(
    client: TestClient, db: Session, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    game, lines = setup_game(db)
    placed = bet(client, auth_headers, [lines["taylor_td"]], 1_000)
    finish(db, game, hours_ago=2)

    def down(path, params):
        raise httpx.ConnectError("espn down")

    monkeypatch.setattr(props_grading, "fetch_espn", down)
    settlement.grade_props_and_settle(db)
    assert status_of(db, placed["id"])[0] == BetStatus.PENDING

    user = db.scalars(select(User)).one()
    user.is_admin = True
    db.commit()
    # Not listed until automatic grading has had its 12-hour grace period.
    assert client.get("/api/admin/props-to-grade", headers=auth_headers).json() == []
    finish(db, game, hours_ago=16)
    [item] = client.get("/api/admin/props-to-grade", headers=auth_headers).json()
    assert (item["participant"], item["market"]) == ("Jonathan Taylor", "player_anytime_td")

    graded = client.post(
        f"/api/admin/legs/{item['leg_id']}/grade", json={"result": "won"}, headers=auth_headers
    )
    assert graded.status_code == 204
    assert status_of(db, placed["id"]) == (BetStatus.WON, payout_cents(1_000, -150))
    again = client.post(
        f"/api/admin/legs/{item['leg_id']}/grade", json={"result": "lost"}, headers=auth_headers
    )
    assert again.status_code == 400
    assert client.get("/api/admin/props-to-grade", headers=auth_headers).json() == []


def test_manual_grading_is_admin_only(
    client: TestClient, db: Session, auth_headers: dict[str, str]
) -> None:
    assert client.get("/api/admin/props-to-grade", headers=auth_headers).status_code == 403
    missing = "00000000-0000-0000-0000-000000000000"
    response = client.post(
        f"/api/admin/legs/{missing}/grade", json={"result": "won"}, headers=auth_headers
    )
    assert response.status_code == 403
