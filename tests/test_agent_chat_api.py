"""Agent-scoped chat + prompt API tests."""
from __future__ import annotations

import os
import uuid
from typing import Optional

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text


def _database_url() -> Optional[str]:
    return os.getenv("DATABASE_URL")


@pytest.mark.skipif(not _database_url(), reason="DATABASE_URL not set")
def test_threads_scoped_by_agent():
    from crm import service

    tag = uuid.uuid4().hex[:8]
    head_thread = service.create_scout_thread(f"head-{tag}", agent_name="head")
    discovery_thread = service.create_scout_thread(f"disc-{tag}", agent_name="discovery")
    try:
        heads = service.list_scout_threads(agent_name="head", limit=50)
        discs = service.list_scout_threads(agent_name="discovery", limit=50)
        assert any(t["id"] == head_thread["id"] for t in heads)
        assert not any(t["id"] == head_thread["id"] for t in discs)
        assert any(t["id"] == discovery_thread["id"] for t in discs)
    finally:
        eng = create_engine(_database_url())
        with eng.begin() as conn:
            conn.execute(
                text("DELETE FROM scout_messages WHERE thread_id IN (SELECT id FROM scout_threads WHERE id = ANY(CAST(:ids AS uuid[])))"),
                {"ids": [str(head_thread["id"]), str(discovery_thread["id"])]},
            )
        with eng.begin() as conn:
            conn.execute(
                text("DELETE FROM scout_threads WHERE id = ANY(CAST(:ids AS uuid[]))"),
                {"ids": [str(head_thread["id"]), str(discovery_thread["id"])]},
            )
        eng.dispose()

@pytest.fixture
def client():
    from api.main import app

    return TestClient(app)


def test_unknown_agent_threads_400(client):
    r = client.get("/api/agents/nope/threads")
    assert r.status_code == 400, r.text


def test_list_threads_scoped_by_agent(client, monkeypatch):
    from crm import service

    monkeypatch.setattr(service, "list_scout_threads", lambda agent_name, limit=50: [])
    r = client.get("/api/agents/head/threads?limit=10")
    assert r.status_code == 200, r.text
    assert r.json() == []


def test_create_thread_posts_agent_name(client, monkeypatch):
    from crm import service

    calls = {}
    monkeypatch.setattr(
        service,
        "create_scout_thread",
        lambda title=None, agent_name="discovery": calls.update(title=title, agent_name=agent_name)
        or {"id": "00000000-0000-0000-0000-000000000001", "title": title, "created_at": None, "updated_at": None},
    )
    r = client.post("/api/agents/qualifier/threads", json={"title": "q1"})
    assert r.status_code == 201, r.text
    assert calls["agent_name"] == "qualifier"
    assert calls["title"] == "q1"


def test_unknown_agent_messages_400(client):
    r = client.get("/api/agents/nope/threads/00000000-0000-0000-0000-000000000001/messages")
    assert r.status_code == 400, r.text


def test_agent_sse_stream_frames(client, monkeypatch):
    from crm import scout

    monkeypatch.setattr(
        scout,
        "run_agent_turn",
        lambda agent_name, thread_id, content, **kw: {
            "thread_id": "00000000-0000-0000-0000-000000000001",
            "assistant": "hello there",
            "tool_calls": 0,
            "message_ids": [],
        },
    )
    r = client.post(
        "/api/agents/head/threads/00000000-0000-0000-0000-000000000001/messages",
        json={"content": "hi"},
    )
    assert r.status_code == 200, r.text
    body = r.text
    assert "event: start" in body
    assert "event: delta" in body
    assert "hello there" in body
    assert "event: done" in body
