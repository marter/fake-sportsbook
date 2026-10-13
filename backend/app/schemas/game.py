import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class OddsLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    market: str
    participant: str
    outcome: str
    price_american: int
    point: float | None


class GameRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    home_team: str
    away_team: str
    commence_time: datetime
    # Game-level lines only (moneyline, spread, total); props come from /games/{id}/props.
    odds_lines: list[OddsLineRead]
    # Whether this league offers player props (they open ~2 days before kickoff).
    has_props: bool = False


class PropMarketRead(BaseModel):
    key: str
    label: str
    short: str
    kind: str


class GamePropsResponse(BaseModel):
    game: GameRead
    # Why props aren't available right now ("open about two days before kickoff"), if so.
    unavailable_reason: str | None
    markets: list[PropMarketRead]
    lines: list[OddsLineRead]


class SportRead(BaseModel):
    slug: str
    name: str
    in_season: bool
    upcoming_games: int
    spread_label: str
    season_note: str


class GamesResponse(BaseModel):
    odds_updated_at: datetime | None
    games: list[GameRead]
