"""LLM runtime status endpoint — provider detection, no secret leakage."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from api.main import app

    return TestClient(app)


@pytest.fixture
def stub_settings(monkeypatch):
    """Monkeypatch get_settings + ensure_llm_reachable for hermetic tests."""

    def _patch(**overrides):
        from config.settings import Settings

        settings = Settings().model_copy(
            update={
                "openai_api_base": None,
                "lm_studio_base_url": "http://127.0.0.1:1234/v1",
                "openai_api_key": "lm-studio",
                "agent_model_discovery": "mistralai/mistral-7b-instruct-v0.3",
                "agent_model_head": "mistralai/mistral-7b-instruct-v0.3",
                **overrides,
            }
        )
        monkeypatch.setattr("config.settings.get_settings", lambda: settings)
        monkeypatch.setattr(
            "agents.lm_client.ensure_llm_reachable",
            lambda: (True, "ok via chat probe"),
        )
        return settings

    return _patch


def test_llm_status_openrouter(stub_settings):
    stub_settings(openai_api_base="https://openrouter.ai/api/v1", openai_api_key="sk-or-v1-secret")
    client = TestClient(__import__("api.main", fromlist=["app"]).app)

    r = client.get("/api/llm/status")
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "OpenRouter"
    assert body["base_url"] == "https://openrouter.ai/api/v1"
    assert body["api_key_set"] is True
    assert body["reachable"] is True
    assert body["detail"] == "ok via chat probe"
    assert {m["agent"] for m in body["models"]} == {"discovery", "head"}
    assert "sk-or-v1-secret" not in r.text


def test_llm_status_litellm(stub_settings):
    stub_settings(openai_api_base="http://litellm:4000/v1", openai_api_key="dev-key")
    client = TestClient(__import__("api.main", fromlist=["app"]).app)

    body = client.get("/api/llm/status").json()
    assert body["provider"] == "LiteLLM"
    assert body["api_key_set"] is True


def test_llm_status_openai_compatible(stub_settings):
    stub_settings(openai_api_base="https://api.example.com/v1", openai_api_key="sk-test")
    client = TestClient(__import__("api.main", fromlist=["app"]).app)

    body = client.get("/api/llm/status").json()
    assert body["provider"] == "OpenAI-compatible"


def test_llm_status_lm_studio_default(stub_settings):
    stub_settings()
    client = TestClient(__import__("api.main", fromlist=["app"]).app)

    body = client.get("/api/llm/status").json()
    assert body["provider"] == "LM Studio (local)"
    assert body["base_url"] == "http://127.0.0.1:1234/v1"
    assert body["api_key_set"] is False


def test_llm_status_unreachable(stub_settings, monkeypatch):
    stub_settings()
    monkeypatch.setattr(
        "agents.lm_client.ensure_llm_reachable",
        lambda: (False, "connection refused"),
    )
    client = TestClient(__import__("api.main", fromlist=["app"]).app)

    body = client.get("/api/llm/status").json()
    assert body["reachable"] is False
    assert body["detail"] == "connection refused"
