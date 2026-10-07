import uuid

from pydantic import BaseModel


class LeaderboardRow(BaseModel):
    rank: int
    user_id: uuid.UUID
    display_name: str
    profit_cents: int  # payouts minus stakes, settled bets only
    staked_cents: int  # total stakes on settled bets
    wins: int
    losses: int
    pushes: int
    open_bets: int
