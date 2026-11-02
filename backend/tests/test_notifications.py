import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services import email
from tests.test_admin import make_admin, register


def test_admins_are_emailed_about_new_accounts(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "max_users", 4)
    register(client, "boss@example.com")
    register(client, "deputy@example.com")
    make_admin(db, "boss@example.com")
    make_admin(db, "deputy@example.com")
    email.outbox.clear()

    register(client, "pat@example.com")
    assert sorted(m.to for m in email.outbox) == ["boss@example.com", "deputy@example.com"]
    message = email.outbox[0]
    assert "pat" in message.subject
    assert "pat@example.com" in message.text
    assert "3 of 4 accounts. 1 sign-up slot left." in message.text
    assert f"{get_settings().app_base_url}/admin" in message.text

    email.outbox.clear()
    register(client, "sam@example.com")
    assert "Sign-ups are now closed" in email.outbox[0].text


def test_no_admins_means_no_notice(client: TestClient) -> None:
    register(client, "pat@example.com")
    assert email.outbox == []


def test_a_failed_notice_doesnt_fail_sign_up(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    register(client, "boss@example.com")
    make_admin(db, "boss@example.com")

    def broken(_message: email.Email) -> None:
        raise email.EmailError("mail provider is down")

    monkeypatch.setattr(email, "send", broken)
    response = client.post(
        "/api/auth/register",
        json={"email": "pat@example.com", "password": "hunter22!", "display_name": "pat"},
    )
    assert response.status_code == 201
