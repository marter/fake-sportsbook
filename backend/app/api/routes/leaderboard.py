from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.db import get_db
from app.models.bet import Bet, BetStatus
from app.models.user import User
from app.schemas.leaderboard import LeaderboardRow
from app.services import settlement

router = APIRouter(prefix="/api/leaderboard", tags=["leaderboard"])

SETTLED = (BetStatus.WON, BetStatus.LOST, BetStatus.PUSH, BetStatus.VOID)


@router.get("", response_model=list[LeaderboardRow])
def leaderboard(
    db: Session = Depends(get_db), _current: User = Depends(get_current_user)
) -> list[LeaderboardRow]:
    """Everyone ranked by betting profit on settled bets.

    Ranked by profit rather than balance, so the starting bonus and admin adjustments don't
    count: only results from betting do.
    """
    settlement.settle_if_due(db)

    settled = Bet.status.in_(SETTLED)
    profit = func.coalesce(func.sum(Bet.payout_cents - Bet.stake_cents).filter(settled), 0)
    staked = func.coalesce(func.sum(Bet.stake_cents).filter(settled), 0)
    wins = func.count(Bet.id).filter(Bet.status == BetStatus.WON)
    rows = db.execute(
        select(
            User.id,
            User.display_name,
            profit.label("profit"),
            staked.label("staked"),
            wins.label("wins"),
            func.count(Bet.id).filter(Bet.status == BetStatus.LOST).label("losses"),
            func.count(Bet.id).filter(Bet.status == BetStatus.PUSH).label("pushes"),
            func.count(Bet.id).filter(Bet.status == BetStatus.PENDING).label("open_bets"),
        )
        .outerjoin(Bet, Bet.user_id == User.id)
        .where(User.is_active.is_(True))
        .group_by(User.id)
        .order_by(profit.desc(), wins.desc(), User.display_name)
    ).all()

    board: list[LeaderboardRow] = []
    for i, row in enumerate(rows):
        # Equal profit and wins share a rank (1, 2, 2, 4).
        tied = i > 0 and (row.profit, row.wins) == (rows[i - 1].profit, rows[i - 1].wins)
        board.append(
            LeaderboardRow(
                rank=board[-1].rank if tied else i + 1,
                user_id=row.id,
                display_name=row.display_name,
                profit_cents=row.profit,
                staked_cents=row.staked,
                wins=row.wins,
                losses=row.losses,
                pushes=row.pushes,
                open_bets=row.open_bets,
            )
        )
    return board
