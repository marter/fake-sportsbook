import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.game import Game, Market


class BetStatus(enum.StrEnum):
    PENDING = "pending"
    WON = "won"
    LOST = "lost"
    PUSH = "push"  # stake refunded
    VOID = "void"  # cancelled, stake refunded


class LegResult(enum.StrEnum):
    PENDING = "pending"
    WON = "won"
    LOST = "lost"
    PUSH = "push"


class Bet(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A wager. Single bets have one leg; parlays (later) will have several."""

    __tablename__ = "bets"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    stake_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # Stake plus winnings if every leg wins, fixed at placement.
    potential_payout_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[BetStatus] = mapped_column(
        Enum(BetStatus, name="bet_status"), nullable=False, default=BetStatus.PENDING, index=True
    )
    # What was actually paid back on settlement (0 for a loss).
    payout_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    legs: Mapped[list["BetLeg"]] = relationship(
        back_populates="bet", cascade="all, delete-orphan", lazy="raise"
    )


class BetLeg(UUIDPrimaryKeyMixin, Base):
    """One selection, with the price and line locked in when the bet was placed."""

    __tablename__ = "bet_legs"

    bet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    game_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("games.id"), nullable=False, index=True
    )
    market: Mapped[Market] = mapped_column(Enum(Market, name="market"), nullable=False)
    outcome: Mapped[str] = mapped_column(String(100), nullable=False)
    price_american: Mapped[int] = mapped_column(Integer, nullable=False)
    point: Mapped[float | None] = mapped_column(Numeric(5, 1, asdecimal=False), nullable=True)
    result: Mapped[LegResult] = mapped_column(
        Enum(LegResult, name="leg_result"), nullable=False, default=LegResult.PENDING
    )

    bet: Mapped[Bet] = relationship(back_populates="legs", lazy="raise")
    game: Mapped[Game] = relationship(lazy="raise")
