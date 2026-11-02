"""Grades bets against final scores and pays them out.

No background worker, same as odds: `settle_if_due` runs when someone loads their bets or the
games list. It only calls the scores endpoint while some open bet is waiting on a game that
should be over, and at most every `scores_min_interval_minutes`.
"""

import hashlib
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.models.bet import Bet, BetLeg, BetStatus, LegResult
from app.models.game import Game, Market, OddsFetch
from app.models.ledger import LedgerKind
from app.services import espn, odds, wallet
from app.services.odds_math import parlay_payout_cents
from app.sports import BY_API_KEY, SPORTS, Sport

logger = logging.getLogger(__name__)


def grade_leg(
    market: str,
    outcome: str,
    point: float | None,
    home_team: str,
    away_team: str,
    home_score: int,
    away_score: int,
) -> LegResult:
    """Win, loss, or push for one selection given the final score."""
    if market == Market.TOTALS:
        assert point is not None
        total = home_score + away_score
        if total == point:
            return LegResult.PUSH
        over_wins = total > point
        return LegResult.WON if over_wins == (outcome == "Over") else LegResult.LOST

    if outcome == home_team:
        mine, theirs = home_score, away_score
    elif outcome == away_team:
        mine, theirs = away_score, home_score
    else:
        raise ValueError(f"{outcome!r} isn't playing in {away_team} @ {home_team}")

    margin = mine - theirs + (point if market == Market.SPREADS and point is not None else 0)
    if margin == 0:
        return LegResult.PUSH  # includes a tied game on the moneyline
    return LegResult.WON if margin > 0 else LegResult.LOST


def bet_outcome(bet: Bet) -> tuple[BetStatus, int] | None:
    """Final status and payout, or None if the bet can't be decided yet.

    Any lost leg loses the whole bet right away, even with games still to play. Otherwise it
    waits for every leg. Pushed and voided legs drop out (the parlay pays as if they weren't
    there), so a bet where every leg pushes or is voided is refunded its stake.
    """
    results = [leg.result for leg in bet.legs]
    if LegResult.LOST in results:
        return BetStatus.LOST, 0
    if LegResult.PENDING in results:
        return None
    if all(r == LegResult.VOID for r in results):
        return BetStatus.VOID, bet.stake_cents
    if all(r in (LegResult.PUSH, LegResult.VOID) for r in results):
        return BetStatus.PUSH, bet.stake_cents
    won = [leg.price_american for leg in bet.legs if leg.result == LegResult.WON]
    return BetStatus.WON, parlay_payout_cents(bet.stake_cents, won)


def _unfinished_games_with_open_bets(db: Session):
    return (
        select(Game)
        .join(BetLeg, BetLeg.game_id == Game.id)
        .join(Bet, Bet.id == BetLeg.bet_id)
        .where(Bet.status == BetStatus.PENDING, Game.completed.is_(False))
        .distinct()
    )


def _sport_of(game: Game) -> Sport:
    return BY_API_KEY.get(game.sport_key, SPORTS[0])


def _games_awaiting_result(db: Session, now: datetime) -> list[Game]:
    """Games with open bets that should be over by now (by their sport's usual length) but
    aren't past the give-up window."""
    settings = get_settings()
    shortest = min(s.game_minutes for s in SPORTS)
    give_up = now - timedelta(hours=settings.settlement_give_up_hours)
    candidates = db.scalars(
        _unfinished_games_with_open_bets(db).where(
            Game.commence_time <= now - timedelta(minutes=shortest),
            Game.commence_time > give_up,
        )
    ).all()
    return [
        g
        for g in candidates
        if g.commence_time <= now - timedelta(minutes=_sport_of(g).game_minutes)
    ]


def stuck_games(db: Session) -> list[Game]:
    """Games with open bets and still no final score past the give-up window."""
    give_up = datetime.now(UTC) - timedelta(hours=get_settings().settlement_give_up_hours)
    return list(
        db.scalars(
            _unfinished_games_with_open_bets(db)
            .where(Game.commence_time <= give_up)
            .order_by(Game.commence_time)
        ).all()
    )


