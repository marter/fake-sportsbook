import uuid
from datetime import datetime

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
