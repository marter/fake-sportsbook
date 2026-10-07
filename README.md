# Fake Sportsbook

A play-money betting app for the NFL, NBA, MLB and WNBA, built mobile-first for the web. Odds come from
[The Odds API](https://the-odds-api.com). Nothing here involves real money.

Stack and conventions follow `volunteer-scheduler`.

## Repo layout

- `backend/`: FastAPI, SQLAlchemy, Postgres API
- `frontend/`: React, TypeScript (Vite) mobile web app

## Local development

Requires Docker Desktop. Host ports are offset from volunteer-scheduler's so both
stacks can run at once.

```bash
docker compose up
```

- API: http://localhost:8001 (docs at `/docs`)
- Web app: http://localhost:5174. On a phone on the same Wi-Fi, use
  `http://<your-mac-ip>:5174` and add `http://<your-mac-ip>:5174` to `CORS_ORIGINS`.
- Postgres: localhost:5433 (`sportsbook` / `sportsbook`)

Dependencies sync and migrations run automatically when the backend container starts.
To use real odds, copy `backend/.env.example` to `backend/.env` and set `ODDS_API_KEY`. To create a new one:

```bash
cd backend
uv run alembic revision --autogenerate -m "describe change"
uv run alembic upgrade head
```

### Backend only

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8001
uv run pytest        # needs the db container; uses a separate fake_sportsbook_test database
uv run ruff check .
uv run mypy app
```

### Frontend only

```bash
cd frontend
npm install
npm run dev
```

## Architecture notes

- **Auth**: JWT bearer tokens, one global user. No orgs or tenants (yet).
- **Money**: integer cents everywhere (`balance_cents`). New accounts get
  `STARTING_BALANCE_CENTS` (default $1,000). Every balance change writes a `LedgerEntry`
  (via `app/services/wallet.py`) while holding a row lock on the user, so a user's ledger
  always sums to their balance and concurrent bets can't overspend.
- **Email verification**: new accounts get a single-use link (24h, stored hashed) and can't
  bet until they click it; resends are limited to 1/minute and 5/day. Accounts that never
  verify are deleted after 48 hours so they don't hold one of the `MAX_USERS` slots. Emails
  go through Resend in production (`RESEND_API_KEY`); locally they're printed in the backend
  logs (`docker compose logs backend`). Accounts created before this feature were marked
  verified by the migration.
- **Admins** can list users and adjust balances (recorded as ledger entries with a note).
  Admin is granted only from the server: `python -m app.cli make-admin <email>`.
- **Sports**: defined in `backend/app/sports.py` (API key, name, typical game length, what
  the spread is called, off-season note) and switched on with `ENABLED_SPORTS`. Each league is
  a tab on the Games page (`/games/nba`). Leagues out of season (per The Odds API's free
  `/sports` list, checked every 6 hours) show as dimmed tabs and are never fetched. Sample
  data for local dev lives in `backend/fixtures/<sport>_odds.json`.
- **Odds**: cached in Postgres for a day per sport (`ODDS_CACHE_HOURS`, default 24). There's no
  background worker. `GET /api/games` checks the cache, and if it's stale, makes one call to
  The Odds API (NFL, DraftKings, moneyline/spread/total, about 3 credits). If that call
  fails, the API serves the stale odds. The frontend never calls The Odds API directly.
- **Background worker** (`python -m app.worker`, the `settler` service in production): every
  15 minutes it runs the same cached checks as page loads, so odds refresh once a day and bets
  settle soon after games end even if nobody opens the app. It only spends credits when those
  checks are due. Score checks stop for a game with no final score 24h after kickoff (it's
  listed under "Needs attention" on the admin page for voiding) and pause when fewer than 50
  API credits are left.
- **Settlement**: also on demand. Loading bets or games checks whether any open bet is
  waiting on a game that kicked off over `GAME_DURATION_MINUTES` (180) ago; if so, it calls
  the scores endpoint (2 credits) at most every `SCORES_MIN_INTERVAL_MINUTES` (30), records
  final scores, grades legs, and pays winners / refunds pushes through the ledger. A
  settlement-wide advisory lock plus row locks on open bets mean a bet is paid exactly once.
  Force a run with `python -m app.cli settle`.
- **No API key?** With `ODDS_API_KEY` unset, odds load from `backend/fixtures/nfl_odds.json`,
  shifted so the games are always in the near future.
- **Force a refresh**: `docker compose exec backend python -m app.services.odds`

## Roadmap

1. ~~Scaffold: auth, mobile shell, migrations~~
2. ~~NFL odds: weekly cache, fixture mode, games list~~
3. ~~Betting: wallet ledger, bet placement with row locking and line-move checks, bet slip,
   admin balance adjustments~~
4. ~~Settlement: scores (short cache, only for started games with pending bets), grading, payouts~~
5. Polish: ~~leaderboard~~, daily top-up, PWA

Deployment: one Lightsail server with Docker Compose and Caddy. See `deploy/README.md`.
