"""GET/PUT agent system prompt (prompts/{name}.md) API tests."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from api.main import app

    return TestClient(app)


@pytest.fixture
def tmp_prompt_dir(monkeypatch, tmp_path):
    from knowledge import prompts

    monkeypatch.setattr(prompts, "_PROMPT_DIR", tmp_path)
    return tmp_path


def test_get_missing_prompt_returns_exists_false(client, tmp_prompt_dir):
    r = client.get("/api/agents/head/prompt")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["agent_name"] == "head"
    assert data["exists"] is False
    assert data["content"] == ""


def test_put_writes_and_get_roundtrips(client, tmp_prompt_dir):
    content = "# System Prompt — Head\n\nBe decisive."
    r = client.put("/api/agents/head/prompt", json={"content": content})
    assert r.status_code == 200, r.text
    assert r.json()["exists"] is True
    assert r.json()["content"] == content

    r2 = client.get("/api/agents/head/prompt")
    assert r2.json()["content"] == content


def test_unknown_agent_prompt_400(client, tmp_prompt_dir):
    assert client.get("/api/agents/nope/prompt").status_code == 400
    assert client.put("/api/agents/nope/prompt", json={"content": "x"}).status_code == 400
