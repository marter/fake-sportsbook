from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.core.db import get_db
from app.models.game import Game
from app.models.user import User
from app.schemas.game import GameRead, GamesResponse, SportRead
from app.services import odds, settlement
from app.sports import BY_SLUG, Sport

router = APIRouter(prefix="/api", tags=["games"])


def _sport(slug: str) -> Sport:
    sport = BY_SLUG.get(slug)
    if sport is None or sport not in odds.enabled_sports():
        raise HTTPException(status_code=404, detail=f"Unknown sport {slug!r}")
    return sport


@router.get("/sports", response_model=list[SportRead])
def list_sports(
    db: Session = Depends(get_db), _current: User = Depends(get_current_user)
) -> list[SportRead]:
    """The league tabs: every enabled sport, whether it's in season, and upcoming game counts.
    Reads only what's cached; it never spends API credits."""
    counts = dict(
        db.execute(
            select(Game.sport_key, func.count())
            .where(Game.commence_time > datetime.now(UTC))
            .group_by(Game.sport_key)
        ).all()
    )
    return [
        SportRead(
            slug=s.slug,
            name=s.name,
            in_season=odds.is_active(s),
            upcoming_games=counts.get(s.api_key, 0),
            spread_label=s.spread_label,
            season_note=s.season_note,
        )
        for s in odds.enabled_sports()
    ]


@router.get("/games", response_model=GamesResponse)
def list_games(
    sport: str = "nfl",
    db: Session = Depends(get_db),
    _current: User = Depends(get_current_user),
) -> GamesResponse:
    """A sport's upcoming games with current lines, refreshing its daily odds cache if stale."""
    league = _sport(sport)
    fetch = odds.ensure_fresh_odds(db, league)
    settlement.settle_if_due(db)
    games = db.scalars(
        select(Game)
        .where(
            Game.sport_key == league.api_key,
            Game.commence_time > datetime.now(UTC),
            Game.completed.is_(False),
        )
        .options(selectinload(Game.odds_lines))
        .order_by(Game.commence_time, Game.home_team)
    ).all()
    return GamesResponse(
        odds_updated_at=fetch.fetched_at if fetch else None,
        games=[GameRead.model_validate(g) for g in games],
    )
