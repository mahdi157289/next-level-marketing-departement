"""brain_query_metrics — record + read RAG brain query telemetry (P4)."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from db.session import engine


def record_query(
    agent_name: str,
    domain: Optional[str],
    query_hash: str,
    latency_ms: int,
    cache_hit: bool,
    vector_hits: int,
    graph_hits: int,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO brain_query_metrics
                    (id, agent_name, domain, query_hash, latency_ms, cache_hit, vector_hits, graph_hits, created_at)
                VALUES (:id, :agent_name, :domain, :query_hash, :latency_ms, :cache_hit, :vector_hits, :graph_hits, NOW())
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "agent_name": agent_name,
                "domain": domain,
                "query_hash": query_hash,
                "latency_ms": latency_ms,
                "cache_hit": cache_hit,
                "vector_hits": vector_hits,
                "graph_hits": graph_hits,
            },
        )


def recent_queries(limit: int = 20) -> List[Dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, agent_name, domain, query_hash, latency_ms, cache_hit, vector_hits, graph_hits, created_at
                FROM brain_query_metrics
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        ).mappings().all()
    return [dict(r) for r in rows]
