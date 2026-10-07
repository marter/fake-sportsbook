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
from app.services import odds, wallet
from app.services.odds_math import payout_cents
from app.sports import BY_API_KEY, SPORTS, Sport

logger = logging.getLogger(__name__)


def grade_leg(
    market: Market,
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


def bet_outcome(bet: Bet) -> tuple[BetStatus, int]:
    """Final status and payout for a bet whose legs are all graded.

    Any lost leg loses the bet. Pushed legs drop out (they pay even money), so a single bet
    that pushes is refunded its stake.
    """
    results = [leg.result for leg in bet.legs]
    if LegResult.LOST in results:
        return BetStatus.LOST, 0
    if all(r == LegResult.PUSH for r in results):
        return BetStatus.PUSH, bet.stake_cents
    payout = bet.stake_cents
    for leg in bet.legs:
        if leg.result == LegResult.WON:
            payout = payout_cents(payout, leg.price_american)
    return BetStatus.WON, payout


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


def _low_on_credits(db: Session) -> bool:
    """True if the most recent API call reported fewer credits left than the floor."""
    last_api_call = db.scalars(
        select(OddsFetch)
        .where(OddsFetch.source == "api", OddsFetch.requests_remaining.is_not(None))
        .order_by(OddsFetch.fetched_at.desc())
        .limit(1)
    ).first()
    return (
        last_api_call is not None
        and last_api_call.requests_remaining is not None
        and last_api_call.requests_remaining < get_settings().scores_min_credits
    )


def _has_settleable_bets(db: Session) -> bool:
    """Open bets on games that already have a final score (normally settled in the same run
    that records the score, but this catches anything left behind)."""
    return (
        db.scalars(
            select(Bet.id)
            .join(BetLeg, BetLeg.bet_id == Bet.id)
            .join(Game, Game.id == BetLeg.game_id)
            .where(Bet.status == BetStatus.PENDING, Game.completed.is_(True))
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
    """Grades and pays every open bet whose games are all final. Returns bets settled."""
    # Row locks on the open bets: a concurrent run waits, then no longer sees them as pending.
    pending = db.scalars(
        select(Bet)
        .where(Bet.status == BetStatus.PENDING)
        .options(selectinload(Bet.legs).selectinload(BetLeg.game))
        .with_for_update(of=Bet)
    ).all()

    settled = 0
    for bet in pending:
        if not all(leg.game.completed for leg in bet.legs):
            continue
        for leg in bet.legs:
            game = leg.game
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
        status, payout = bet_outcome(bet)
        bet.status = status
        bet.payout_cents = payout
        bet.settled_at = now
        if payout > 0:
            user = wallet.lock_user(db, bet.user_id)
            kind = LedgerKind.BET_PAYOUT if status == BetStatus.WON else LedgerKind.BET_REFUND
            wallet.apply(db, user, payout, kind, bet_id=bet.id)
        settled += 1
    return settled


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

    low_credits = settings.odds_api_key and _low_on_credits(db)
    if awaiting and low_credits:
        logger.warning(
            "Skipping score check: under %d API credits left", settings.scores_min_credits
        )
    by_sport: dict[Sport, list[Game]] = {}
    for game in awaiting:
        by_sport.setdefault(_sport_of(game), []).append(game)
    for sport, games in by_sport.items():
        if low_credits:
            break
        last = odds.latest_fetch(db, sport.api_key, kind="scores")
        throttled = last is not None and now - last.fetched_at < timedelta(
            minutes=settings.scores_min_interval_minutes
        )
        if throttled and not force_fetch:
            continue
        try:
            if settings.odds_api_key:
                events, remaining = odds.fetch_scores_from_api(sport)
                source = "api"
            else:
                events, remaining = fixture_scores(games), None
                source = "fixture"
        except httpx.HTTPError:
            logger.exception("The Odds API %s scores request failed; will retry", sport.name)
            continue
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

    settled = settle_completed(db, now)
    db.commit()
    if settled:
        logger.info("Settled %d bet(s)", settled)
    return settled
