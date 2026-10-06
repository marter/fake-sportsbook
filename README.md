# Fake Sportsbook

A play-money NFL betting app, built mobile-first for the web. Odds come from
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
  `STARTING_BALANCE_CENTS` (default $1,000).
- **Odds**: cached in Postgres for a week (`ODDS_CACHE_HOURS`, default 168). There's no
  background worker. `GET /api/games` checks the cache, and if it's stale, makes one call to
  The Odds API (NFL, DraftKings, moneyline/spread/total, about 3 credits). If that call
  fails, the API serves the stale odds. The frontend never calls The Odds API directly.
- **No API key?** With `ODDS_API_KEY` unset, odds load from `backend/fixtures/nfl_odds.json`,
  shifted so the games are always in the near future.
- **Force a refresh**: `docker compose exec backend python -m app.services.odds`

## Roadmap

1. ~~Scaffold: auth, mobile shell, migrations~~
2. ~~NFL odds: weekly cache, fixture mode, games list~~
3. Betting: wallet ledger, bet placement with row locking and line-move checks, bet slip
4. Settlement: scores (short cache, only for started games with pending bets), grading, payouts
5. Polish: leaderboard, daily top-up, PWA

Deployment: one Lightsail server with Docker Compose and Caddy. See `deploy/README.md`.
