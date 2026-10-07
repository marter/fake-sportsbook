"""The leagues the sportsbook offers. Everything sport-specific lives here."""

from dataclasses import dataclass
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"


@dataclass(frozen=True)
class Sport:
    slug: str  # used in URLs and the API: /games/nba, ?sport=nba
    api_key: str  # The Odds API's sport key, also stored on Game.sport_key
    name: str
    # Start checking for a final score this long after kickoff.
    game_minutes: int
    # What the spread market is called in this sport.
    spread_label: str
    # Shown on the tab when the league is out of season.
    season_note: str

    @property
    def fixture_path(self) -> Path:
        return FIXTURES_DIR / f"{self.slug}_odds.json"


SPORTS: tuple[Sport, ...] = (
    Sport(
        slug="nfl",
        api_key="americanfootball_nfl",
        name="NFL",
        game_minutes=180,
        spread_label="Spread",
        season_note="The NFL season runs September to February.",
    ),
    Sport(
        slug="nba",
        api_key="basketball_nba",
        name="NBA",
        game_minutes=150,
        spread_label="Spread",
        season_note="The NBA season starts in late October.",
    ),
    Sport(
        slug="mlb",
        api_key="baseball_mlb",
        name="MLB",
        game_minutes=170,
        spread_label="Run line",
        season_note="The MLB season starts in late March.",
    ),
    Sport(
        slug="wnba",
        api_key="basketball_wnba",
        name="WNBA",
        game_minutes=140,
        spread_label="Spread",
        season_note="The WNBA season starts in May.",
    ),
)
BY_SLUG = {s.slug: s for s in SPORTS}
BY_API_KEY = {s.api_key: s for s in SPORTS}
