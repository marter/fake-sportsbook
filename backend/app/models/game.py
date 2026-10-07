import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class Market(enum.StrEnum):
    H2H = "h2h"  # moneyline
    SPREADS = "spreads"
    TOTALS = "totals"


class Game(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One game, keyed by The Odds API's event id."""

    __tablename__ = "games"

    external_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    sport_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    home_team: Mapped[str] = mapped_column(String(100), nullable=False)
    away_team: Mapped[str] = mapped_column(String(100), nullable=False)
    commence_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    completed: Mapped[bool] = mapped_column(default=False)
    home_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    odds_lines: Mapped[list["OddsLine"]] = relationship(
        back_populates="game", cascade="all, delete-orphan", lazy="raise"
    )


class OddsLine(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The current price for one outcome of one market, from the configured bookmaker."""

    __tablename__ = "odds_lines"
    __table_args__ = (
        UniqueConstraint("game_id", "market", "outcome", name="uq_odds_line_game_market_outcome"),
    )

    game_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True
    )
    market: Mapped[Market] = mapped_column(Enum(Market, name="market"), nullable=False)
    # A team name for h2h/spreads, "Over" or "Under" for totals.
    outcome: Mapped[str] = mapped_column(String(100), nullable=False)
    price_american: Mapped[int] = mapped_column(Integer, nullable=False)
    # Spread or total line; null for h2h.
    point: Mapped[float | None] = mapped_column(Numeric(5, 1, asdecimal=False), nullable=True)
    bookmaker: Mapped[str] = mapped_column(String(64), nullable=False)

    game: Mapped[Game] = relationship(back_populates="odds_lines", lazy="raise")


class OddsFetch(UUIDPrimaryKeyMixin, Base):
    """One call to The Odds API (or fixture load). The latest row per sport and kind drives
    caching: the weekly odds refresh and the scores throttle each look only at their own kind.
    """

    __tablename__ = "odds_fetches"

    sport_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(  # "odds" | "scores"
        String(16), nullable=False, default="odds", server_default="odds"
    )
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)  # "api" | "fixture"
    event_count: Mapped[int] = mapped_column(Integer, nullable=False)
    requests_remaining: Mapped[int | None] = mapped_column(Integer, nullable=True)
