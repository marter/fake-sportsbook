from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(50), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    # Can view all users and adjust balances. Only granted from the server CLI
    # (python -m app.cli make-admin <email>), never through the API.
    is_admin: Mapped[bool] = mapped_column(default=False, server_default="false")
    # Play money, always in integer cents. Only change this inside a transaction that holds a
    # row lock (SELECT ... FOR UPDATE) and writes a matching ledger entry (phase 3).
    balance_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Null until the user clicks the link in their verification email.
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    @property
    def email_verified(self) -> bool:
        return self.email_verified_at is not None
