"""ESPN's public JSON API: final scores (settlement) and box scores (props_grading.py).

No key and no credits, but it's unofficial and can change without notice, so settlement
falls back to The Odds API when ESPN fails or can't find a game.
"""

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.models.game import Game
from app.sports import Sport

ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports"
ESPN_PATHS = {
    "nfl": "football/nfl",
    "nba": "basketball/nba",
    "mlb": "baseball/mlb",
    "wnba": "basketball/wnba",
}
EASTERN = ZoneInfo("America/New_York")
# ESPN team names that differ from The Odds API's (which is what games store).
TEAM_ALIASES = {"LA Clippers": "Los Angeles Clippers"}
# An ESPN game this far from our kickoff time isn't ours (e.g. the other half of a
# doubleheader, or a rescheduled game).
MAX_START_DIFFERENCE = timedelta(hours=3)


class EspnError(Exception):
    """ESPN was unreachable or answered in a shape we don't understand."""


def fetch_espn(path: str, params: dict[str, str]) -> dict[str, Any]:
    response = httpx.get(
        f"{ESPN_BASE}/{path}", params=params, headers={"User-Agent": "Mozilla/5.0"}, timeout=10
    )
    response.raise_for_status()
    return response.json()


def team_name(espn_name: str) -> str:
    return TEAM_ALIASES.get(espn_name, espn_name)


def final_scores(sport: Sport, games: list[Game]) -> tuple[list[dict[str, Any]], list[Game]]:
    """Looks up `games` on ESPN's scoreboard. Returns final scores as events in The Odds API's
    scores shape (keyed by our external_id, so settlement treats both sources alike), and the
    games ESPN doesn't list at all. Games ESPN lists but hasn't finished (still playing,
    postponed) are in neither. Raises EspnError if ESPN fails."""
    path = ESPN_PATHS[sport.slug]
    boards: dict[date, list[dict[str, Any]]] = {}

    def events_on(day: date) -> list[dict[str, Any]]:
        if day not in boards:
            board = fetch_espn(f"{path}/scoreboard", {"dates": day.strftime("%Y%m%d")})
            boards[day] = board.get("events", [])
        return boards[day]

    events, unlisted = [], []
    try:
        for game in games:
            match = _find(game, events_on)
            if match is None:
                unlisted.append(game)
            elif match["status"]["type"]["completed"]:
                competitors = match["competitions"][0]["competitors"]
                events.append(
                    {
                        "id": game.external_id,
                        "completed": True,
                        "scores": [
                            {"name": team_name(c["team"]["displayName"]), "score": c["score"]}
                            for c in competitors
                        ],
                    }
                )
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
        raise EspnError(f"ESPN {sport.name} scoreboard: {exc!r}") from exc
    return events, unlisted


def _find(game: Game, events_on: Any) -> dict[str, Any] | None:
    """The ESPN event with the same two teams that starts closest to our kickoff. ESPN files
    games under their US-Eastern date; neighboring days are checked only if needed."""
    wanted = {game.home_team, game.away_team}
    local_day = game.commence_time.astimezone(EASTERN).date()
    for offset in (0, -1, 1):
        day = local_day + timedelta(days=offset)
        candidates = [event for event in events_on(day) if _teams(event) == wanted]
        if candidates:
            best = min(candidates, key=lambda e: abs(_start(e) - game.commence_time))
            return best if abs(_start(best) - game.commence_time) <= MAX_START_DIFFERENCE else None
    return None


def _teams(event: dict[str, Any]) -> set[str]:
    return {team_name(c["team"]["displayName"]) for c in event["competitions"][0]["competitors"]}


def _start(event: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(event["date"].replace("Z", "+00:00"))
