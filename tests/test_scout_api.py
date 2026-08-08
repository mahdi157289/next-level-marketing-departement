"""Scout status + SSE chat endpoint (engine mocked)."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from api.main import app

    return TestClient(app)


def test_scout_status_shape(client):
    r = client.get("/api/scout/status")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "scout_active" in body
    assert "scout_last_seed" in body
    assert "latest_missions" in body
    assert isinstance(body["latest_missions"], list)


def test_scout_chat_sse(client, monkeypatch):
    from api import router as api_router
    import crm.scout as scout_mod

    def fake_run(agent_name, thread_id, user_text, **kw):
        return {"thread_id": thread_id, "assistant": "done", "tool_calls": 0, "message_ids": ["m1"]}

    monkeypatch.setattr(scout_mod, "run_agent_turn", fake_run)
    r = client.post("/api/scout/threads/00000000-0000-0000-0000-000000000001/messages", json={"content": "hello"})
    assert r.status_code == 200, r.text
    assert "text/event-stream" in r.headers["content-type"]
    assert "event: done" in r.text
    assert "done" in r.text


def _parse_sse(raw):
    text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw
    frames = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event = None
        data = None
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data = line.split(":", 1)[1].strip()
        frames.append((event, data))
    return frames


async def test_scout_chat_sse_sequence(monkeypatch):
    """Iterating _agent_chat_events directly yields start -> delta(s) -> done."""
    import crm.scout as scout_mod
    from api import router as api_router

    def fake_run(agent_name, thread_id, user_text, **kw):
        return {
            "thread_id": thread_id,
            "assistant": "A" * 200,
            "tool_calls": 2,
            "message_ids": ["m1"],
        }

    monkeypatch.setattr(scout_mod, "run_agent_turn", fake_run)

    resp = api_router._agent_chat_events(
        "discovery", "00000000-0000-0000-0000-000000000001", "hello"
    )
    frames = []
    async for chunk in resp.body_iterator:
            frames.append(chunk)
    events = _parse_sse("".join(frames))
    kinds = [ev for ev, _ in events]

    assert kinds[0] == "start"
    assert kinds[-1] == "done"
    assert kinds[1:-1] == ["delta"] * len(kinds[1:-1])
    assert len(kinds[1:-1]) > 1  # multi-chunk assistant
    done = json.loads(events[-1][1])
    assert done["tool_calls"] == 2
    assert done["assistant"] == "A" * 200


async def test_scout_chat_sse_error(monkeypatch):
    """An engine exception yields event: error after the start frame."""
    import crm.scout as scout_mod
    from api import router as api_router

    def fake_run(agent_name, thread_id, user_text, **kw):
        raise RuntimeError("engine blew up")

    monkeypatch.setattr(scout_mod, "run_agent_turn", fake_run)

    resp = api_router._agent_chat_events("discovery", "t1", "hi")
    frames = []
    async for chunk in resp.body_iterator:
            frames.append(chunk)
    events = _parse_sse("".join(frames))
    kinds = [ev for ev, _ in events]
    assert kinds == ["start", "error"]
    err = json.loads(events[-1][1])
    assert "engine blew up" in err["detail"]
