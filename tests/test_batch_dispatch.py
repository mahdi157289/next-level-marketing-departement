"""P6 — POST /api/agents/{name}/batch (hermetic shape; DB-gated enqueue)."""

from __future__ import annotations

import os
from typing import Optional
from unittest import mock

import pytest
from fastapi.testclient import TestClient


def _database_url() -> Optional[str]:
    return os.getenv("DATABASE_URL")


@pytest.fixture
def client():
    from api.main import app

    return TestClient(app)


def _run_dict(run_id: str, seed: str) -> dict:
    return {
        "id": run_id,
        "trigger": "agent:head",
        "seed_query": seed,
        "status": "running",
        "started_at": None,
        "finished_at": None,
        "meta": {"mode": "dispatch"},
    }


def test_batch_dispatch_shape_with_mocked_enqueue(client):
    """Hermetic (no DB): route returns {runs: [...]} in order, 201."""
    from crm import orchestrator

    fake_runs = [_run_dict("r1", "s1"), _run_dict("r2", "s2")]
    with mock.patch.object(orchestrator, "enqueue_run", side_effect=fake_runs):
        r = client.post(
            "/api/agents/head/batch",
            json={"missions": [{"seed_query": "s1"}, {"seed_query": "s2"}]},
        )
    assert r.status_code == 201, r.text
    assert [x["id"] for x in r.json()["runs"]] == ["r1", "r2"]


def test_batch_dispatch_unknown_agent_404(client):
    from crm import orchestrator

    with mock.patch.object(orchestrator, "enqueue_run", side_effect=ValueError("No runner")):
        r = client.post(
            "/api/agents/nope/batch",
            json={"missions": [{"seed_query": "s1"}]},
        )
    assert r.status_code == 404, r.text


class _FakePool:
    max_workers = 3

    def submit(self, fn, run_id, seed, mission=None):
        pass

    def active_count(self):
        return 0

    def queued_count(self):
        return 0


@pytest.mark.skipif(not _database_url(), reason="DATABASE_URL not set")
def test_batch_dispatch_enqueues_runs(client):
    from sqlalchemy import create_engine, text

    from crm import orchestrator

    fake = _FakePool()
    with mock.patch.object(orchestrator, "pool", return_value=fake):
        r = client.post(
            "/api/agents/head/batch",
            json={
                "missions": [
                    {"seed_query": "s1", "mission": "m1"},
                    {"seed_query": "s2", "mission": "m2"},
                ]
            },
        )
    assert r.status_code == 201, r.text
    runs = r.json()["runs"]
    assert len(runs) == 2
    run_ids = [x["id"] for x in runs]

    eng = create_engine(_database_url())
    try:
        with eng.connect() as conn:
            for rid in run_ids:
                row = conn.execute(
                    text("SELECT trigger, seed_query, meta FROM pipeline_runs WHERE id = :id"),
                    {"id": rid},
                ).fetchone()
                assert row is not None, f"run {rid} not found"
                trigger, seed, meta = row
                assert trigger == "agent:head"
                assert meta["from_agent"] == "head"
                assert meta["mode"] == "dispatch"
    finally:
        with eng.begin() as conn:
            for rid in run_ids:
                conn.execute(
                    text("DELETE FROM pipeline_runs WHERE id = :id"), {"id": rid}
                )
        eng.dispose()
