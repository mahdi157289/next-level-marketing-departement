"""Agent chat engine — pure logic, mocked LLM + tools + service."""
from __future__ import annotations

import pytest


class _FakeProfile:
    def __init__(self, **kw):
        self.model = kw.get("model", "head-model")
        self.mission_prompt = kw.get("mission_prompt", "You are the Head Agent.")
        self.enabled_tools = kw.get("enabled_tools", ["llm_chat"])

    def get(self, key, default=None):
        return getattr(self, key, default)


def test_run_agent_turn_uses_agent_profile(monkeypatch):
    from crm import scout

    recorded = []
    monkeypatch.setattr(
        scout.service, "get_agent_profile",
        lambda name: _FakeProfile() if name == "head" else None,
    )

    def fake_add(*a, **kw):
        role = kw.get("role") if len(a) < 2 else a[1]
        recorded.append({"role": role, "agent_name": kw.get("agent_name")})
        return {"id": f"m{len(recorded)}"}

    monkeypatch.setattr(scout.service, "add_scout_message", fake_add)
    monkeypatch.setattr(scout.service, "list_scout_messages", lambda tid, limit=200: [])
    monkeypatch.setattr(
        scout.lm_client,
        "chat_completion_tools",
        lambda model, messages, tools, **kw: {"content": "Plan ready.", "tool_calls": []},
    )
    monkeypatch.setattr(scout.lm_client, "chat_completion", lambda *a, **kw: "Plan ready.")

    out = scout.run_agent_turn("head", "thread-1", "plan this")

    assert out["assistant"] == "Plan ready."
    assert recorded[0] == {"role": "user", "agent_name": "head"}
    assert recorded[-1]["role"] == "assistant"
    assert recorded[-1]["agent_name"] == "head"


def test_run_agent_turn_advertises_no_tools_for_llm_only(monkeypatch):
    from crm import scout

    seen_tools = {}

    def fake_tools(model, messages, tools, **kw):
        seen_tools["tools"] = tools
        return {"content": "ok", "tool_calls": []}

    monkeypatch.setattr(scout.service, "get_agent_profile", lambda name: _FakeProfile(enabled_tools=["llm_chat"]))
    monkeypatch.setattr(scout.service, "add_scout_message", lambda *a, **kw: {"id": "m"})
    monkeypatch.setattr(scout.service, "list_scout_messages", lambda tid, limit=200: [])
    monkeypatch.setattr(scout.lm_client, "chat_completion_tools", fake_tools)

    scout.run_agent_turn("head", "thread-1", "hi")

    assert seen_tools["tools"] == []


def test_run_scout_turn_still_delegates_to_discovery(monkeypatch):
    from crm import scout

    def fake_tools(model, messages, tools, **kw):
        return {"content": "Scout answer.", "tool_calls": []}

    monkeypatch.setattr(scout.service, "get_agent_profile", lambda name: _FakeProfile())
    monkeypatch.setattr(scout.service, "add_scout_message", lambda *a, **kw: {"id": "m"})
    monkeypatch.setattr(scout.service, "list_scout_messages", lambda tid, limit=200: [])
    monkeypatch.setattr(scout.lm_client, "chat_completion_tools", fake_tools)
    monkeypatch.setattr(scout.lm_client, "chat_completion", lambda *a, **kw: "Scout answer.")

    out = scout.run_scout_turn("thread-1", "hello")

    assert out["assistant"] == "Scout answer."
