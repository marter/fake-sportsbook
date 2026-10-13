import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.schemas.bet import BetRead


class AdminUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    display_name: str
    balance_cents: int
    is_admin: bool
    email_verified: bool
    created_at: datetime


class BalanceAdjustment(BaseModel):
    """Give exactly one: `amount_cents` to add/subtract, or `set_balance_cents` for a target."""

    amount_cents: int | None = None
    set_balance_cents: int | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def exactly_one(self) -> "BalanceAdjustment":
        if (self.amount_cents is None) == (self.set_balance_cents is None):
            raise ValueError("Provide exactly one of amount_cents or set_balance_cents")
        if self.amount_cents == 0:
            raise ValueError("amount_cents can't be 0")
        return self


class AdminUserBets(BaseModel):
    user: AdminUserRead
    bets: list[BetRead]


class VoidBet(BaseModel):
    note: str | None = Field(default=None, max_length=200)


class StuckBet(BaseModel):
    bet_id: uuid.UUID
    user_id: uuid.UUID
    display_name: str
    stake_cents: int


class StuckGame(BaseModel):
    game_id: uuid.UUID
    home_team: str
    away_team: str
    commence_time: datetime
    open_bets: list[StuckBet]


class PropToGrade(BaseModel):
    leg_id: uuid.UUID
    bet_id: uuid.UUID
    user_id: uuid.UUID
    display_name: str
    market: str
    outcome: str
    participant: str
    point: float | None
    price_american: int
    home_team: str
    away_team: str
    commence_time: datetime
    home_score: int | None
    away_score: int | None


class GradeLeg(BaseModel):
    result: Literal["won", "lost", "push", "void"]
