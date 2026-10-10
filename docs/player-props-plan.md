# Player props: plan

Status: in progress on the `feat/player-props` branch, not merged to main.

Player props are bets on one player's stats rather than the game result, e.g.
"Jalen Hurts over 186.5 passing yards" or "Travis Kelce scores a touchdown (anytime)".

## What we verified (Oct 10, 2026)

**Odds: The Odds API has them, on the free plan.**
- Only per game: `GET /v4/sports/{sport}/events/{eventId}/odds?markets=player_pass_yds,...`.
  The game list (`/events`) is free.
- Cost: **1 credit per market per game** (2 markets on one NFL game cost 2).
- Format:
  - Over/under props: `{"name": "Over", "description": "Trevor Lawrence", "price": -112, "point": 228.5}`
  - Yes-only props (anytime TD): `{"name": "Yes", "description": "Jalen Hurts", "price": 195}`

**Results: The Odds API has no player stats.** ESPN's public JSON (no key; unofficial, so
it can change without notice) has full box scores:
- `site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates=YYYYMMDD` lists games
- `.../summary?event={id}` gives per-player passing/rushing/receiving lines
- NBA and MLB endpoints respond too (`basketball/nba`, `baseball/mlb`).

## Markets (start small: NFL only)

**Decision (Oct 10): two markets on the free plan, Anytime TD and Passing yards** (2 credits
per game, ~130/month). Adding more later is a one-line change to `NFL_PROPS` in
`backend/app/sports.py`, e.g. after moving to the ~$30/month API tier.

| Key | Shown as | Kind | Graded from (ESPN box score) |
|---|---|---|---|
| `player_pass_yds` | Passing yards | Over/Under | passing YDS |
| `player_rush_yds` | Rushing yards | Over/Under | rushing YDS |
| `player_reception_yds` | Receiving yards | Over/Under | receiving YDS |
| `player_anytime_td` | Anytime TD | Yes | rushing TD + receiving TD |

Later, NBA (`player_points`, `player_rebounds`, `player_assists`) and MLB (`batter_hits`,
`pitcher_strikeouts`) use the same machinery.

## Credits (the real constraint on the free plan)

Props are fetched **lazily**: only when someone opens a game's props, only for games kicking
off within ~2 days, and at most once per game (odds lock at placement, so stale prop lines
are fine for play money; an admin can force a refresh).

- 4 NFL markets × ~15 games a week, if every game gets opened: ~60 credits/week, ~260/month.
- Daily game odds for NFL + NBA + MLB already use ~270/month, so **both together exceed 500**
  in a busy month.
- Levers, cheapest first: fewer markets (2 is about 130/month), props only for the
  primetime/featured games, refresh NBA/MLB game odds every 48h, or the ~$30/month API tier.
  **Decision needed before shipping.**

## Rules

- A prop is one pick on its game, so the existing one-pick-per-game parlay rule applies.
  Same-game parlays (prop + spread on one game) are correlated and need special pricing:
  out of scope.
- Over/Under graded against the stat; a whole-number line hit exactly is a push.
- Anytime TD wins if the player has a rushing or receiving TD. (Passing TDs don't count, as
  at real books.)
- **Player doesn't play / not in the box score: the leg is voided (refunded).** That's the
  standard sportsbook rule; in a parlay the leg drops out like a push.
- Can't be matched automatically (name mismatch, ESPN down for 24h): listed for an admin to
  grade or void by hand.

## Build steps

1. **Data model** (branch): markets become plain strings instead of a fixed enum, and lines
   and legs get a `participant` (player name). Migration converts existing data; no visible
   change. *(done)*
2. **Fetch props**: per-game, lazy, cached; `GET /api/games/{id}/props`; credits logged like
   other fetches; fixture data for dev. *(done: once per game within 48h of kickoff, skipped
   when credits are low, retried if the API call fails; settlement leaves prop legs open
   until step 4)*
3. **UI**: "Props" link on each game card opens a game page with props grouped by market,
   player rows with Over/Under (or Yes) buttons that add to the existing bet slip. Bet slip
   and bet cards label them, e.g. "Hurts Over 186.5 pass yds".
4. **Grading**: after a game is final, match it to ESPN by date and teams, pull the box score,
   match players by normalized name (case, punctuation, Jr./III), grade or void legs. Admin
   "needs grading" list for anything unmatched.
5. **Tests** throughout; rehearse on dev with fixture props and a saved ESPN box score.
6. **Decide credits, then merge.**
