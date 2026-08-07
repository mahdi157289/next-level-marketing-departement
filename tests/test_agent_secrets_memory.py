"""P2 — agent secrets (encrypted) + scoped memory, real Postgres."""

from __future__ import annotations

import os
import uuid
from typing import Optional

import pytest
from fastapi.testclient import TestClient

from db.secrets import decrypt_secret, encrypt_secret


def _database_url() -> Optional[str]:
    return os.getenv("DATABASE_URL")


@pytest.fixture
def client():
    from api.main import app

    return TestClient(app)


@pytest.fixture
def agent_name():
    return f"pytest-{uuid.uuid4().hex[:6]}"


@pytest.mark.skipif(not _database_url(), reason="DATABASE_URL not set")
def test_secret_roundtrip_and_is_encrypted(client, agent_name):
    key = "sk-test-1234567890"
    token = encrypt_secret(key)
    # Token differs from plaintext (Fernet) when a key is configured.
    if os.getenv("SECRET_ENCRYPTION_KEY"):
        assert token != key
        assert decrypt_secret(token) == key
    else:
        # Dev fallback: plaintext storage.
        assert decrypt_secret(token) == key

    r = client.post(
        f"/crm/agents/{agent_name}/secrets",
        json={"kind": "openai", "name": "OPENAI_API_KEY", "value": key},
    )
    assert r.status_code == 200, r.text

    rows = client.get(f"/crm/agents/{agent_name}/secrets").json()
    listed = next(s for s in rows if s["kind"] == "openai" and s["name"] == "OPENAI_API_KEY")
    assert listed["agent_name"] == agent_name
    # List returns a short fingerprint, never the raw token value.
    assert listed["fingerprint"]
    assert "value" not in listed
    assert all("value" not in s for s in rows)

    resolved = client.get(f"/crm/agents/{agent_name}/secrets/openai/resolve").json()
    assert resolved["value"] == key
    client.delete(f"/crm/agents/{agent_name}/secrets/openai")


@pytest.mark.skipif(not _database_url(), reason="DATABASE_URL not set")
def test_memory_append_list_clear(client, agent_name):
    r = client.post(
        f"/crm/agents/{agent_name}/memory",
        json={"scope": "campaign:alpha", "key": "offer_angle", "value": "AI tools for Tunisia market"},
    )
    assert r.status_code == 200, r.text
    mem = r.json()
    assert mem["agent_name"] == agent_name
    assert mem["scope"] == "campaign:alpha"
    assert mem["key"] == "offer_angle"

    lst = client.get(f"/crm/agents/{agent_name}/memory?scope=campaign:alpha").json()
    assert len(lst) == 1
    assert lst[0]["value"] == "AI tools for Tunisia market"

    from crm import service

    n = service.clear_memory(agent_name, scope="campaign:alpha")
    assert n == 1
    assert client.get(f"/crm/agents/{agent_name}/memory?scope=campaign:alpha").json() == []


@pytest.mark.skipif(not _database_url(), reason="DATABASE_URL not set")
def test_resolve_missing_secret_returns_404(client, agent_name):
    r = client.get(f"/crm/agents/{agent_name}/secrets/openai/resolve")
    assert r.status_code == 404


def test_encrypt_decrypt_without_key_returns_plaintext(monkeypatch):
    monkeypatch.delenv("SECRET_ENCRYPTION_KEY", raising=False)
    # Reimport to reset the module-level `_fernet`.
    import importlib

    import db.secrets as secrets_mod

    importlib.reload(secrets_mod)
    assert secrets_mod.encrypt_secret("plain") == "plain"
    assert secrets_mod.decrypt_secret("plain") == "plain"
