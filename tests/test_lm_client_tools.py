"""chat_completion_tools returns content + parsed tool calls (mocked client)."""
from __future__ import annotations

import pytest


class _FakeMsg:
    content = None
    tool_calls = None
    model_extra = None


class _FakeChoice:
    def __init__(self):
        self.message = _FakeMsg()


class _FakeResp:
    def __init__(self):
        self.choices = [_FakeChoice()]


def test_returns_empty_tool_calls_when_none(monkeypatch):
    from agents import lm_client

    resp = _FakeResp()
    resp.choices[0].message.content = "ok"

    class _FakeClient:
        @property
        def chat(self):
            class _FakeCompletions:
                def create(self, **kwargs):
                    return resp
            class _FakeChat:
                completions = _FakeCompletions()
            return _FakeChat()

    monkeypatch.setattr(lm_client, "_get_client", lambda: _FakeClient())
    out = lm_client.chat_completion_tools("m", [{"role": "user", "content": "hi"}], tools=[])
    assert out["content"] == "ok"
    assert out["tool_calls"] == []


def test_parses_tool_calls(monkeypatch):
    from agents import lm_client

    resp = _FakeResp()
    msg = resp.choices[0].message
    msg.content = "let me search"
    msg.tool_calls = [
        type("TC", (), {
            "id": "call_1",
            "function": type("F", (), {"name": "web_search", "arguments": '{"query": "x", "max_results": 3}'}),
        })()
    ]

    class _FakeClient:
        @property
        def chat(self):
            class _FakeCompletions:
                def create(self, **kwargs):
                    return resp
            class _FakeChat:
                completions = _FakeCompletions()
            return _FakeChat()

    monkeypatch.setattr(lm_client, "_get_client", lambda: _FakeClient())
    out = lm_client.chat_completion_tools("m", [{"role": "user", "content": "find"}], tools=[{"type": "function", "function": {"name": "web_search"}}])
    assert out["content"] == "let me search"
    assert out["tool_calls"][0]["name"] == "web_search"
    assert out["tool_calls"][0]["arguments"]["query"] == "x"
