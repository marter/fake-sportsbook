"""Grades player-prop legs from ESPN box scores.

The Odds API has odds but no player stats, so finished games are looked up in ESPN's public
JSON (no key; unofficial, so it can change without notice). This runs from the background
worker and the `settle` CLI, never on page loads, so a slow ESPN can't slow the app down.
Legs that can't be graded automatically (game or player not found) stay open and, after a
grace period, show up on the admin page to grade by hand.
"""

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.bet import Bet, BetLeg, BetStatus, LegResult
from app.models.game import Game
from app.sports import BY_API_KEY, prop_market

logger = logging.getLogger(__name__)

ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports"
ESPN_PATHS = {"nfl": "football/nfl", "nba": "basketball/nba", "mlb": "baseball/mlb"}
EASTERN = ZoneInfo("America/New_York")
# Box-score categories whose TD column counts toward "anytime touchdown". Passing TDs don't
# count (the thrower isn't the scorer), matching real sportsbooks.
TD_CATEGORIES = ("rushing", "receiving", "kickReturns", "puntReturns")
# Don't ask an admin to grade a leg until automatic grading has had this long after the game.
MANUAL_GRADING_AFTER = timedelta(hours=12)


def fetch_espn(path: str, params: dict[str, str]) -> dict[str, Any]:
    response = httpx.get(
        f"{ESPN_BASE}/{path}", params=params, headers={"User-Agent": "Mozilla/5.0"}, timeout=10
    )
    response.raise_for_status()
    return response.json()


def normalize_name(name: str) -> str:
    """"Marvin Harrison Jr." and "marvin harrison" compare equal; so do "A.J." and "AJ"."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    cleaned = re.sub(r"[^a-z ]", "", ascii_name.lower().replace("-", " "))
    words = [w for w in cleaned.split() if w not in {"jr", "sr", "ii", "iii", "iv", "v"}]
    return " ".join(words)


@dataclass
class PlayerStats:
    pass_yds: float = 0
    rush_yds: float = 0
    rec_yds: float = 0
    receptions: float = 0
    tds: int = 0  # rushing + receiving + return touchdowns


@dataclass
class BoxScore:
    players: dict[str, PlayerStats] = field(default_factory=dict)  # by normalized name

    def stat(self, market: str, player: str) -> float | None:
        """The stat a market is graded on, or None if the player isn't in the box score."""
        stats = self.players.get(normalize_name(player))
        if stats is None:
            return None
        return {
            "player_pass_yds": stats.pass_yds,
            "player_rush_yds": stats.rush_yds,
            "player_reception_yds": stats.rec_yds,
            "player_receptions": stats.receptions,
            "player_anytime_td": stats.tds,
        }.get(market)


