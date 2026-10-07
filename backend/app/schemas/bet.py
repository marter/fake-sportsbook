import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.bet import BetStatus, LegResult
from app.models.game import Market
from app.models.ledger import LedgerKind

MIN_STAKE_CENTS = 100  # $1
MAX_LEGS = 8


class BetLegCreate(BaseModel):
    odds_line_id: uuid.UUID
    # The price/line the user saw. If the line has moved since, the bet is rejected with 409
    # so they can confirm the new one.
    expected_price_american: int
    expected_point: float | None = None


class BetCreate(BaseModel):
    """One leg is a single bet; two or more is a parlay (every leg must win)."""

    legs: list[BetLegCreate] = Field(min_length=1, max_length=MAX_LEGS)
    stake_cents: int = Field(ge=MIN_STAKE_CENTS)


class BetGame(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sport: str
    home_team: str
    away_team: str
    commence_time: datetime
    completed: bool
    home_score: int | None
    away_score: int | None


class BetLegRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    market: Market
    outcome: str
    price_american: int
    point: float | None
    result: LegResult
    game: BetGame


class BetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    stake_cents: int
    potential_payout_cents: int
    payout_cents: int | None
    status: BetStatus
    created_at: datetime
    settled_at: datetime | None
    legs: list[BetLegRead]


class PlaceBetResponse(BaseModel):
    bet: BetRead
    balance_cents: int


class LedgerEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    amount_cents: int
    balance_after_cents: int
    kind: LedgerKind
    bet_id: uuid.UUID | None
    note: str | None
    created_at: datetime
