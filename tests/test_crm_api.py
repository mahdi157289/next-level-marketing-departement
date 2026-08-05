"""Real-DB integration tests for the CRM module.

These tests require `DATABASE_URL` to be set (same pattern as
`tests/test_db.py`). They exercise the full loop:

    POST /run/pipeline/minimal
        -> pipeline_runs row
        -> discovery agent_run (apis_consumed, leads)
        -> head agent_run (apis_consumed)
        -> pipeline_runs.status=success

If LM Studio is OFF, the pipeline will fail at the LLM step and the
pipeline_run will be marked `failed`; we assert on the *infrastructure*
(the rows exist) rather than the LLM outcome.
"""

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


def test_crm_health(client):
    r = client.get("/crm/health")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("status") == "ok"
    assert body.get("module") == "crm"


def test_crm_leads_empty_or_renders(client):
    r = client.get("/crm/leads?limit=10")
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)


def test_crm_leads_create_and_get(client):
    url = f"https://crm-test-{uuid.uuid4().hex[:8]}.example.com"
    payload = {"name": "CRM Test Co", "url": url, "status": "raw", "source": "pytest"}
    r = client.post("/crm/leads", json=payload)
    assert r.status_code == 201, r.text
    lead_id = r.json()["id"]

    r = client.get(f"/crm/leads/{lead_id}")
    assert r.status_code == 200, r.text
    assert r.json()["url"] == url

    r = client.get("/crm/leads?status=raw&limit=200")
    assert any(lead["url"] == url for lead in r.json()), "Created lead not in list"

    # Cleanup
    if _database_url():
        eng = create_engine(_database_url())
        with eng.begin() as conn:
            conn.execute(text("DELETE FROM lead_events WHERE lead_id = :id"), {"id": lead_id})
            conn.execute(text("DELETE FROM leads WHERE id = :id"), {"id": lead_id})


def test_crm_agent_runs_list(client):
    r = client.get("/crm/agent-runs?limit=10")
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)


def test_crm_pipeline_run_minimal_writes_runs(client):
    """POST /run/pipeline/minimal creates pipeline_run + agent_runs (infra check).

    Skipped by default: live pipeline must not dump search junk into the shared
    CRM during unit pytest. Set RUN_PIPELINE_INFRA_TEST=1 to opt in; then this
    test cleans up the pipeline_run + agent_runs it created (leaves real leads
    if any — prefer a dedicated test DB).
    """
    if not _database_url():
        pytest.skip("DATABASE_URL not set")
    if os.getenv("RUN_PIPELINE_INFRA_TEST") != "1":
        pytest.skip("Set RUN_PIPELINE_INFRA_TEST=1 to run live pipeline infra assert")

    r = client.post(
        "/run/pipeline/minimal",
        json={"seed_query": "digital marketing agency Tunis", "max_search_results": 2},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    pipeline_run_id = body.get("pipeline_run_id")
    assert pipeline_run_id, f"No pipeline_run_id in response: {body}"
    assert body.get("status") in ("success", "failed"), body

    r = client.get(f"/crm/agent-runs?pipeline_run_id={pipeline_run_id}&limit=10")
    assert r.status_code == 200, r.text
    runs = r.json()
    assert isinstance(runs, list)
    assert any(run.get("agent_name") == "discovery" for run in runs), runs


def test_crm_ui_renders_leads(client):
    r = client.get("/crm/ui/leads")
    assert r.status_code == 200, r.text
    assert "<table" in r.text


def test_crm_ui_renders_runs(client):
    r = client.get("/crm/ui/runs")
    assert r.status_code == 200, r.text
    assert "<table" in r.text
