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


def test_enabled_tools_gate(monkeypatch):
    """A tool the model names but that is not in enabled_tools is refused and never resolved."""
    from crm import scout

    profile = _FakeProfile()
    profile.enabled_tools = ["web_search"]
    monkeypatch.setattr(scout.service, "get_agent_profile", lambda name: profile)

    recorded = []

    def fake_add(*a, **kw):
        role = a[1] if len(a) > 1 else kw.get("role")
        recorded.append({"role": role, "kwargs": dict(kw)})
        return {"id": f"m{len(recorded)}"}

    monkeypatch.setattr(scout.service, "add_scout_message", fake_add)
    monkeypatch.setattr(scout.service, "list_scout_messages", lambda tid, limit=200: [])

    counter = {"n": 0}

    def fake_tools(model, messages, tools, **kw):
        counter["n"] += 1
        if counter["n"] == 1:
            return {
                "content": "",
                "tool_calls": [
                    {"id": "c1", "name": "meta_ads_search", "arguments": {"query": "ads"}},
                ],
            }
        if counter["n"] == 2:
            return {
                "content": "",
                "tool_calls": [
                    {"id": "c2", "name": "web_search", "arguments": {"query": "plumber", "max_results": 2}},
                ],
            }
        return {"content": "Found leads.", "tool_calls": []}

    monkeypatch.setattr(scout.lm_client, "chat_completion_tools", fake_tools)

    def fake_resolve(name):
        if name == "meta_ads_search":
            raise AssertionError("resolve_callable('meta_ads_search') must not be called")
        if name == "web_search":
            return lambda **kw: [{"title": "A", "url": "http://a.tn"}]
        return None

    monkeypatch.setattr(scout.registry, "resolve_callable", fake_resolve)

    out = scout.run_scout_turn("thread-gate", "find me a plumber")
    assert out["tool_calls"] == 2
    assert out["assistant"] == "Found leads."

    roles = [r["role"] for r in recorded]
    assert roles[0] == "user"
    assert roles[-1] == "assistant"

    tool_msgs = [r for r in recorded if r["role"] == "tool"]
    meta = [r for r in tool_msgs if r["kwargs"].get("tool_name") == "meta_ads_search"]
    assert len(meta) == 1
    assert meta[0]["kwargs"]["tool_result"]["error"] == "tool meta_ads_search not enabled"

    web = [r for r in tool_msgs if r["kwargs"].get("tool_name") == "web_search"]
    assert len(web) == 1
    assert web[0]["kwargs"]["tool_result"]["error"] is None
