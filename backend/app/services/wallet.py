"""Balance changes. Every one goes through `apply`, so the ledger always matches the balance."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ledger import LedgerEntry, LedgerKind
from app.models.user import User


def lock_user(db: Session, user_id: uuid.UUID) -> User:
    """Re-reads the user with a row lock, held until the transaction ends.

    Anything that reads and then changes balance_cents must hold this lock, or two
    concurrent requests could both spend the same money.
    """
    return db.scalars(
        select(User).where(User.id == user_id).with_for_update().execution_options(
            populate_existing=True
        )
    ).one()


def apply(
    db: Session,
    user: User,
    amount_cents: int,
    kind: LedgerKind,
    bet_id: uuid.UUID | None = None,
    created_by_id: uuid.UUID | None = None,
    note: str | None = None,
) -> LedgerEntry:
    """Changes the (already locked) user's balance and records it. Caller commits."""
    user.balance_cents += amount_cents
    entry = LedgerEntry(
        user_id=user.id,
        amount_cents=amount_cents,
        balance_after_cents=user.balance_cents,
        kind=kind,
        bet_id=bet_id,
        created_by_id=created_by_id,
        note=note,
    )
    db.add(entry)
    return entry
