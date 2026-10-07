import uuid
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
from app.services import settlement, verification, wallet
from app.services.odds_math import parlay_payout_cents

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
    if not verification.is_verified(current):
        raise HTTPException(status_code=403, detail="Verify your email to place bets")

    lines: list[tuple[OddsLine, Game]] = []
    for leg in payload.legs:
        line = db.get(OddsLine, leg.odds_line_id)
        if line is None:
            raise HTTPException(status_code=404, detail="One of those lines is no longer available")
        game = db.get(Game, line.game_id)
        assert game is not None
        lines.append((line, game))

    game_ids = [game.id for _, game in lines]
    if len(set(game_ids)) != len(game_ids):
        # Picks from the same game depend on each other, which parlay odds don't account for.
        raise HTTPException(status_code=400, detail="A parlay can only have one pick per game")
    started = [g for _, g in lines if g.commence_time <= datetime.now(UTC)]
    if started:
        game = started[0]
        raise HTTPException(
            status_code=400, detail=f"{game.away_team} @ {game.home_team} has already started"
        )

    changes = [
        {"odds_line_id": str(line.id), "price_american": line.price_american, "point": line.point}
        for (line, _), leg in zip(lines, payload.legs, strict=True)
        if (line.price_american, line.point) != (leg.expected_price_american, leg.expected_point)
    ]
    if changes:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "The odds have changed", "changes": changes},
        )

    user = wallet.lock_user(db, current.id)
    if payload.stake_cents > user.balance_cents:
        raise HTTPException(status_code=400, detail="Not enough balance for that stake")

    bet = Bet(
        user_id=user.id,
        stake_cents=payload.stake_cents,
        potential_payout_cents=parlay_payout_cents(
            payload.stake_cents, [line.price_american for line, _ in lines]
        ),
        status=BetStatus.PENDING,
        legs=[
            BetLeg(
                game_id=game.id,
                market=line.market,
                outcome=line.outcome,
                price_american=line.price_american,
                point=line.point,
            )
            for line, game in lines
        ],
    )
    db.add(bet)
    db.flush()
    wallet.apply(db, user, -payload.stake_cents, LedgerKind.BET_STAKE, bet_id=bet.id)
    db.commit()

    return PlaceBetResponse(
        bet=BetRead.model_validate(_load_bet(db, bet.id)), balance_cents=user.balance_cents
    )


BetState = Literal["open", "settled"]


def bets_for_user(db: Session, user_id: uuid.UUID, state: BetState) -> list[Bet]:
    """A user's open bets (oldest first) or settled bets (most recently settled first)."""
    query = (
        select(Bet)
        .where(Bet.user_id == user_id)
        .options(selectinload(Bet.legs).selectinload(BetLeg.game))
    )
    if state == "open":
        query = query.where(Bet.status == BetStatus.PENDING).order_by(Bet.created_at)
    else:
        query = query.where(Bet.status != BetStatus.PENDING).order_by(
            Bet.settled_at.desc(), Bet.created_at.desc()
        )
    return list(db.scalars(query).all())


@router.get("", response_model=list[BetRead])
def list_bets(
    state: BetState = "open",
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> list[Bet]:
    settlement.settle_if_due(db)
    return bets_for_user(db, current.id, state)
