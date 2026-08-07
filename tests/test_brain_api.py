"""P4 — /api/brain/* endpoints (mocked brain layers for shape; live DB test gated)."""

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


def test_scoped_query_endpoint_shape(client):
    payload = {"query": "web agency", "domain": "tn", "agent_name": "discovery", "cache_hit": False,
               "vector_hits": 0, "graph_hits": 0, "results": [], "checked_at": "x", "latency_ms": 1}
    with mock.patch("knowledge.rag.scoped_query", return_value=payload) as m:
        r = client.post("/api/brain/scoped_query", json={"agent_name": "discovery", "domain": "tn", "query": "web agency"})
    assert r.status_code == 200
    assert r.json()["query"] == "web agency"
    m.assert_called_once()


def test_graph_status_endpoint_shape(client):
    with mock.patch("knowledge.graph.graph_stats", return_value={"available": False, "vertices": 0, "edges": 0}):
        r = client.get("/api/brain/graph/status")
    assert r.status_code == 200
    assert r.json()["available"] is False


def test_graph_ingest_503_when_unavailable(client):
    from knowledge.graph import GraphUnavailable

    with mock.patch("knowledge.graph.ingest_all_from_db", side_effect=GraphUnavailable("down")):
        r = client.post("/api/brain/graph/ingest")
    assert r.status_code == 503


def test_metrics_endpoint_shape(client):
    with mock.patch("db.brain_metrics.recent_queries", return_value=[]):
        r = client.get("/api/brain/metrics")
    assert r.status_code == 200
    assert r.json() == {"metrics": []}


@pytest.mark.skipif(not _database_url(), reason="DATABASE_URL not set")
def test_metrics_endpoint_live_db(client):
    from db.brain_metrics import record_query

    record_query("pytest", "tn", "live-metrics-hash", 3, True, 0, 0)
    r = client.get("/api/brain/metrics", params={"limit": 5})
    assert r.status_code == 200
    assert any(m["query_hash"] == "live-metrics-hash" for m in r.json()["metrics"])