def _has_settleable_bets(db: Session) -> bool:
    """Ungraded legs of open bets on games that already have a final score (normally graded in
    the same run that records the score, but this catches anything left behind)."""
    return (
        db.scalars(
            select(Bet.id)
            .join(BetLeg, BetLeg.bet_id == Bet.id)
            .join(Game, Game.id == BetLeg.game_id)
            .where(
                Bet.status == BetStatus.PENDING,
                BetLeg.result == LegResult.PENDING,
                BetLeg.participant == "",  # props wait for box-score grading in the worker
                Game.completed.is_(True),
            )
            .limit(1)
        ).first()
        is not None
    )


# Plausible (lowest, spread) of final scores per sport, for made-up fixture results.
FIXTURE_SCORE_RANGE = {"nfl": (10, 28), "nba": (95, 35), "wnba": (68, 30), "mlb": (0, 10)}


def fixture_scores(games: list[Game]) -> list[dict[str, Any]]:
    """Made-up but stable final scores, in the scores API's shape, for running without a key."""
    events = []
    for game in games:
        sport = _sport_of(game)
        low, spread = FIXTURE_SCORE_RANGE.get(sport.slug, (10, 28))
        digest = hashlib.sha256(game.external_id.encode()).digest()
        home, away = low + digest[0] % spread, low + digest[1] % spread
        if home == away and sport.slug != "nfl":
            home += 1  # only football can end in a tie
        events.append(
            {
                "id": game.external_id,
                "completed": True,
                "scores": [
                    {"name": game.home_team, "score": str(home)},
                    {"name": game.away_team, "score": str(away)},
                ],
            }
        )
    return events


def apply_scores(db: Session, events: list[dict[str, Any]]) -> int:
    """Records final scores for completed games we know about. Returns how many were updated."""
    by_id = {e["id"]: e for e in events if e.get("completed") and e.get("scores")}
    if not by_id:
        return 0
    updated = 0
    for game in db.scalars(select(Game).where(Game.external_id.in_(by_id))).all():
        if game.completed:
            continue
        scores = {s["name"]: int(s["score"]) for s in by_id[game.external_id]["scores"]}
        if game.home_team not in scores or game.away_team not in scores:
            logger.warning("Scores for %s don't match its teams: %s", game.external_id, scores)
            continue
        game.home_score = scores[game.home_team]
        game.away_score = scores[game.away_team]
        game.completed = True
        updated += 1
    return updated


def settle_completed(db: Session, now: datetime) -> int:
    """Grades every open bet's finished legs, and settles bets that are decided: all legs
    graded, or any leg lost. Returns bets settled."""
    # Row locks on the open bets: a concurrent run waits, then no longer sees them as pending.
    pending = db.scalars(
        select(Bet)
        .where(Bet.status == BetStatus.PENDING)
        .options(selectinload(Bet.legs).selectinload(BetLeg.game))
        .with_for_update(of=Bet)
    ).all()

    settled = 0
    for bet in pending:
        for leg in bet.legs:
            game = leg.game
            if leg.result != LegResult.PENDING or not game.completed:
                continue
            if leg.participant:
                continue  # props are graded from box scores (services/props_grading.py)
            assert game.home_score is not None and game.away_score is not None
            leg.result = grade_leg(
                leg.market,
                leg.outcome,
                leg.point,
                game.home_team,
                game.away_team,
                game.home_score,
                game.away_score,
            )
        outcome = bet_outcome(bet)
        if outcome is None:
            continue  # a parlay still waiting on other games; graded legs are saved
        status, payout = outcome
        bet.status = status
        bet.payout_cents = payout
        bet.settled_at = now
        if payout > 0:
            user = wallet.lock_user(db, bet.user_id)
            kind = LedgerKind.BET_PAYOUT if status == BetStatus.WON else LedgerKind.BET_REFUND
            wallet.apply(db, user, payout, kind, bet_id=bet.id)
        settled += 1
    return settled


def _record_scores(
    db: Session,
    sport: Sport,
    now: datetime,
    events: list[dict[str, Any]],
    source: str,
    remaining: int | None,
) -> None:
    apply_scores(db, events)
    db.add(
        OddsFetch(
            sport_key=sport.api_key,
            kind="scores",
            fetched_at=now,
            source=source,
            event_count=len(events),
            requests_remaining=remaining,
        )
    )


