"""How much of the month's Odds API credits we've used, for the admin page.

Each logged API call records the credits remaining after it (from the response headers), so
a call's cost is the drop from the call before it. The quota resets on the 1st (UTC). Calls
are ordered by remaining credits, not time: the balance only goes down within a month, and
the web server and worker can log calls a moment out of order.
"""

import calendar
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.game import OddsFetch


@dataclass
class CreditUsage:
    monthly_credits: int
    used: int
    remaining: int
    # Where usage ends up by the reset at the last 7 days' pace.
    projected: int
    resets_on: date
    # Below this many credits, score checks and props fetches pause (see low_on_credits).
    floor: int
    last_call_at: datetime | None
    by_kind: dict[str, int] = field(default_factory=dict)  # "odds" | "scores" | "props"
    by_day: dict[date, int] = field(default_factory=dict)
    last_month_used: int | None = None

    @property
    def status(self) -> Literal["ok", "warning", "paused"]:
        if self.remaining < self.floor:
            return "paused"
        if self.projected > self.monthly_credits:
            return "warning"
        return "ok"


RECENT = timedelta(days=7)


def _month_start(moment: datetime) -> datetime:
    return moment.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _api_calls(db: Session, start: datetime, end: datetime) -> list[OddsFetch]:
    calls = db.scalars(
        select(OddsFetch).where(
            OddsFetch.source == "api",
            OddsFetch.requests_remaining.is_not(None),
            OddsFetch.fetched_at >= start,
            OddsFetch.fetched_at < end,
        )
    ).all()
    return sorted(calls, key=lambda c: (-(c.requests_remaining or 0), c.fetched_at))


def _costs(calls: list[OddsFetch], quota: int) -> list[tuple[OddsFetch, int]]:
    """Each call of one month with what it cost, starting from a full quota."""
    remaining = quota
    costs = []
    for call in calls:
        after = call.requests_remaining or 0
        costs.append((call, max(remaining - after, 0)))
        remaining = min(remaining, after)
    return costs


def credit_usage(db: Session, now: datetime | None = None) -> CreditUsage:
    settings = get_settings()
    quota = settings.odds_api_monthly_credits
    now = now or datetime.now(UTC)
    start = _month_start(now)
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    next_start = start + timedelta(days=days_in_month)

    this_month = _costs(_api_calls(db, start, next_start), quota)
    last_month = _costs(_api_calls(db, _month_start(start - timedelta(days=1)), start), quota)

    by_kind: dict[str, int] = defaultdict(int)
    by_day: dict[date, int] = defaultdict(int)
    for call, cost in this_month:
        if cost:
            by_kind[call.kind] += cost
            by_day[call.fetched_at.date()] += cost
    used = sum(cost for _, cost in this_month)
    remaining = min((c.requests_remaining or 0 for c, _ in this_month), default=quota)

    # Project the rest of the month at the last week's pace (spanning the reset if need be),
    # not this month's: one or two days into a month is too little to go on.
    recent = [(c, cost) for c, cost in last_month + this_month if c.fetched_at > now - RECENT]
    if recent:
        first = min(c.fetched_at for c, _ in last_month + this_month)
        window_days = max(min(RECENT, now - first) / timedelta(days=1), 1)
        per_day = sum(cost for _, cost in recent) / window_days
    else:
        per_day = 0
    projected = round(used + per_day * (next_start - now) / timedelta(days=1))

    return CreditUsage(
        monthly_credits=quota,
        used=used,
        remaining=remaining,
        projected=projected,
        resets_on=next_start.date(),
        floor=settings.scores_min_credits,
        last_call_at=max((c.fetched_at for c, _ in this_month), default=None),
        by_kind=dict(by_kind),
        by_day=dict(sorted(by_day.items())),
        last_month_used=sum(cost for _, cost in last_month) if last_month else None,
    )
