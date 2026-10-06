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
