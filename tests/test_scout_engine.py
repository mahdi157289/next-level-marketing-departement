"""Scout chat engine — pure logic, mocked LLM + tools + service."""
from __future__ import annotations

import pytest


class _FakeProfile:
    def __init__(self):
        self.model = "scout-model"
        self.mission_prompt = "You are the Scout."
        self.enabled_tools = ["web_search", "google_maps_search", "llm_chat"]

    def get(self, key, default=None):
        return getattr(self, key, default)


def _patch_service(monkeypatch, msgs=None, created_ids=None):
    from crm import scout

    msgs = msgs or []
    created_ids = created_ids or []

    class _FakeMessages:
        def __init__(self, items):
            self._items = items

        def __len__(self):
            return len(self._items)

        def __getitem__(self, i):
            return self._items[i]

        def __iter__(self):
            return iter(self._items)

    monkeypatch.setattr(scout.service, "get_agent_profile", lambda name: _FakeProfile())
    monkeypatch.setattr(scout.service, "add_scout_message", lambda *a, **kw: {"id": f"m{len(created_ids)}"})
    return _FakeMessages(msgs)


def test_plain_answer_no_tools(monkeypatch):
    from crm import scout
    from crm import service

    _patch_service(monkeypatch)
    monkeypatch.setattr(scout.service, "list_scout_messages", lambda tid, limit=200: [])
    monkeypatch.setattr(
        scout.lm_client,
        "chat_completion_tools",
        lambda model, messages, tools, **kw: {"content": "I checked.", "tool_calls": []},
    )
    monkeypatch.setattr(scout.lm_client, "chat_completion", lambda *a, **kw: "I checked.")

    out = scout.run_scout_turn("thread-1", "hello")
    assert out["assistant"] == "I checked."
    assert out["tool_calls"] == 0


def test_tool_call_roundtrip(monkeypatch):
    from crm import scout

    profile = _FakeProfile()
    profile.enabled_tools = ["web_search", "google_maps_search", "llm_chat"]
    monkeypatch.setattr(scout.service, "get_agent_profile", lambda name: profile)
    monkeypatch.setattr(scout.service, "add_scout_message", lambda *a, **kw: {"id": "x"})
    monkeypatch.setattr(scout.service, "list_scout_messages", lambda tid, limit=200: [])

    # First call requests a tool; second call produces the final answer.
    calls = {"n": 0}

    def fake_tools(model, messages, tools, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "content": "",
                "tool_calls": [
                    {"id": "c1", "name": "web_search", "arguments": {"query": "plumber Tunis", "max_results": 2}}
                ],
            }
        return {"content": "Found leads.", "tool_calls": []}

    monkeypatch.setattr(scout.lm_client, "chat_completion_tools", fake_tools)

    monkeypatch.setattr(
        scout.registry,
        "resolve_callable",
        lambda tid: (lambda **kw: [{"title": "A", "url": "http://a.tn"}]) if tid == "web_search" else None,
    )

    out = scout.run_scout_turn("thread-1", "find me a plumber")
    assert out["tool_calls"] == 1
    assert out["assistant"] == "Found leads."
