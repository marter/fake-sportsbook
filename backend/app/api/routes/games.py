import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.core.db import get_db
from app.models.game import Game, Market
from app.models.user import User
from app.schemas.game import (
    GamePropsResponse,
    GameRead,
    GamesResponse,
    OddsLineRead,
    PropMarketRead,
    SportRead,
)
from app.services import odds, settlement
from app.sports import BY_API_KEY, BY_SLUG, Sport

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
        games=[game_read(g) for g in games],
    )


GAME_MARKETS = {m.value for m in Market}


def game_read(game: Game) -> GameRead:
    sport = BY_API_KEY.get(game.sport_key)
    return GameRead(
        id=game.id,
        home_team=game.home_team,
        away_team=game.away_team,
        commence_time=game.commence_time,
        odds_lines=[
            OddsLineRead.model_validate(line)
            for line in game.odds_lines
            if line.market in GAME_MARKETS
        ],
        has_props=bool(sport and sport.prop_markets),
    )


@router.get("/games/{game_id}/props", response_model=GamePropsResponse)
def game_props(
    game_id: uuid.UUID,
    db: Session = Depends(get_db),
    _current: User = Depends(get_current_user),
) -> GamePropsResponse:
    """A game's player props, fetched from The Odds API the first time anyone asks (once per
    game, within two days of kickoff)."""
    game = db.get(Game, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    odds.ensure_props(db, game)
    game = db.scalars(
        select(Game).where(Game.id == game_id).options(selectinload(Game.odds_lines))
    ).one()
    sport = BY_API_KEY.get(game.sport_key)
    markets = sport.prop_markets if sport else ()
    reason = odds.props_unavailable_reason(game, datetime.now(UTC))
    prop_keys = {m.key for m in markets}
    lines = [] if reason else [line for line in game.odds_lines if line.market in prop_keys]
    if not reason and not lines and game.props_fetched_at is not None:
        reason = "No player props were posted for this game."
    return GamePropsResponse(
        game=game_read(game),
        unavailable_reason=reason,
        markets=[PropMarketRead(**m.__dict__) for m in markets],
        lines=[
            OddsLineRead.model_validate(line)
            for line in sorted(lines, key=lambda x: (x.market, x.participant, x.outcome))
        ],
    )
