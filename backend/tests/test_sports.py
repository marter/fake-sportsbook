from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.game import Game, OddsFetch
from app.services import odds, settlement
from app.sports import BY_SLUG
from tests.test_bets import bet_payload


def games(client: TestClient, headers: dict[str, str], sport: str) -> list[dict]:
    response = client.get(f"/api/games?sport={sport}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["games"]


def bet_on_first_game(client: TestClient, headers: dict[str, str], sport: str) -> dict:
    game = games(client, headers, sport)[0]
    line = next(line for line in game["odds_lines"] if line["market"] == "h2h")
    response = client.post("/api/bets", json=bet_payload(line, 1_000), headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["bet"]


def test_sports_list(client: TestClient, auth_headers: dict[str, str]) -> None:
    games(client, auth_headers, "nba")  # load NBA's odds so it has upcoming games
    sports = {s["slug"]: s for s in client.get("/api/sports", headers=auth_headers).json()}
    assert list(sports) == ["nfl", "nba", "mlb", "wnba"]
    assert {slug: s["in_season"] for slug, s in sports.items()} == {
        "nfl": True,
        "nba": True,
        "mlb": True,
        "wnba": False,  # no sample data, so off-season without an API key
    }
    assert sports["mlb"]["spread_label"] == "Run line"
    assert sports["nba"]["upcoming_games"] == 6
    assert "May" in sports["wnba"]["season_note"]


def test_games_are_per_sport(client: TestClient, auth_headers: dict[str, str]) -> None:
    nba = games(client, auth_headers, "nba")
    nfl = games(client, auth_headers, "nfl")
    assert len(nba) == 6 and len(nfl) == 8
    assert "Boston Celtics" in {g["home_team"] for g in nba}
    assert not {g["id"] for g in nba} & {g["id"] for g in nfl}
    assert games(client, auth_headers, "wnba") == []
    assert client.get("/api/games?sport=nhl", headers=auth_headers).status_code == 404


def test_off_season_sports_spend_no_credits(
    client: TestClient, db: Session, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "odds_api_key", "test-key")
    only_nfl = frozenset({"americanfootball_nfl"})
    monkeypatch.setattr(odds, "fetch_active_sport_keys", lambda: only_nfl)
    fetched: list[str] = []

    def fake_fetch(sport):
        fetched.append(sport.slug)
        return odds.load_fixture_events(sport, datetime.now(UTC)), 400

    monkeypatch.setattr(odds, "fetch_events_from_api", fake_fetch)
    assert games(client, auth_headers, "nba") == []
    assert len(games(client, auth_headers, "nfl")) == 8
    assert fetched == ["nfl"]


def test_in_season_list_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "odds_api_key", "test-key")
    calls: list[int] = []

    def fake_active():
        calls.append(1)
        return frozenset({"basketball_nba"})

    monkeypatch.setattr(odds, "fetch_active_sport_keys", fake_active)
    assert odds.is_active(BY_SLUG["nba"]) and not odds.is_active(BY_SLUG["mlb"])
    assert odds.is_active(BY_SLUG["nba"])
    assert calls == [1]


def test_bets_carry_their_sport(client: TestClient, auth_headers: dict[str, str]) -> None:
    bet = bet_on_first_game(client, auth_headers, "nba")
    assert bet["legs"][0]["game"]["sport"] == "nba"


def test_settlement_uses_each_sports_game_length_and_throttle(
    client: TestClient, db: Session, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    nfl_bet = bet_on_first_game(client, auth_headers, "nfl")
    nba_bet = bet_on_first_game(client, auth_headers, "nba")
    # Both kicked off 2h40m ago: an NBA game (~2.5h) should be over, an NFL game (~3h) not yet.
    for bet in (nfl_bet, nba_bet):
        game = db.get(Game, bet["legs"][0]["game"]["id"])
        assert game is not None
        game.commence_time = datetime.now(UTC) - timedelta(minutes=160)
    db.commit()

    fetched: list[str] = []
    real = settlement.fixture_scores

    def tracking(games_list):
        fetched.extend(settlement._sport_of(g).slug for g in games_list)
        return real(games_list)

    monkeypatch.setattr(settlement, "fixture_scores", tracking)
    client.get("/api/bets", headers=auth_headers)
    assert fetched == ["nba"]
    settled = client.get("/api/bets?state=settled", headers=auth_headers).json()
    settled_ids = {b["id"] for b in settled}
    assert nba_bet["id"] in settled_ids and nfl_bet["id"] not in settled_ids

    # 30 minutes later the NFL game is due too; NBA's recent fetch doesn't throttle NFL's.
    game = db.get(Game, nfl_bet["legs"][0]["game"]["id"])
    assert game is not None
    game.commence_time = datetime.now(UTC) - timedelta(minutes=190)
    db.commit()
    client.get("/api/bets", headers=auth_headers)
    assert fetched == ["nba", "nfl"]
    score_fetches = select(OddsFetch.sport_key).where(OddsFetch.kind == "scores")
    assert sorted(db.scalars(score_fetches).all()) == ["americanfootball_nfl", "basketball_nba"]


def test_fixture_scores_never_tie_outside_football(db: Session) -> None:
    for slug in ("nba", "mlb", "wnba"):
        for i in range(200):
            game = Game(
                external_id=f"{slug}-{i}",
                sport_key=BY_SLUG[slug].api_key,
                home_team="Home",
                away_team="Away",
                commence_time=datetime.now(UTC),
            )
            home, away = (int(s["score"]) for s in settlement.fixture_scores([game])[0]["scores"])
            assert home != away


def test_enabled_sports_setting_hides_a_league(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import Settings

    assert Settings(enabled_sports="nfl, NBA,mlb").enabled_sports == ["nfl", "nba", "mlb"]
    monkeypatch.setattr(get_settings(), "enabled_sports", ["nfl", "nba", "mlb"])
    slugs = [s["slug"] for s in client.get("/api/sports", headers=auth_headers).json()]
    assert slugs == ["nfl", "nba", "mlb"]
    assert client.get("/api/games?sport=wnba", headers=auth_headers).status_code == 404
