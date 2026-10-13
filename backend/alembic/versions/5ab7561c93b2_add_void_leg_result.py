"""add void leg result

Revision ID: 5ab7561c93b2
Revises: 5514d5a0db69
Create Date: 2026-10-13 14:40:00.780371

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5ab7561c93b2'
down_revision: Union[str, Sequence[str], None] = '5514d5a0db69'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """A leg can now be voided (e.g. a player prop whose player didn't play)."""
    op.execute("ALTER TYPE leg_result ADD VALUE IF NOT EXISTS 'VOID'")


def downgrade() -> None:
    """Postgres can't drop an enum value; voided legs become pushes (both refund the leg)."""
    op.execute("UPDATE bet_legs SET result = 'PUSH' WHERE result = 'VOID'")
