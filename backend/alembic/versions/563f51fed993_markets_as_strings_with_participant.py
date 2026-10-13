"""markets as strings with participant

Revision ID: 563f51fed993
Revises: 044ac9ec9e67
Create Date: 2026-10-10 12:37:46.756175

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '563f51fed993'
down_revision: Union[str, Sequence[str], None] = '044ac9ec9e67'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Store markets as plain lowercase strings and add a participant (player) column, so
    player-prop markets fit alongside the game markets."""
    for table in ("odds_lines", "bet_legs"):
        # The enum stored member names ("H2H"); the API and code use values ("h2h").
        op.alter_column(
            table,
            "market",
            type_=sa.String(40),
            existing_nullable=False,
            postgresql_using="lower(market::text)",
        )
        op.add_column(
            table,
            sa.Column("participant", sa.String(100), nullable=False, server_default=""),
        )
    op.execute("DROP TYPE market")
    op.drop_constraint("uq_odds_line_game_market_outcome", "odds_lines", type_="unique")
    op.create_unique_constraint(
        "uq_odds_line_game_market_outcome",
        "odds_lines",
        ["game_id", "market", "outcome", "participant"],
    )


def downgrade() -> None:
    """Back to the three-value enum. Fails if any player-prop rows exist (delete them first)."""
    op.drop_constraint("uq_odds_line_game_market_outcome", "odds_lines", type_="unique")
    op.create_unique_constraint(
        "uq_odds_line_game_market_outcome", "odds_lines", ["game_id", "market", "outcome"]
    )
    op.execute("CREATE TYPE market AS ENUM ('H2H', 'SPREADS', 'TOTALS')")
    for table in ("odds_lines", "bet_legs"):
        op.drop_column(table, "participant")
        op.alter_column(
            table,
            "market",
            type_=sa.Enum("H2H", "SPREADS", "TOTALS", name="market"),
            existing_nullable=False,
            postgresql_using="upper(market)::market",
        )
