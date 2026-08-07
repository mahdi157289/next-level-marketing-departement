"""P4 — knowledge/graph.py (unit tests, no live JanusGraph required)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest


def _unreachable_settings(monkeypatch):
    from knowledge import graph

    graph.reset_connection()
    monkeypatch.setattr(
        graph, "get_settings", lambda: SimpleNamespace(janusgraph_base_url="ws://127.0.0.1:1/gremlin")
    )


def test_graph_available_false_when_unreachable(monkeypatch):
    from knowledge import graph

    _unreachable_settings(monkeypatch)
    assert graph.graph_available() is False


def test_expand_related_leads_falls_back_to_empty(monkeypatch):
    from knowledge import graph

    _unreachable_settings(monkeypatch)
    assert graph.expand_related_leads(["web"], "tn", limit=5) == []


def test_graph_stats_reports_unavailable(monkeypatch):
    from knowledge import graph

    _unreachable_settings(monkeypatch)
    stats = graph.graph_stats()
    assert stats["available"] is False


def test_ingest_all_from_db_raises_when_unreachable(monkeypatch):
    from knowledge import graph

    _unreachable_settings(monkeypatch)
    with pytest.raises(graph.GraphUnavailable):
        graph.ingest_all_from_db()


def test_expand_traversal_builds_without_server():
    # Building a traversal must not require a connection.
    from gremlin_python.structure.graph import Graph

    from knowledge import graph

    g = Graph().traversal()
    tr = graph._expand_traversal(g, ["web"], "tn", 5)
    assert tr is not None
