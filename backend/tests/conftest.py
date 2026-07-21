"""Pytest fixtures. DATA_DIR is pointed at a temp dir before the app imports."""

from __future__ import annotations

import os
import tempfile

# Must be set before any `app.*` import so the engine binds to a throwaway DB.
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="tracker-test-")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def app_client():
    from app.main import app

    with TestClient(app) as client:
        yield client


@pytest.fixture()
def client(app_client):
    """A test client with all tables truncated before each test."""
    from app.db import Base, engine

    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    return app_client
