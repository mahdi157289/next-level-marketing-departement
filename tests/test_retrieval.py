"""P6 — knowledge/retrieval.py default_domain + build_brain_context."""

from __future__ import annotations

import pytest


def test_default_domain_uses_profile_field(monkeypatch):
    from crm import service
    from knowledge import retrieval

    monkeypatch.setattr(service, "get_agent_profile", lambda name: {"default_domain": "tn"})
    assert retrieval.default_domain("discovery") == "tn"


def test_default_domain_falls_back_to_global(monkeypatch):
    from crm import service
    from knowledge import retrieval

    monkeypatch.setattr(service, "get_agent_profile", lambda name: None)
    assert retrieval.default_domain("discovery") == "global"


def test_default_domain_never_raises(monkeypatch):
    from crm import service
    from knowledge import retrieval

    def boom(name):
        raise RuntimeError("db down")

    monkeypatch.setattr(service, "get_agent_profile", boom)
    assert retrieval.default_domain("discovery") == "global"


def test_build_brain_context_formats_results(monkeypatch):
    from knowledge import rag, retrieval

    monkeypatch.setattr(retrieval, "default_domain", lambda name: "tn")
    payload = {
        "results": [
            {"type": "chunk", "content": "Tunisia agency", "source": "leads/1"},
            {"type": "lead", "content": "Acme", "source": "https://acme.tn"},
        ]
    }
    monkeypatch.setattr(rag, "scoped_query", lambda a, d, q, limit=5: payload)
    ctx = retrieval.build_brain_context("discovery", "web agency")
    assert "## Brain context" in ctx
    assert "[chunk] Tunisia agency (leads/1)" in ctx
    assert "[lead] Acme (https://acme.tn)" in ctx


def test_build_brain_context_empty_when_no_results(monkeypatch):
    from knowledge import rag, retrieval

    monkeypatch.setattr(retrieval, "default_domain", lambda name: "tn")
    monkeypatch.setattr(rag, "scoped_query", lambda a, d, q, limit=5: {"results": []})
    assert retrieval.build_brain_context("discovery", "x") == ""


def test_build_brain_context_never_raises(monkeypatch):
    from knowledge import rag, retrieval

    monkeypatch.setattr(retrieval, "default_domain", lambda name: "tn")

    def boom(a, d, q, limit=5):
        raise RuntimeError("graph down")

    monkeypatch.setattr(rag, "scoped_query", boom)
    assert retrieval.build_brain_context("discovery", "x") == ""
