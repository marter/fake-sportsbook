from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


def register(client: TestClient, email: str) -> dict[str, str]:
    token = client.post(
        "/api/auth/register",
        json={"email": email, "password": "hunter22!", "display_name": email.split("@")[0]},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def make_admin(db: Session, email: str) -> None:
    user = db.scalars(select(User).where(User.email == email)).one()
    user.is_admin = True
    db.commit()


def user_id(db: Session, email: str) -> str:
    return str(db.scalars(select(User.id).where(User.email == email)).one())


def test_admin_endpoints_require_admin(client: TestClient, db: Session) -> None:
    pat = register(client, "pat@example.com")
    assert client.get("/api/auth/me", headers=pat).json()["is_admin"] is False
    assert client.get("/api/admin/users", headers=pat).status_code == 403
    adjust = client.post(
        f"/api/admin/users/{user_id(db, 'pat@example.com')}/adjust",
        json={"amount_cents": 1_000_000},
        headers=pat,
    )
    assert adjust.status_code == 403
    assert client.get("/api/auth/me", headers=pat).json()["balance_cents"] == 100_000


def test_admin_adjusts_balance_with_ledger_entry(client: TestClient, db: Session) -> None:
    admin = register(client, "boss@example.com")
    make_admin(db, "boss@example.com")
    pat = register(client, "pat@example.com")
    pat_id = user_id(db, "pat@example.com")

    users = client.get("/api/admin/users", headers=admin).json()
    assert [u["email"] for u in users] == ["boss@example.com", "pat@example.com"]

    added = client.post(
        f"/api/admin/users/{pat_id}/adjust",
        json={"amount_cents": 50_000, "note": "Won the office pool"},
        headers=admin,
    )
    assert added.status_code == 200, added.text
    assert added.json()["balance_after_cents"] == 150_000

    exact = client.post(
        f"/api/admin/users/{pat_id}/adjust", json={"set_balance_cents": 2_500}, headers=admin
    )
    assert exact.json()["amount_cents"] == 2_500 - 150_000
    assert client.get("/api/auth/me", headers=pat).json()["balance_cents"] == 2_500

    ledger = client.get("/api/wallet/ledger", headers=pat).json()
    assert [e["kind"] for e in ledger] == ["admin_adjustment", "admin_adjustment", "signup_bonus"]
    assert ledger[1]["note"] == "Won the office pool"
    assert sum(e["amount_cents"] for e in ledger) == 2_500


def test_admin_adjustment_validation(client: TestClient, db: Session) -> None:
    admin = register(client, "boss@example.com")
    make_admin(db, "boss@example.com")
    register(client, "pat@example.com")
    url = f"/api/admin/users/{user_id(db, 'pat@example.com')}/adjust"

    below_zero = client.post(url, json={"amount_cents": -100_001}, headers=admin)
    assert below_zero.status_code == 400
    both = client.post(url, json={"amount_cents": 1, "set_balance_cents": 5}, headers=admin)
    assert both.status_code == 422
    neither = client.post(url, json={"note": "hi"}, headers=admin)
    assert neither.status_code == 422
    same = client.post(url, json={"set_balance_cents": 100_000}, headers=admin)
    assert same.status_code == 400


def test_admin_can_view_another_users_bets(client: TestClient, db: Session) -> None:
    admin = register(client, "boss@example.com")
    make_admin(db, "boss@example.com")
    pat = register(client, "pat@example.com")
    pat_id = user_id(db, "pat@example.com")

    game = client.get("/api/games", headers=pat).json()["games"][0]
    line = game["odds_lines"][0]
    client.post(
        "/api/bets",
        json={
            "odds_line_id": line["id"],
            "stake_cents": 1_500,
            "expected_price_american": line["price_american"],
            "expected_point": line["point"],
        },
        headers=pat,
    )

    body = client.get(f"/api/admin/users/{pat_id}/bets?state=open", headers=admin).json()
    assert body["user"]["email"] == "pat@example.com"
    assert [b["stake_cents"] for b in body["bets"]] == [1_500]
    assert body["bets"][0]["legs"][0]["game"]["id"] == game["id"]
    settled = client.get(f"/api/admin/users/{pat_id}/bets?state=settled", headers=admin).json()
    assert settled["bets"] == []


def test_only_admins_can_view_other_users_bets(client: TestClient, db: Session) -> None:
    register(client, "boss@example.com")
    pat = register(client, "pat@example.com")
    boss_id = user_id(db, "boss@example.com")
    assert client.get(f"/api/admin/users/{boss_id}/bets", headers=pat).status_code == 403

    # Someone else being an admin doesn't let pat in.
    make_admin(db, "boss@example.com")
    assert client.get(f"/api/admin/users/{boss_id}/bets", headers=pat).status_code == 403


def test_view_bets_of_unknown_user_is_404(client: TestClient, db: Session) -> None:
    admin = register(client, "boss@example.com")
    make_admin(db, "boss@example.com")
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/api/admin/users/{missing}/bets", headers=admin).status_code == 404
