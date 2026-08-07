"""P5 — provider/API-key inputs (hashed fingerprint) + catalog."""

from __future__ import annotations

import os
from typing import Optional

import pytest
from fastapi.testclient import TestClient


def _database_url() -> Optional[str]:
    return os.getenv("DATABASE_URL")


@pytest.fixture
def client():
    from api.main import app

    return TestClient(app)


@pytest.mark.skipif(not _database_url(), reason="DATABASE_URL not set")
def test_providers_list_and_secret_fingerprint(client):
    from crm import service

    agent = "head"
    # Ensure a clean known state for openai key on head.
    service.delete_agent_secret(agent, "openai")

    rows = client.get(f"/api/agents/{agent}/providers").json()
    kinds = {p["kind"] for p in rows}
    assert {"openai", "serpapi", "google_maps", "meta_ads"} <= kinds
    openai = next(p for p in rows if p["kind"] == "openai")
    assert openai["has_key"] is False
    assert openai["fingerprint"] is None

    client.post(
        f"/api/agents/{agent}/secrets",
        json={"kind": "openai", "name": "OPENAI_API_KEY", "value": "sk-test-abcdef123456"},
    )

    rows = client.get(f"/api/agents/{agent}/providers").json()
    openai = next(p for p in rows if p["kind"] == "openai")
    assert openai["has_key"] is True
    assert openai["fingerprint"]
    assert len(openai["fingerprint"]) >= 8
    # Fingerprint is a hash, not the raw key.
    assert "sk-test" not in openai["fingerprint"]

    # Resolution still returns the raw value once.
    resolved = client.get(f"/api/agents/{agent}/secrets/openai/resolve").json()
    assert resolved["value"] == "sk-test-abcdef123456"
    # List does NOT leak the value.
    listed = client.get(f"/api/agents/{agent}/secrets").json()
    assert all("value" not in s for s in listed)
    client.delete(f"/api/agents/{agent}/secrets/openai")


@pytest.mark.skipif(not _database_url(), reason="DATABASE_URL not set")
def test_unknown_agent_providers_404(client):
    r = client.get("/api/agents/does-not-exist/providers")
    assert r.status_code == 404
