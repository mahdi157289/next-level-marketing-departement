"""Scout status + SSE chat endpoint (engine mocked)."""
from __future__ import annotations

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

    def fake_run(thread_id, user_text, **kw):
        return {"thread_id": thread_id, "assistant": "done", "tool_calls": 0, "message_ids": ["m1"]}

    monkeypatch.setattr(scout_mod, "run_scout_turn", fake_run)
    r = client.post("/api/scout/threads/00000000-0000-0000-0000-000000000001/messages", json={"content": "hello"})
    assert r.status_code == 200, r.text
    assert "text/event-stream" in r.headers["content-type"]
    assert "event: done" in r.text
    assert "done" in r.text
