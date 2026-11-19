"""Test configuration — isolated DB/storage and a deterministic owner account."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

ROOT = Path("/tmp/opencode/v2d-tests")
if ROOT.exists():
    shutil.rmtree(ROOT)
ROOT.mkdir(parents=True, exist_ok=True)

os.environ["DATABASE_URL"] = f"sqlite:///{ROOT}/test.db"
os.environ["STORAGE_DIR"] = str(ROOT / "storage")
os.environ["JWT_SECRET"] = "test-secret-that-is-definitely-long-enough-123456"
os.environ["OWNER_EMAILS"] = "owner@test.dev"
os.environ["BILLING_ENABLED"] = "false"
os.environ["QUEUE_BACKEND"] = "thread"
os.environ["ENVIRONMENT"] = "development"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def owner_headers(client):
    r = client.post("/api/auth/register", json={
        "email": "owner@test.dev", "password": "password123", "full_name": "Owner"})
    if r.status_code == 409:
        r = client.post("/api/auth/login", json={
            "email": "owner@test.dev", "password": "password123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def free_headers(client):
    email = f"free-{os.urandom(4).hex()}@test.dev"
    r = client.post("/api/auth/register", json={
        "email": email, "password": "password123", "full_name": "Free"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
