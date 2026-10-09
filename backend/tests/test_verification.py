import re
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.user import User
from app.models.verification import EmailVerificationToken
from app.services import email
from tests.test_bets import bet_payload, first_line

pytestmark = pytest.mark.usefixtures("verification_on")


def register(client: TestClient, address: str = "pat@example.com") -> dict[str, str]:
    response = client.post(
        "/api/auth/register",
        json={"email": address, "password": "hunter22!", "display_name": address.split("@")[0]},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def link_token(message: email.Email) -> str:
    match = re.search(r"/verify-email\?token=([\w-]+)", message.text)
    assert match, message.text
    return match.group(1)


def test_signup_sends_link_and_blocks_betting_until_verified(client: TestClient) -> None:
    headers = register(client)
    assert client.get("/api/auth/me", headers=headers).json()["email_verified"] is False

    assert len(email.outbox) == 1
    message = email.outbox[0]
    assert message.to == "pat@example.com"
    assert get_settings().app_base_url in message.text
    token = link_token(message)

    line = first_line(client, headers)
    blocked = client.post("/api/bets", json=bet_payload(line), headers=headers)
    assert blocked.status_code == 403
    assert "verify" in blocked.json()["detail"].lower()

    # The link works without being logged in.
    verified = client.post("/api/auth/verify-email", json={"token": token})
    assert verified.status_code == 200
    assert verified.json()["email_verified"] is True
    assert client.post("/api/bets", json=bet_payload(line), headers=headers).status_code == 201

    # Clicking the same link again is harmless.
    assert client.post("/api/auth/verify-email", json={"token": token}).status_code == 200


def test_bad_and_expired_links(client: TestClient, db: Session) -> None:
    register(client)
    token = link_token(email.outbox[0])

    bad = client.post("/api/auth/verify-email", json={"token": "x" * 43})
    assert bad.status_code == 400

    db.execute(
        update(EmailVerificationToken).values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    )
    db.commit()
    expired = client.post("/api/auth/verify-email", json={"token": token})
    assert expired.status_code == 400
    assert "expired" in expired.json()["detail"]


def test_resend_is_rate_limited(client: TestClient, db: Session) -> None:
    headers = register(client)
    # Sign-up just sent one, so an immediate resend is too soon.
    assert client.post("/api/auth/resend-verification", headers=headers).status_code == 429

    def age_tokens(minutes: int) -> None:
        db.execute(
            update(EmailVerificationToken).values(
                issued_at=EmailVerificationToken.issued_at - timedelta(minutes=minutes)
            )
        )
        db.commit()

    for _ in range(4):
        age_tokens(2)
        assert client.post("/api/auth/resend-verification", headers=headers).status_code == 204
    assert len(email.outbox) == 5
    age_tokens(2)
    too_many = client.post("/api/auth/resend-verification", headers=headers)
    assert too_many.status_code == 429
    assert "tomorrow" in too_many.json()["detail"]

    # Any of the links works; the newest one verifies.
    newest = link_token(email.outbox[-1])
    assert client.post("/api/auth/verify-email", json={"token": newest}).status_code == 200
    assert client.post("/api/auth/resend-verification", headers=headers).status_code == 400


def test_stale_unverified_accounts_are_deleted_to_free_slots(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "max_users", 2)
    register(client, "real@example.com")
    verify_token = link_token(email.outbox[0])
    client.post("/api/auth/verify-email", json={"token": verify_token})
    register(client, "typo@exmaple.com")
    assert client.get("/api/auth/registration").json() == {"open": False}

    # Two days later the typo'd account never verified.
    db.execute(
        text("UPDATE users SET created_at = created_at - interval '49 hours' WHERE email = :e"),
        {"e": "typo@exmaple.com"},
    )
    db.commit()
    assert client.get("/api/auth/registration").json() == {"open": True}
    emails = set(db.scalars(select(User.email)).all())
    assert emails == {"real@example.com"}
    register(client, "fixed@example.com")


def test_unverified_users_are_left_off_the_leaderboard(client: TestClient) -> None:
    headers = register(client, "real@example.com")
    client.post("/api/auth/verify-email", json={"token": link_token(email.outbox[0])})
    register(client, "pending@example.com")
    names = [r["display_name"] for r in client.get("/api/leaderboard", headers=headers).json()]
    assert names == ["real"]


def test_admin_can_verify_or_delete_unverified(client: TestClient, db: Session) -> None:
    admin = register(client, "boss@example.com")
    boss = db.scalars(select(User).where(User.email == "boss@example.com")).one()
    boss.is_admin = True
    boss.email_verified_at = datetime.now(UTC)
    db.commit()
    register(client, "stuck@example.com")
    register(client, "typo@exmaple.com")
    ids = {u["email"]: u["id"] for u in client.get("/api/admin/users", headers=admin).json()}

    marked = client.post(f"/api/admin/users/{ids['stuck@example.com']}/verify", headers=admin)
    assert marked.json()["email_verified"] is True

    typo_delete = client.delete(f"/api/admin/users/{ids['typo@exmaple.com']}", headers=admin)
    assert typo_delete.status_code == 204
    remaining = {u["email"] for u in client.get("/api/admin/users", headers=admin).json()}
    assert remaining == {"boss@example.com", "stuck@example.com"}
