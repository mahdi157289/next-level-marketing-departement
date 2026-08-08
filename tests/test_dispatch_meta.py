"""Dispatch (mission metadata) integration tests.

DB-gated like the rest of tests/test_crm_api.py. We assert on the persisted
PipelineRun.meta via SQL and clean up created rows. The orchestrator pool is
stubbed so no background LLM runner is spawned.
"""
from __future__ import annotations

import os
import uuid
from typing import Optional
from unittest import mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text


def _database_url() -> Optional[str]:
    return os.getenv("DATABASE_URL")


@pytest.fixture
def client():
    from api.main import app

    return TestClient(app)


class _FakePool:
    max_workers = 3

    def submit(self, *a, **kw):
        return None

    def active_count(self):
        return 0

    def queued_count(self):
        return 0


def test_dispatch_records_mission_metadata(client):
    if not _database_url():
        pytest.skip("DATABASE_URL not set")
    from crm import orchestrator

    mission = f"pytest-mission-{uuid.uuid4().hex[:8]}"
    with mock.patch.object(orchestrator, "pool", return_value=_FakePool()):
        r = client.post(
            "/api/agents/head/dispatch",
            json={"seed_query": None, "mission": mission},
        )
    assert r.status_code == 201, r.text
    run_id = r.json()["id"]
    eng = create_engine(_database_url())
    try:
        with eng.connect() as conn:
            row = conn.execute(
                text("SELECT meta FROM pipeline_runs WHERE id = :id"),
                {"id": run_id},
            ).fetchone()
        assert row is not None, "pipeline_runs row not found"
        meta = row[0] or {}
        assert meta.get("mission") == mission, meta
        assert meta.get("from_agent") == "head", meta
        assert meta.get("mode") == "dispatch", meta
    finally:
        with eng.begin() as conn:
            conn.execute(text("DELETE FROM pipeline_runs WHERE id = :id"), {"id": run_id})
        eng.dispose()


def test_dispatch_unknown_agent_returns_404(client):
    if not _database_url():
        pytest.skip("DATABASE_URL not set")
    r = client.post(
        "/api/agents/definitely-not-an-agent/dispatch",
        json={"seed_query": "x", "mission": "y"},
    )
    assert r.status_code == 404, r.text
