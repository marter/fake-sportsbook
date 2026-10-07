import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.db import get_db
from app.models.ledger import LedgerEntry, LedgerKind
from app.models.user import User
from app.schemas.admin import AdminUserRead, BalanceAdjustment
from app.schemas.bet import LedgerEntryRead
from app.services import wallet

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users", response_model=list[AdminUserRead])
def list_users(db: Session = Depends(get_db), _admin: User = Depends(require_admin)) -> list[User]:
    return list(db.scalars(select(User).order_by(User.created_at)).all())


@router.post("/users/{user_id}/adjust", response_model=LedgerEntryRead)
def adjust_balance(
    user_id: uuid.UUID,
    payload: BalanceAdjustment,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> LedgerEntry:
    if db.get(User, user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")
    user = wallet.lock_user(db, user_id)

    if payload.set_balance_cents is not None:
        amount = payload.set_balance_cents - user.balance_cents
        if amount == 0:
            raise HTTPException(status_code=400, detail="Balance is already that amount")
    else:
        assert payload.amount_cents is not None
        amount = payload.amount_cents
    if user.balance_cents + amount < 0:
        raise HTTPException(status_code=400, detail="Balance can't go below $0")

    entry = wallet.apply(
        db,
        user,
        amount,
        LedgerKind.ADMIN_ADJUSTMENT,
        created_by_id=admin.id,
        note=payload.note.strip() if payload.note else None,
    )
    db.commit()
    return entry
