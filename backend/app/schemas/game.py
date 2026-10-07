import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.game import Market


class OddsLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    market: Market
    outcome: str
    price_american: int
    point: float | None


class GameRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    home_team: str
    away_team: str
    commence_time: datetime
    odds_lines: list[OddsLineRead]


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
