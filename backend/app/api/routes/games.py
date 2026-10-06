from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.db import get_db
from app.models.game import Game
from app.models.user import User
from app.schemas.game import GameRead, GamesResponse
from app.services.odds import ensure_fresh_odds

router = APIRouter(prefix="/api/games", tags=["games"])


@router.get("", response_model=GamesResponse)
def list_games(
    db: Session = Depends(get_db), _current: User = Depends(get_current_user)
) -> GamesResponse:
    """Upcoming games with current lines, refreshing the weekly odds cache first if stale."""
    fetch = ensure_fresh_odds(db)
    games = db.scalars(
        select(Game)
        .where(
            Game.sport_key == get_settings().odds_sport_key,
            Game.commence_time > datetime.now(UTC),
        )
        .options(selectinload(Game.odds_lines))
        .order_by(Game.commence_time, Game.home_team)
    ).all()
    return GamesResponse(
        odds_updated_at=fetch.fetched_at if fetch else None,
        games=[GameRead.model_validate(g) for g in games],
    )
