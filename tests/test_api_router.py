"""Unified /api prefix — reuses the crm router + new scout/pipeline endpoints."""
from __future__ import annotations

import os
import uuid
from typing import Optional

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text


def _database_url() -> Optional[str]:
    return os.getenv("DATABASE_URL")


@pytest.fixture
def client():
    from api.main import app

    return TestClient(app)


def test_api_health_and_crm_prefix(client):
    r = client.get("/api/crm/health")
    assert r.status_code == 200, r.text


def test_api_leads_via_crm_router(client):
    r = client.get("/api/crm/leads?limit=5")
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)


def test_api_pipeline_runs_list(client):
    r = client.get("/api/pipeline-runs?limit=5")
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)


@pytest.mark.skipif(not _database_url(), reason="DATABASE_URL not set")
def test_api_scout_thread_crud(client):
    r = client.post("/api/scout/threads", json={"title": "api test"})
    assert r.status_code == 201, r.text
    thread_id = r.json()["id"]

    r = client.get("/api/scout/threads")
    assert any(t["id"] == thread_id for t in r.json())

    r = client.get(f"/api/scout/threads/{thread_id}/messages")
    assert r.status_code == 200, r.text
    assert r.json() == []

    eng = create_engine(_database_url())
    with eng.begin() as conn:
        conn.execute(text("DELETE FROM scout_messages WHERE thread_id = :id"), {"id": uuid.UUID(thread_id)})
        conn.execute(text("DELETE FROM scout_threads WHERE id = :id"), {"id": uuid.UUID(thread_id)})
    eng.dispose()
