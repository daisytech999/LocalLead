import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("JWT_SECRET", "test-secret")

from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers(client):
    r = client.post(
        "/api/auth/signup",
        json={"name": "Test", "email": "test@example.com", "password": "password123"},
    )
    assert r.status_code == 201
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def stub_places(monkeypatch):
    """Patch Google Places everywhere it's imported, with a controllable result."""
    state = {
        "results": [
            {"place_id": "p1", "name": "Joe's Plumbing", "address": "1247 Orange Ave",
             "phone": "4075550148", "website": None, "rating": 4.6, "review_count": 47},
            {"place_id": "p2", "name": "Beta Drain", "address": "5 Main St",
             "phone": "4075550199", "website": None, "rating": 4.0, "review_count": 8},
        ]
    }

    def fake_search(category, city, limit=20):
        return list(state["results"])

    from app.routers import leads as leads_router
    from app.services import alerts as alerts_service

    monkeypatch.setattr(leads_router.places, "search_businesses", fake_search)
    monkeypatch.setattr(alerts_service.places, "search_businesses", fake_search)
    return state
