from datetime import UTC, date, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.game import OddsFetch
from app.services.api_usage import credit_usage
from tests.test_admin import make_admin, register


def log_call(db: Session, when: datetime, kind: str, remaining: int, source: str = "api") -> None:
    db.add(
        OddsFetch(
            sport_key="americanfootball_nfl",
            kind=kind,
            fetched_at=when,
            source=source,
            event_count=1,
            requests_remaining=remaining,
        )
    )
    db.commit()


def test_usage_adds_up_drops_by_kind(db: Session) -> None:
    log_call(db, datetime(2026, 10, 20, tzinfo=UTC), "odds", 181)  # last month
    log_call(db, datetime(2026, 11, 1, 1, tzinfo=UTC), "odds", 497)  # reset to 500, then 3
    log_call(db, datetime(2026, 11, 3, 18, tzinfo=UTC), "scores", 495)
    log_call(db, datetime(2026, 11, 4, 12, tzinfo=UTC), "props", 491)
    # Logged a moment out of order by the other process: still costs 3, not -3 then 6.
    log_call(db, datetime(2026, 11, 4, 11, 59, tzinfo=UTC), "odds", 488)
    log_call(db, datetime(2026, 11, 4, 13, tzinfo=UTC), "odds", 0, source="fixture")  # ignored

    usage = credit_usage(db, now=datetime(2026, 11, 6, tzinfo=UTC))
    assert usage.used == 12
    assert usage.remaining == 488
    assert usage.by_kind == {"odds": 6, "scores": 2, "props": 4}
    assert usage.by_day == {date(2026, 11, 1): 3, date(2026, 11, 3): 2, date(2026, 11, 4): 7}
    # 12 credits in the last 7 days, then 25 more days at that pace.
    assert usage.projected == 55
    assert usage.resets_on == date(2026, 12, 1)
    assert usage.last_month_used == 319
    assert usage.status == "ok"


def test_projection_uses_the_last_week_across_the_reset(db: Session) -> None:
    for day in range(24, 32):  # 10 credits a day at the end of October
        log_call(db, datetime(2026, 10, day, 12, tzinfo=UTC), "odds", 500 - 10 * (day - 23))
    log_call(db, datetime(2026, 11, 1, 12, tzinfo=UTC), "odds", 490)
    usage = credit_usage(db, now=datetime(2026, 11, 2, tzinfo=UTC))
    # Month-to-date alone would say ~150 (10 in a day); the week says 10/day for 29 more days.
    assert usage.used == 10
    assert usage.projected == 300


def test_usage_status_warns_then_pauses(db: Session) -> None:
    log_call(db, datetime(2026, 11, 5, tzinfo=UTC), "odds", 200)
    assert credit_usage(db, now=datetime(2026, 11, 10, tzinfo=UTC)).status == "warning"
    log_call(db, datetime(2026, 11, 9, tzinfo=UTC), "scores", 40)
    assert credit_usage(db, now=datetime(2026, 11, 10, tzinfo=UTC)).status == "paused"


def test_no_calls_yet_this_month(db: Session) -> None:
    usage = credit_usage(db, now=datetime(2026, 11, 1, 6, tzinfo=UTC))
    assert (usage.used, usage.remaining, usage.projected) == (0, 500, 0)
    assert usage.last_call_at is None
    assert usage.last_month_used is None


def test_api_usage_endpoint_is_admin_only(client: TestClient, db: Session) -> None:
    pat = register(client, "pat@example.com")
    assert client.get("/api/admin/api-usage", headers=pat).status_code == 403
    make_admin(db, "pat@example.com")
    body = client.get("/api/admin/api-usage", headers=pat).json()
    assert body["monthly_credits"] == 500
    assert body["status"] == "ok"
    assert body["by_day"] == []
