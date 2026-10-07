from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.db import get_db
from app.models.ledger import LedgerEntry
from app.models.user import User
from app.schemas.bet import LedgerEntryRead

router = APIRouter(prefix="/api/wallet", tags=["wallet"])


@router.get("/ledger", response_model=list[LedgerEntryRead])
def ledger(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> list[LedgerEntry]:
    """The user's balance history, newest first."""
    return list(
        db.scalars(
            select(LedgerEntry)
            .where(LedgerEntry.user_id == current.id)
            .order_by(LedgerEntry.created_at.desc(), LedgerEntry.id)
            .limit(limit)
        ).all()
    )
