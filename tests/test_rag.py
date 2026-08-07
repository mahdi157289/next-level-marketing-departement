"""P4 — knowledge/rag.py scoped_query orchestration (monkeypatched layers)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest


@pytest.fixture
def patch_layers(monkeypatch):
    from knowledge import rag

    calls = {"vector": 0, "graph": 0, "cache_set": 0, "record": 0}
    monkeypatch.setattr(rag, "cache_get", lambda key: None)
    monkeypatch.setattr(
        rag, "cache_set", lambda key, payload: calls.__setitem__("cache_set", calls["cache_set"] + 1)
    )
    monkeypatch.setattr(
        rag, "search_chunks",
        lambda agent, query, scope=None, limit=5: calls.__setitem__("vector", calls["vector"] + 1) or [
            {"source_uri": "leads/1", "content": "Tunisia agency", "similarity": 0.9}
        ],
    )
    monkeypatch.setattr(
        rag, "expand_related_leads",
        lambda terms, domain, limit=5: calls.__setitem__("graph", calls["graph"] + 1) or [
            {"pg_id": "p1", "name": "Acme", "url": "https://acme.tn", "industry": "web"}
        ],
    )
    monkeypatch.setattr(
        rag, "record_query",
        lambda *a, **kw: calls.__setitem__("record", calls["record"] + 1),
    )
    return rag, calls


def test_cache_hit_short_circuits_vector_and_graph(monkeypatch):
    from knowledge import rag

    monkeypatch.setattr(rag, "cache_get", lambda key: {"results": [], "cache_hit": False})
    monkeypatch.setattr(rag, "search_chunks", lambda *a, **kw: pytest.fail("vector called on cache hit"))
    monkeypatch.setattr(rag, "expand_related_leads", lambda *a, **kw: pytest.fail("graph called on cache hit"))
    monkeypatch.setattr(rag, "record_query", lambda *a, **kw: None)
    out = rag.scoped_query("discovery", "tn", "web agency", limit=5)
    assert out["cache_hit"] is True


def test_miss_runs_vector_then_graph_and_caches(patch_layers):
    rag, calls = patch_layers
    out = rag.scoped_query("discovery", "tn", "web agency tunisia", limit=5)
    assert calls["vector"] == 1
    assert calls["graph"] == 1
    assert calls["cache_set"] == 1
    assert calls["record"] == 1
    assert out["cache_hit"] is False
    assert out["vector_hits"] == 1
    assert out["graph_hits"] == 1
    types = {r["type"] for r in out["results"]}
    assert types == {"chunk", "lead"}


def test_graph_down_still_returns_vector(patch_layers, monkeypatch):
    rag, calls = patch_layers
    monkeypatch.setattr(rag, "expand_related_leads", lambda *a, **kw: [])
    out = rag.scoped_query("discovery", "tn", "web agency", limit=5)
    assert out["graph_hits"] == 0
    assert any(r["type"] == "chunk" for r in out["results"])
