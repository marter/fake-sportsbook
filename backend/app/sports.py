"""The leagues the sportsbook offers. Everything sport-specific lives here."""

from dataclasses import dataclass
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"


@dataclass(frozen=True)
class PropMarket:
    key: str  # The Odds API market key
    label: str  # "Passing yards"
    short: str  # "pass yds", used in bet labels like "Hurts Over 186.5 pass yds"
    kind: str  # "over_under" (Over/Under a line) or "yes" (a single Yes price, e.g. anytime TD)


# Each prop market costs 1 API credit per game fetched. On the free plan we offer two for the
# NFL; on a paid tier, add more here (e.g. player_rush_yds, player_reception_yds).
NFL_PROPS = (
    PropMarket("player_anytime_td", "Anytime touchdown", "anytime TD", "yes"),
    PropMarket("player_pass_yds", "Passing yards", "pass yds", "over_under"),
)


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
    # Player prop markets offered for this sport (empty: no props).
    prop_markets: tuple[PropMarket, ...] = ()

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
        prop_markets=NFL_PROPS,
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


def prop_market(key: str) -> PropMarket | None:
    for sport in SPORTS:
        for market in sport.prop_markets:
            if market.key == key:
                return market
    return None
