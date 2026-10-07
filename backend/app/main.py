from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import admin, auth, bets, games, leaderboard, wallet
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title="Fake Sportsbook API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(games.router)
app.include_router(bets.router)
app.include_router(wallet.router)
app.include_router(admin.router)
app.include_router(leaderboard.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
