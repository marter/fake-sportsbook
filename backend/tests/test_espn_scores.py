from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.game import Game, OddsFetch
from app.services import espn, odds, settlement
from app.sports import BY_SLUG
from tests.test_settlement import place, start_game

NBA = BY_SLUG["nba"]


def espn_event(home: str, away: str, start: datetime, home_score: int, away_score: int, *,
               completed: bool = True) -> dict[str, Any]:
    return {
        "id": "401",
        "date": start.strftime("%Y-%m-%dT%H:%MZ"),
        "status": {"type": {"completed": completed}},
        "competitions": [
            {
                "competitors": [
                    {"homeAway": "home", "team": {"displayName": home}, "score": str(home_score)},
                    {"homeAway": "away", "team": {"displayName": away}, "score": str(away_score)},
                ]
            }
        ],
    }


def fake_scoreboard(monkeypatch: pytest.MonkeyPatch, events: list[dict[str, Any]]) -> list[str]:
    """ESPN answers every date with `events`. Returns the dates asked for."""
    asked: list[str] = []

    def fake(path: str, params: dict[str, str]) -> dict[str, Any]:
        assert path.endswith("/scoreboard")
        asked.append(params["dates"])
        return {"events": events}

    monkeypatch.setattr(espn, "fetch_espn", fake)
    return asked


def nba_game(home: str = "Los Angeles Clippers", away: str = "Boston Celtics",
             start: datetime = datetime(2026, 11, 1, 23, 30, tzinfo=UTC)) -> Game:
    return Game(external_id="odds-1", sport_key=NBA.api_key, home_team=home, away_team=away,
                commence_time=start)


def test_final_scores_maps_team_names_and_our_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    game = nba_game()
    asked = fake_scoreboard(
        monkeypatch, [espn_event("LA Clippers", "Boston Celtics", game.commence_time, 101, 99)]
    )
    events, unlisted = espn.final_scores(NBA, [game])
    assert unlisted == []
    assert events == [
        {
            "id": "odds-1",
            "completed": True,
            "scores": [
                {"name": "Los Angeles Clippers", "score": "101"},
                {"name": "Boston Celtics", "score": "99"},
            ],
        }
    ]
    assert asked == ["20261101"]  # 6:30pm ET; neighboring days only if needed


def test_final_scores_picks_the_right_half_of_a_doubleheader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mlb = BY_SLUG["mlb"]
    first = datetime(2026, 9, 12, 17, 5, tzinfo=UTC)
    second = first + timedelta(hours=5)
    fake_scoreboard(
        monkeypatch,
        [
            espn_event("New York Yankees", "Boston Red Sox", first, 3, 2),
            espn_event("New York Yankees", "Boston Red Sox", second, 1, 7),
        ],
    )
    game = Game(external_id="nightcap", sport_key=mlb.api_key, home_team="New York Yankees",
                away_team="Boston Red Sox", commence_time=second)
    events, _ = espn.final_scores(mlb, [game])
    assert events[0]["scores"][0] == {"name": "New York Yankees", "score": "1"}

    moved = Game(external_id="moved", sport_key=mlb.api_key, home_team="New York Yankees",
                 away_team="Boston Red Sox", commence_time=second + timedelta(hours=4))
    assert espn.final_scores(mlb, [moved]) == ([], [moved])  # nothing within 3 hours


def test_final_scores_skips_unfinished_and_reports_unlisted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playing = nba_game()
    missing = nba_game(home="Miami Heat", away="Utah Jazz")
    fake_scoreboard(
        monkeypatch,
        [espn_event("LA Clippers", "Boston Celtics", playing.commence_time, 50, 48,
                    completed=False)],
    )
    assert espn.final_scores(NBA, [playing, missing]) == ([], [missing])


