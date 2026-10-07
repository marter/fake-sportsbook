def payout_cents(stake_cents: int, price_american: int) -> int:
    """Stake plus winnings for a winning bet at American odds, rounded down to the cent.

    +150: a $100 stake wins $150 (pays $250). -110: a $110 stake wins $100 (pays $210).
    """
    if price_american >= 100:
        winnings = stake_cents * price_american // 100
    elif price_american <= -100:
        winnings = stake_cents * 100 // -price_american
    else:
        raise ValueError(f"Invalid American odds: {price_american}")
    return stake_cents + winnings