def _number(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        return 0


def parse_box_score(summary: dict[str, Any]) -> BoxScore:
    """Per-player stats from an ESPN NFL summary. Columns are looked up by label, not
    position. Anyone listed in any category (even defense or kicking) counts as having
    played, so their prop is graded (a 0) rather than voided."""
    box = BoxScore()
    for team in summary.get("boxscore", {}).get("players", []):
        for category in team.get("statistics", []):
            labels = category.get("labels", [])
            for row in category.get("athletes", []):
                name = normalize_name(row["athlete"]["displayName"])
                stats = box.players.setdefault(name, PlayerStats())
                values = dict(zip(labels, row.get("stats", []), strict=False))
                kind = category.get("name")
                if kind == "passing":
                    stats.pass_yds += _number(values.get("YDS", "0"))
                elif kind == "rushing":
                    stats.rush_yds += _number(values.get("YDS", "0"))
                elif kind == "receiving":
                    stats.rec_yds += _number(values.get("YDS", "0"))
                    stats.receptions += _number(values.get("REC", "0"))
                if kind in TD_CATEGORIES:
                    stats.tds += int(_number(values.get("TD", "0")))
    return box


def grade_prop(market: str, outcome: str, point: float | None, stat: float | None) -> LegResult:
    """Over/Under against the line (exact hit pushes); Yes wins on at least one. A player
    who isn't in the box score didn't play: void."""
    if stat is None:
        return LegResult.VOID
    meta = prop_market(market)
    if outcome == "Yes" or (meta and meta.kind == "yes"):
        return LegResult.WON if stat >= 1 else LegResult.LOST
    assert point is not None
    if stat == point:
        return LegResult.PUSH
    over_hits = stat > point
    return LegResult.WON if over_hits == (outcome == "Over") else LegResult.LOST


def find_espn_event(game: Game, sport_path: str) -> str | None:
    """The ESPN event id for a finished game: same teams on the same US-Eastern date (also
    checking the neighboring days, for late games that cross midnight)."""
    local_day = game.commence_time.astimezone(EASTERN).date()
    wanted = {game.home_team, game.away_team}
    for offset in (0, -1, 1):
        day = local_day + timedelta(days=offset)
        board = fetch_espn(f"{sport_path}/scoreboard", {"dates": day.strftime("%Y%m%d")})
        for event in board.get("events", []):
            competitors = event.get("competitions", [{}])[0].get("competitors", [])
            teams = {c["team"]["displayName"] for c in competitors}
            if teams == wanted:
                if not event.get("status", {}).get("type", {}).get("completed"):
                    return None  # found, but ESPN doesn't have it final yet
                return str(event["id"])
    return None


def _games_with_ungraded_props(db: Session) -> list[Game]:
    return list(
        db.scalars(
            select(Game)
            .join(BetLeg, BetLeg.game_id == Game.id)
            .join(Bet, Bet.id == BetLeg.bet_id)
            .where(
                Game.completed.is_(True),
                Bet.status == BetStatus.PENDING,
                BetLeg.participant != "",
                BetLeg.result == LegResult.PENDING,
            )
            .distinct()
        ).all()
    )


def grade_props(db: Session) -> int:
    """Grades open prop legs on finished games from ESPN box scores. Returns legs graded.
    The caller settles bets afterwards (decided bets pay out through the normal path)."""
    graded = 0
    for game in _games_with_ungraded_props(db):
        sport = BY_API_KEY.get(game.sport_key)
        path = ESPN_PATHS.get(sport.slug) if sport else None
        if path is None:
            continue
        try:
            event_id = find_espn_event(game, path)
            if event_id is None:
                logger.info("No final ESPN box score yet for %s", game.external_id)
                continue
            box = parse_box_score(fetch_espn(f"{path}/summary", {"event": event_id}))
        except httpx.HTTPError:
            logger.exception("ESPN request failed for %s; will retry", game.external_id)
            continue
        if not box.players:
            logger.warning("ESPN box score for %s has no players", game.external_id)
            continue

        legs = db.scalars(
            select(BetLeg)
            .join(Bet, Bet.id == BetLeg.bet_id)
            .where(
                BetLeg.game_id == game.id,
                BetLeg.participant != "",
                BetLeg.result == LegResult.PENDING,
                Bet.status == BetStatus.PENDING,
            )
            .with_for_update(of=BetLeg)
        ).all()
        for leg in legs:
            leg.result = grade_prop(
                leg.market, leg.outcome, leg.point, box.stat(leg.market, leg.participant)
            )
            graded += 1
    return graded


def legs_needing_manual_grading(db: Session) -> list[BetLeg]:
    """Prop legs still open well after their game finished (ESPN couldn't match them)."""
    now = datetime.now(UTC)
    legs = db.scalars(
        select(BetLeg)
        .join(Bet, Bet.id == BetLeg.bet_id)
        .join(Game, Game.id == BetLeg.game_id)
        .where(
            Game.completed.is_(True),
            Bet.status == BetStatus.PENDING,
            BetLeg.participant != "",
            BetLeg.result == LegResult.PENDING,
        )
        .options(selectinload(BetLeg.game), selectinload(BetLeg.bet))
        .order_by(Game.commence_time)
    ).all()
    result = []
    for leg in legs:
        sport = BY_API_KEY.get(leg.game.sport_key)
        game_minutes = sport.game_minutes if sport else 180
        if now - leg.game.commence_time >= timedelta(minutes=game_minutes) + MANUAL_GRADING_AFTER:
            result.append(leg)
    return result
