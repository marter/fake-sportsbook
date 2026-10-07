from fractions import Fraction


def decimal_odds(price_american: int) -> Fraction:
    """American odds as an exact decimal multiplier: +150 -> 5/2, -110 -> 21/11."""
    if price_american >= 100:
        return Fraction(100 + price_american, 100)
    if price_american <= -100:
        return Fraction(-price_american + 100, -price_american)
    raise ValueError(f"Invalid American odds: {price_american}")


def parlay_payout_cents(stake_cents: int, prices_american: list[int]) -> int:
    """Stake plus winnings if every price wins, rounded down to the cent.

    A parlay multiplies the legs' decimal odds; with one price it's an ordinary single bet.
    Exact fractions until the final rounding, so the order of legs never changes the result.
    """
    multiplier = Fraction(1)
    for price in prices_american:
        multiplier *= decimal_odds(price)
    return int(stake_cents * multiplier)  # int() truncates toward zero == floor for positives


def payout_cents(stake_cents: int, price_american: int) -> int:
    """Stake plus winnings for a winning single bet at American odds, rounded down to the cent.

    +150: a $100 stake wins $150 (pays $250). -110: a $110 stake wins $100 (pays $210).
    """
    return parlay_payout_cents(stake_cents, [price_american])
