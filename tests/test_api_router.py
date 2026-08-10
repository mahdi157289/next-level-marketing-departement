"""Unified /api prefix — reuses the crm router + new scout/pipeline endpoints."""
from __future__ import annotations

import os
import time
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


def test_api_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200, r.text


def test_openapi_unique_operation_ids():
    from api.main import app

    schema = app.openapi()
    ids = []
    for path, methods in schema["paths"].items():
        for method, op in methods.items():
            if isinstance(op, dict) and "operationId" in op:
                ids.append(op["operationId"])
    dupes = len(ids) - len(set(ids))
    print(f"operationId unique={len(set(ids))} total={len(ids)} dupes={dupes}")
    assert dupes == 0
    assert len(ids) > 0


def test_api_leads(client):
    r = client.get("/api/leads?limit=5")
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)


@pytest.mark.skipif(not _database_url(), reason="DATABASE_URL not set")
def test_api_leads_enrich_starts_job(client):
    """POST /api/leads/enrich spawns a Lead Completion background job (202)."""
    from crm import runner
    import workflows.enrich_leads as el

    url = f"https://api-enrich-{uuid.uuid4().hex[:8]}.example.com"
    r = client.post("/api/leads", json={"name": "API Enrich Co", "url": url, "status": "raw", "source": "pytest"})
    assert r.status_code == 201, r.text
    lead_id = r.json()["id"]

    orig = el.enrich_leads
    el.enrich_leads = lambda *a, **k: {"pipeline_run_id": "mocked", "status": "completed", "enriched": 1}
    pid = None
    try:
        r = client.post("/api/leads/enrich", json={"lead_ids": [lead_id]})
        if r.status_code == 409:
            pytest.skip("another job is already running")
        assert r.status_code == 202, r.text
        body = r.json()
        assert body["status"] == "running"
        assert body["target_count"] == 1
        pid = body["pipeline_run_id"]
        assert pid
        for _ in range(100):
            with runner._lock:
                slot = runner._active_enrich
            if slot is None:
                break
            time.sleep(0.05)
    finally:
        el.enrich_leads = orig

    eng = create_engine(_database_url())
    with eng.begin() as conn:
        conn.execute(text("DELETE FROM lead_events WHERE lead_id = :id"), {"id": uuid.UUID(lead_id)})
        conn.execute(text("DELETE FROM leads WHERE id = :id"), {"id": uuid.UUID(lead_id)})
        if pid:
            conn.execute(text("DELETE FROM agent_runs WHERE pipeline_run_id = :p"), {"p": uuid.UUID(pid)})
            conn.execute(text("DELETE FROM pipeline_runs WHERE id = :p"), {"p": uuid.UUID(pid)})
    eng.dispose()


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
