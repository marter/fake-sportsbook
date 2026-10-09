import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select, text, update
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_admin
from app.api.routes.bets import BetState, bets_for_user
from app.core.db import get_db
from app.models.bet import Bet, BetLeg, BetStatus
from app.models.ledger import LedgerEntry, LedgerKind
from app.models.user import User
from app.schemas.admin import (
    AdminUserBets,
    AdminUserRead,
    BalanceAdjustment,
    StuckBet,
    StuckGame,
    VoidBet,
)
from app.schemas.bet import BetRead, LedgerEntryRead
from app.services import settlement, wallet

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


@router.get("/users/{user_id}/bets", response_model=AdminUserBets)
def user_bets(
    user_id: uuid.UUID,
    state: BetState = "open",
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> AdminUserBets:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    settlement.settle_if_due(db)
    return AdminUserBets(
        user=AdminUserRead.model_validate(user),
        bets=[BetRead.model_validate(b) for b in bets_for_user(db, user_id, state)],
    )


@router.post("/bets/{bet_id}/void", response_model=BetRead)
def void_bet(
    bet_id: uuid.UUID,
    payload: VoidBet,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> BetRead:
    """Cancels an open bet and refunds the stake (e.g. one placed by mistake)."""
    # Same lock as settlement, so a void and a settlement can't both act on this bet.
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext('settlement'))"))
    bet = db.scalars(select(Bet).where(Bet.id == bet_id).with_for_update()).first()
    if bet is None:
        raise HTTPException(status_code=404, detail="Bet not found")
    if bet.status != BetStatus.PENDING:
        raise HTTPException(status_code=400, detail="Only open bets can be voided")

    bet.status = BetStatus.VOID
    bet.payout_cents = bet.stake_cents
    bet.settled_at = datetime.now(UTC)
    user = wallet.lock_user(db, bet.user_id)
    wallet.apply(
        db,
        user,
        bet.stake_cents,
        LedgerKind.BET_REFUND,
        bet_id=bet.id,
        created_by_id=admin.id,
        note=(payload.note or "").strip() or "Voided by admin",
    )
    db.commit()

    loaded = db.scalars(
        select(Bet)
        .where(Bet.id == bet_id)
        .options(selectinload(Bet.legs).selectinload(BetLeg.game))
    ).one()
    return BetRead.model_validate(loaded)


@router.post("/users/{user_id}/verify", response_model=AdminUserRead)
def mark_verified(
    user_id: uuid.UUID, db: Session = Depends(get_db), _admin: User = Depends(require_admin)
) -> User:
    """For when the verification email doesn't arrive."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.email_verified:
        user.email_verified_at = datetime.now(UTC)
        db.commit()
    return user


@router.delete("/users/{user_id}", status_code=204)
def delete_user(
    user_id: uuid.UUID, db: Session = Depends(get_db), admin: User = Depends(require_admin)
) -> None:
    """Permanently deletes an account with all its bets and balance history, freeing its
    sign-up slot (the email can register again). Open bets go too, without refunds."""
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="You can't delete your own account")
    # Same lock as settlement, so a bet can't be paid out while its owner is being deleted.
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext('settlement'))"))
    if db.get(User, user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")
    wallet.lock_user(db, user_id)

    # Adjustments this user made to other people's balances stay on those people's history.
    db.execute(
        update(LedgerEntry)
        .where(LedgerEntry.created_by_id == user_id)
        .values(created_by_id=None)
    )
    db.execute(delete(LedgerEntry).where(LedgerEntry.user_id == user_id))
    db.execute(delete(Bet).where(Bet.user_id == user_id))  # legs cascade
    db.execute(delete(User).where(User.id == user_id))  # verification tokens cascade
    db.commit()


@router.get("/stuck-games", response_model=list[StuckGame])
def list_stuck_games(
    db: Session = Depends(get_db), _admin: User = Depends(require_admin)
) -> list[StuckGame]:
    """Games with open bets that still have no final score a day after kickoff (postponed or
    cancelled). Settlement has stopped checking them; void their bets if they won't be played."""
    result = []
    for game in settlement.stuck_games(db):
        rows = db.execute(
            select(Bet.id, Bet.user_id, User.display_name, Bet.stake_cents)
            .join(BetLeg, BetLeg.bet_id == Bet.id)
            .join(User, User.id == Bet.user_id)
            .where(BetLeg.game_id == game.id, Bet.status == BetStatus.PENDING)
            .order_by(Bet.created_at)
        ).all()
        result.append(
            StuckGame(
                game_id=game.id,
                home_team=game.home_team,
                away_team=game.away_team,
                commence_time=game.commence_time,
                open_bets=[
                    StuckBet(bet_id=r[0], user_id=r[1], display_name=r[2], stake_cents=r[3])
                    for r in rows
                ],
            )
        )
    return result
