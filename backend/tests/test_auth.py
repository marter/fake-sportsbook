from fastapi.testclient import TestClient

from app.core.config import get_settings


def register(client: TestClient, email: str = "pat@example.com") -> str:
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": "hunter22!", "display_name": "Pat"},
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


def test_register_grants_starting_balance(client: TestClient) -> None:
    token = register(client)
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    body = response.json()
    assert body["display_name"] == "Pat"
    assert body["balance_cents"] == get_settings().starting_balance_cents


def test_register_rejects_duplicate_email_case_insensitively(client: TestClient) -> None:
    register(client, "pat@example.com")
    response = client.post(
        "/api/auth/register",
        json={"email": "PAT@example.com", "password": "hunter22!", "display_name": "Pat 2"},
    )
    assert response.status_code == 400


def test_login(client: TestClient) -> None:
    register(client)
    ok = client.post(
        "/api/auth/login", json={"email": "pat@example.com", "password": "hunter22!"}
    )
    assert ok.status_code == 200
    assert ok.json()["access_token"]

    bad = client.post("/api/auth/login", json={"email": "pat@example.com", "password": "nope"})
    assert bad.status_code == 401


def test_me_requires_auth(client: TestClient) -> None:
    assert client.get("/api/auth/me").status_code == 401