def _check_odds_api(db: Session, sport: Sport, now: datetime) -> None:
    """The Odds API's scores endpoint: 2 credits, skipped when credits are low."""
    if odds.low_on_credits(db):
        logger.warning(
            "Skipping %s score check: under %d API credits left",
            sport.name,
            get_settings().scores_min_credits,
        )
        return
    try:
        events, remaining = odds.fetch_scores_from_api(sport)
    except httpx.HTTPError:
        logger.exception("The Odds API %s scores request failed; will retry", sport.name)
        return
    _record_scores(db, sport, now, events, "api", remaining)


def _check_espn_then_api(
    db: Session, sport: Sport, games: list[Game], now: datetime, *, force_fetch: bool
) -> None:
    """Free ESPN scores first. Falls back to The Odds API (at most every
    `scores_fallback_hours` per sport, since it costs credits) when ESPN is down or still
    doesn't list a game hours after it should have ended, e.g. a team name we don't map."""
    settings = get_settings()
    try:
        events, unlisted = espn.final_scores(sport, games)
    except espn.EspnError:
        logger.exception("ESPN %s scores failed; trying The Odds API", sport.name)
        # Logged anyway, so the usual throttle keeps page loads from retrying ESPN each time.
        _record_scores(db, sport, now, [], "espn", None)
        needs_fallback = True
    else:
        _record_scores(db, sport, now, events, "espn", None)
        for game in unlisted:
            logger.warning(
                "ESPN doesn't list %s @ %s (%s)", game.away_team, game.home_team, game.external_id
            )
        overdue_after = timedelta(minutes=sport.game_minutes, hours=settings.scores_fallback_hours)
        needs_fallback = any(now - g.commence_time > overdue_after for g in unlisted)
    if not needs_fallback:
        return
    last_api = odds.latest_fetch(db, sport.api_key, kind="scores", source="api")
    recent = last_api is not None and now - last_api.fetched_at < timedelta(
        hours=settings.scores_fallback_hours
    )
    if not recent or force_fetch:
        _check_odds_api(db, sport, now)


def settle_if_due(db: Session, *, force_fetch: bool = False) -> int:
    """Fetches scores if any open bet is waiting on a finished game, then settles what it can.

    Holds a Postgres advisory lock for the whole run, so concurrent page loads can't fetch
    twice or pay a bet twice. Returns the number of bets settled.
    """
    settings = get_settings()
    now = datetime.now(UTC)
    if not force_fetch and not _games_awaiting_result(db, now) and not _has_settleable_bets(db):
        return 0

    db.execute(text("SELECT pg_advisory_xact_lock(hashtext('settlement'))"))
    awaiting = _games_awaiting_result(db, now)  # another request may have just settled them

    by_sport: dict[Sport, list[Game]] = {}
    for game in awaiting:
        by_sport.setdefault(_sport_of(game), []).append(game)
    for sport, games in by_sport.items():
        last = odds.latest_fetch(db, sport.api_key, kind="scores")
        throttled = last is not None and now - last.fetched_at < timedelta(
            minutes=settings.scores_min_interval_minutes
        )
        if throttled and not force_fetch:
            continue
        if not settings.odds_api_key:
            _record_scores(db, sport, now, fixture_scores(games), "fixture", None)
        elif settings.scores_source == "espn" and sport.slug in espn.ESPN_PATHS:
            _check_espn_then_api(db, sport, games, now, force_fetch=force_fetch)
        else:
            _check_odds_api(db, sport, now)

    settled = settle_completed(db, now)
    db.commit()
    if settled:
        logger.info("Settled %d bet(s)", settled)
    return settled


def grade_props_and_settle(db: Session) -> int:
    """Grades prop legs from ESPN box scores, then settles whatever that decided. Runs from
    the worker and the CLI (not page loads), under the settlement lock."""
    from app.services import props_grading

    db.execute(text("SELECT pg_advisory_xact_lock(hashtext('settlement'))"))
    graded = props_grading.grade_props(db)
    settled = settle_completed(db, datetime.now(UTC)) if graded else 0
    db.commit()
    if graded:
        logger.info("Graded %d prop leg(s), settled %d bet(s)", graded, settled)
    return settled
