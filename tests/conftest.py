"""Tests run against an in-memory database so they never touch the demo file."""

from __future__ import annotations

import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SEED_DEMO_DATA"] = "true"

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import SessionLocal
from app.main import app

settings.rate_limit_per_min = 0  # tests that need the limiter switch it on themselves


@pytest.fixture(scope="session")
def client():
    # Context manager runs the lifespan: create tables, then seed demo data.
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def db():
    session = SessionLocal()
    yield session
    session.close()
