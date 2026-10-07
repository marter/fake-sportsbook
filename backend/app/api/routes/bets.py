from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.core.db import get_db
from app.models.bet import Bet, BetLeg, BetStatus
from app.models.game import Game, OddsLine
from app.models.ledger import LedgerKind
from app.models.user import User
from app.schemas.bet import BetCreate, BetRead, PlaceBetResponse
from app.services import wallet
from app.services.odds_math import payout_cents

router = APIRouter(prefix="/api/bets", tags=["bets"])


def _load_bet(db: Session, bet_id) -> Bet:
    return db.scalars(
        select(Bet)
        .where(Bet.id == bet_id)
        .options(selectinload(Bet.legs).selectinload(BetLeg.game))
    ).one()


@router.post("", response_model=PlaceBetResponse, status_code=status.HTTP_201_CREATED)
def place_bet(
    payload: BetCreate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> PlaceBetResponse:
    line = db.get(OddsLine, payload.odds_line_id)
    if line is None:
        raise HTTPException(status_code=404, detail="That line is no longer available")
    game = db.get(Game, line.game_id)
    assert game is not None
    if game.commence_time <= datetime.now(UTC):
        raise HTTPException(status_code=400, detail="This game has already started")

    if (line.price_american, line.point) != (
        payload.expected_price_american,
        payload.expected_point,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "The odds have changed",
                "price_american": line.price_american,
                "point": line.point,
            },
        )

    user = wallet.lock_user(db, current.id)
    if payload.stake_cents > user.balance_cents:
        raise HTTPException(status_code=400, detail="Not enough balance for that stake")

    bet = Bet(
        user_id=user.id,
        stake_cents=payload.stake_cents,
        potential_payout_cents=payout_cents(payload.stake_cents, line.price_american),
        status=BetStatus.PENDING,
        legs=[
            BetLeg(
                game_id=game.id,
                market=line.market,
                outcome=line.outcome,
                price_american=line.price_american,
                point=line.point,
            )
        ],
    )
    db.add(bet)
    db.flush()
    wallet.apply(db, user, -payload.stake_cents, LedgerKind.BET_STAKE, bet_id=bet.id)
    db.commit()

    return PlaceBetResponse(
        bet=BetRead.model_validate(_load_bet(db, bet.id)), balance_cents=user.balance_cents
    )


@router.get("", response_model=list[BetRead])
def list_bets(
    state: Literal["open", "settled"] = "open",
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> list[Bet]:
    query = (
        select(Bet)
        .where(Bet.user_id == current.id)
        .options(selectinload(Bet.legs).selectinload(BetLeg.game))
    )
    if state == "open":
        query = query.where(Bet.status == BetStatus.PENDING).order_by(Bet.created_at)
    else:
        query = query.where(Bet.status != BetStatus.PENDING).order_by(Bet.settled_at.desc())
    return list(db.scalars(query).all())
