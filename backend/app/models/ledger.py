import enum
import uuid

from sqlalchemy import BigInteger, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class LedgerKind(enum.StrEnum):
    SIGNUP_BONUS = "signup_bonus"
    BET_STAKE = "bet_stake"
    BET_PAYOUT = "bet_payout"
    BET_REFUND = "bet_refund"
    ADMIN_ADJUSTMENT = "admin_adjustment"


class LedgerEntry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Every change to a user's balance. The entries for a user always sum to balance_cents."""

    __tablename__ = "ledger_entries"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)  # negative = debit
    balance_after_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    kind: Mapped[LedgerKind] = mapped_column(Enum(LedgerKind, name="ledger_kind"), nullable=False)
    bet_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bets.id"), nullable=True, index=True
    )
    # For admin adjustments: which admin made it, and why.
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
