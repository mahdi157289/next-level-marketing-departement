"""RAG vector store for the Scout brain.

Embeddings come from **Ollama** (`nomic-embed-text`, 768-dim) — no external
API key required and the model is already pulled in the live `marketing_ollama`
container. Vectors are stored in the `agent_chunks.embedding` `vector(768)`
column and searched by cosine distance (`<=>`).

Vectors are sent to PostgreSQL as space-separated string literals (the input
format pgvector accepts), so no Python `pgvector` binding is required.
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Optional
from urllib.request import ProxyHandler, build_opener

from sqlalchemy import text

from db.session import SessionLocal

_EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
EMBEDDING_DIM = 768
OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
# Bypass any system proxy (e.g. Windows WPAD auto-detection) so the container or
# a Windows host can reach a local Ollama directly.
_opener = build_opener(ProxyHandler({}))


def embed_query(text: str) -> List[float]:
    """Embed a query via Ollama; returns a 768-dim list."""
    payload = json.dumps({"model": _EMBEDDING_MODEL, "prompt": text}).encode("utf-8")
    req = urllib.request.Request(f"{OLLAMA_URL}/api/embeddings", data=payload, headers={"Content-Type": "application/json"})
    with _opener.open(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    vec = data.get("embedding")
    if not vec:
        raise RuntimeError(f"no embedding returned for model {EMBEDDING_MODEL}")
    if len(vec) != EMBEDDING_DIM:
        raise RuntimeError(f"embedding dim {len(vec)} != expected {EMBEDDING_DIM}")
    return [float(x) for x in vec]


def _vec_to_str(vec: List[float]) -> str:
    # pgvector's text input format is a JSON-array-like bracket with
    # comma-separated floats, e.g. "[0.1, 0.2, 0.3]".
    return "[" + ", ".join(f"{x:.6f}" for x in vec) + "]"


def insert_chunk(
    agent_name: str,
    content: str,
    scope: str = "shared",
    source_uri: Optional[str] = None,
    embedding: Optional[List[float]] = None,
) -> Dict[str, Any]:
    """Insert a content chunk with its embedding and return the row dict."""
    if embedding is None:
        embedding = embed_query(content)
    vec_str = _vec_to_str(embedding)
    session = SessionLocal()
    try:
        sql = text(
            """
            INSERT INTO agent_chunks (id, agent_name, scope, source_uri, content, embedding, created_at)
            VALUES (:id, :agent_name, :scope, :source_uri, :content, :embedding, NOW())
            """
        )
        row_id = str(__import__("uuid").uuid4())
        session.execute(
            sql,
            {
                "id": row_id,
                "agent_name": agent_name,
                "scope": scope,
                "source_uri": source_uri,
                "content": content,
                "embedding": vec_str,
            },
        )
        session.commit()
        return {"id": row_id, "agent_name": agent_name, "scope": scope, "content": content}
    finally:
        session.close()


def search_chunks(
    agent_name: str,
    query: str,
    scope: Optional[str] = None,
    limit: int = 5,
    min_similarity: float = 0.0,
) -> List[Dict[str, Any]]:
    """Return top-`limit` chunks by cosine similarity (descending).

    ``min_similarity`` is a 0..1 floor; rows whose similarity is below it are
    filtered out (default 0.0 = return all, ranked).
    """
    q_emb = embed_query(query)
    vec_str = _vec_to_str(q_emb)
    session = SessionLocal()
    try:
        where = "agent_name = :agent_name"
        params: Dict[str, Any] = {"agent_name": agent_name, "vec": vec_str, "limit": limit, "min_similarity": min_similarity}
        if scope:
            where += " AND scope = :scope"
            params["scope"] = scope
        sql = text(
            f"""
            SELECT id, agent_name, scope, source_uri, content, created_at,
                   1 - (embedding <=> :vec) AS similarity
            FROM agent_chunks
            WHERE {where} AND (1 - (embedding <=> :vec)) >= :min_similarity
            ORDER BY similarity DESC
            LIMIT :limit
            """
        )
        rows = session.execute(sql, params).mappings().all()
        return [dict(r) for r in rows]
    finally:
        session.close()
