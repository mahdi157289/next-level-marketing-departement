"""P3 — RAG vector store (Ollama + pgvector), real Postgres."""

from __future__ import annotations

import os
import uuid
from typing import Optional
from unittest import mock

import pytest
from fastapi.testclient import TestClient


def _database_url() -> Optional[str]:
    return os.getenv("DATABASE_URL")


@pytest.fixture
def client():
    from api.main import app

    return TestClient(app)


@pytest.fixture
def agent_name():
    return f"pytest-{uuid.uuid4().hex[:6]}"


# Unit test: vector formatting + similarity wiring, no DB / no Ollama needed.
def test_vec_to_str_and_search_params():
    import importlib

    mod = importlib.import_module("db.embeddings")
    s = mod._vec_to_str([0.1, 0.2, 0.3])
    assert s.startswith("[")
    assert "0.100000" in s and "0.300000" in s
    # 768-dim dim assert path
    assert mod.EMBEDDING_DIM == 768


def test_embed_query_rejects_wrong_dim(monkeypatch):
    import importlib

    mod = importlib.import_module("db.embeddings")

    monkeypatch.setattr(mod, "EMBEDDING_DIM", 3)

    class _Resp:
        def __init__(self, data):
            self._data = data

        def read(self):
            import json

            return json.dumps(self._data).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(mod, "_EMBEDDING_MODEL", "nomic-embed-text")
    fake_opener = mock.MagicMock()
    fake_opener.open.return_value.__enter__.return_value = _Resp({"embedding": [0.1, 0.2]})
    monkeypatch.setattr(mod, "_opener", fake_opener)
    with pytest.raises(RuntimeError, match="embedding dim"):
        mod.embed_query("hi")


# Live DB + Ollama integration (skipped if no DB).
@pytest.mark.skipif(not _database_url(), reason="DATABASE_URL not set")
def test_ingest_and_search_roundtrip(client, agent_name, monkeypatch):
    # Gating on Ollama availability — skip gracefully if unreachable (the app
    # may live behind a container name; we only need to confirm an embedding
    # provider is reachable so the round-trip doesn't 500).
    import urllib.request

    reachable = False
    from urllib.request import ProxyHandler, build_opener

    opener = build_opener(ProxyHandler({}))
    for host in ("127.0.0.1", "localhost"):
        try:
            opener.open(f"http://{host}:11434/api/tags", timeout=4)
            reachable = True
            break
        except Exception:
            continue
    if not reachable:
        pytest.skip("Ollama not reachable on host 11434")

    # TestClient runs in-process on the host — point the embedder at the host-
    # reachable published port (the container itself uses nextlevel-ollama:11434).
    import db.embeddings as emb

    monkeypatch.setattr(emb, "OLLAMA_URL", "http://127.0.0.1:11434")

    r = client.post(
        f"/api/agents/{agent_name}/chunks",
        json={"agent_name": agent_name, "content": "Tunisia digital marketing agencies", "scope": "domain:tn"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["agent_name"] == agent_name

    r2 = client.post(
        f"/api/agents/{agent_name}/chunks/search",
        json={"query": "marketing agencies in Tunisia", "scope": "domain:tn", "limit": 3},
    )
    assert r2.status_code == 200, r2.text
    results = r2.json()
    assert len(results) >= 1
    assert results[0]["similarity"] > 0.0  # cosine sim positive