def test_final_scores_raises_on_unexpected_shapes(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_scoreboard(monkeypatch, [{"id": "401", "competitions": []}])
    with pytest.raises(espn.EspnError):
        espn.final_scores(NBA, [nba_game()])


# --- Settlement with ESPN ----------------------------------------------------------------


def no_api_scores(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    def fake(sport):
        calls.append(sport.slug)
        return [], 400

    monkeypatch.setattr(odds, "fetch_scores_from_api", fake)
    return calls


def settle_from_espn(client, db, auth_headers, monkeypatch, *, completed=True):
    _, line, game = place(client, auth_headers, "h2h", 0, 1_000)
    db_game = start_game(db, game["id"])
    monkeypatch.setattr(get_settings(), "odds_api_key", "test-key")
    fake_scoreboard(
        monkeypatch,
        [espn_event(db_game.home_team, db_game.away_team, db_game.commence_time, 27, 13,
                    completed=completed)],
    )
    return line, db_game


def test_bets_settle_from_espn_without_spending_credits(
    client: TestClient, db: Session, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    line, game = settle_from_espn(client, db, auth_headers, monkeypatch)
    api_calls = no_api_scores(monkeypatch)

    settled = client.get("/api/bets?state=settled", headers=auth_headers).json()
    assert settled[0]["status"] == ("won" if line["outcome"] == game.home_team else "lost")
    assert api_calls == []
    fetch = db.scalars(select(OddsFetch).where(OddsFetch.kind == "scores")).one()
    assert (fetch.source, fetch.requests_remaining) == ("espn", None)


def test_espn_keeps_settling_when_credits_are_low(
    client: TestClient, db: Session, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    settle_from_espn(client, db, auth_headers, monkeypatch)
    db.add(OddsFetch(sport_key="americanfootball_nfl", kind="odds", fetched_at=datetime.now(UTC),
                     source="api", event_count=1, requests_remaining=10))
    db.commit()
    assert len(client.get("/api/bets?state=settled", headers=auth_headers).json()) == 1


def test_game_not_final_on_espn_waits_without_fallback(
    client: TestClient, db: Session, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    settle_from_espn(client, db, auth_headers, monkeypatch, completed=False)
    api_calls = no_api_scores(monkeypatch)
    assert len(client.get("/api/bets?state=open", headers=auth_headers).json()) == 1
    assert api_calls == []  # postponed or still playing: ESPN found it, so no paid call


def test_espn_down_falls_back_to_the_odds_api_at_most_every_few_hours(
    db: Session, client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, game = place(client, auth_headers, "h2h", 0, 1_000)
    start_game(db, game["id"])
    monkeypatch.setattr(get_settings(), "odds_api_key", "test-key")
    api_calls = no_api_scores(monkeypatch)  # ESPN is offline in tests by default

    settlement.settle_if_due(db)
    assert api_calls == ["nfl"]
    # Half an hour later ESPN is retried (throttle passed), but the paid fallback isn't.
    for fetch in db.scalars(select(OddsFetch)).all():
        fetch.fetched_at -= timedelta(minutes=31)
    db.commit()
    settlement.settle_if_due(db)
    assert api_calls == ["nfl"]
    scores = db.scalars(select(OddsFetch.source).where(OddsFetch.kind == "scores")).all()
    assert sorted(scores) == ["api", "espn", "espn"]


@pytest.mark.parametrize(("minutes_ago", "expect_fallback"), [(240, False), (600, True)])
def test_game_espn_doesnt_list_falls_back_once_overdue(
    db: Session,
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    minutes_ago: int,
    expect_fallback: bool,
) -> None:
    _, _, game = place(client, auth_headers, "h2h", 0, 1_000)
    start_game(db, game["id"], minutes_ago=minutes_ago)
    monkeypatch.setattr(get_settings(), "odds_api_key", "test-key")
    fake_scoreboard(monkeypatch, [])  # e.g. a team name we don't map
    api_calls = no_api_scores(monkeypatch)
    settlement.settle_if_due(db)
    # NFL games run ~3h; the fallback waits 3 more hours (a 4h-old game doesn't qualify).
    assert api_calls == (["nfl"] if expect_fallback else [])


def test_odds_api_source_setting_skips_espn(
    db: Session, client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, game = place(client, auth_headers, "h2h", 0, 1_000)
    start_game(db, game["id"])
    monkeypatch.setattr(get_settings(), "odds_api_key", "test-key")
    monkeypatch.setattr(get_settings(), "scores_source", "odds_api")

    def espn_must_not_be_called(path, params):
        raise AssertionError("ESPN was called")

    monkeypatch.setattr(espn, "fetch_espn", espn_must_not_be_called)
    api_calls = no_api_scores(monkeypatch)
    settlement.settle_if_due(db)
    assert api_calls == ["nfl"]


def test_espn_request_errors_become_espn_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(espn.EspnError):  # the default test stub raises httpx.ConnectError
        espn.final_scores(NBA, [nba_game()])
