from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.db import Base, get_db
from app.main import app
from app.models import *  # noqa: F401,F403 (registers all models on Base.metadata)

# Tests run against a separate database on the same Postgres server as local dev.
TEST_DATABASE_URL = make_url(get_settings().database_url).set(database="fake_sportsbook_test")


@pytest.fixture(scope="session")
def engine():
    admin = create_engine(TEST_DATABASE_URL.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": TEST_DATABASE_URL.database},
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{TEST_DATABASE_URL.database}"'))
    admin.dispose()

    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db(engine) -> Generator[Session, None, None]:
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestSession()
    yield session
    session.close()
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


@pytest.fixture
def client(db: Session) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/register",
        json={"email": "fixture@example.com", "password": "hunter22!", "display_name": "Fix"},
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture(autouse=True)
def email_settings(monkeypatch: pytest.MonkeyPatch):
    """No real email in tests, and verification off unless a test opts in (`verification_on`)."""
    from app.services import email

    settings = get_settings()
    monkeypatch.setattr(settings, "email_backend", "memory")
    monkeypatch.setattr(settings, "email_verification_required", False)
    email.outbox.clear()
    yield
    email.outbox.clear()


@pytest.fixture
def verification_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "email_verification_required", True)


@pytest.fixture(autouse=True)
def in_season_sports(monkeypatch: pytest.MonkeyPatch):
    """Never call The Odds API's /sports from tests: treat every enabled sport as in season
    when a test sets an API key, and reset the module's cache between tests."""
    from app.services import odds
    from app.sports import SPORTS

    monkeypatch.setattr(odds, "_active_cache", None)
    monkeypatch.setattr(
        odds, "fetch_active_sport_keys", lambda: frozenset(s.api_key for s in SPORTS)
    )
