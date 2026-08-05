"""GET /api/stats — KPI aggregates. Real DB for lead counts; runner mocked."""
from __future__ import annotations

import os
from typing import Optional

import pytest
from fastapi.testclient import TestClient


def _database_url() -> Optional[str]:
    return os.getenv("DATABASE_URL")


@pytest.fixture
def client():
    from api.main import app

    return TestClient(app)


@pytest.mark.skipif(not _database_url(), reason="DATABASE_URL not set")
def test_stats_shape(client):
    r = client.get("/api/stats")
    assert r.status_code == 200, r.text
    body = r.json()
    for key in ("leads_total", "leads_by_status", "leads_avg_score", "runs_today", "run_success_rate", "recent_runs", "scout_active", "scout_last_seed"):
        assert key in body, f"missing {key}"
    assert isinstance(body["leads_by_status"], dict)
    assert isinstance(body["recent_runs"], list)
    assert 0.0 <= body["run_success_rate"] <= 100.0
