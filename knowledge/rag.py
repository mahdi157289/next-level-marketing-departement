"""Orchestrated RAG brain: Redis cache -> pgvector -> graph-expand -> cache.

`scoped_query` is the single entry point P6 will wire into agents. It never
raises: cache, vector, graph and metrics layers each degrade independently.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from config.settings import get_settings
from db.brain_metrics import record_query
from db.embeddings import search_chunks
from knowledge import graph as graphmod

_redis = None


def _cache_client():
    global _redis
    if _redis is None:
        import redis

        _redis = redis.Redis.from_url(
            get_settings().redis_url, decode_responses=True, socket_connect_timeout=2
        )
    return _redis


def _cache_key(agent_name: str, domain: str, query: str) -> str:
    h = hashlib.sha256(f"{agent_name}:{domain}:{query}".encode("utf-8")).hexdigest()
    return f"brain:{agent_name}:{domain}:{h}"


def cache_get(key: str) -> Optional[Dict[str, Any]]:
    try:
        val = _cache_client().get(key)
        return json.loads(val) if val else None
    except Exception:  # noqa: BLE001
        return None


def cache_set(key: str, payload: Dict[str, Any]) -> None:
    try:
        _cache_client().set(key, json.dumps(payload), ex=get_settings().brain_cache_ttl_s)
    except Exception:  # noqa: BLE001
        pass


def expand_related_leads(terms: List[str], domain: str, limit: int = 5) -> List[Dict[str, Any]]:
    return graphmod.expand_related_leads(terms, domain, limit=limit)


def scoped_query(
    agent_name: str,
    domain: str,
    query: str,
    limit: int = 5,
    use_cache: bool = True,
) -> Dict[str, Any]:
    t0 = time.monotonic()
    key = _cache_key(agent_name, domain, query)

    if use_cache:
        cached = cache_get(key)
        if cached is not None:
            cached["cache_hit"] = True
            cached["latency_ms"] = int((time.monotonic() - t0) * 1000)
            try:
                record_query(
                    agent_name, domain, key, cached["latency_ms"], True,
                    cached.get("vector_hits", 0), cached.get("graph_hits", 0),
                )
            except Exception:  # noqa: BLE001
                pass
            return cached

    vector: List[Dict[str, Any]] = []
    try:
        vector = search_chunks(agent_name, query, scope=domain, limit=limit)
    except Exception:  # noqa: BLE001
        vector = []

    graph_leads: List[Dict[str, Any]] = []
    try:
        terms = [t for t in query.lower().split() if len(t) > 2]
        graph_leads = expand_related_leads(terms, domain, limit=limit)
    except Exception:  # noqa: BLE001
        graph_leads = []

    results: List[Dict[str, Any]] = [
        {
            "type": "chunk",
            "source": c.get("source_uri"),
            "content": c.get("content"),
            "similarity": c.get("similarity"),
        }
        for c in vector
    ]
    results += [
        {
            "type": "lead",
            "source": l.get("url"),
            "content": l.get("name"),
            "url": l.get("url"),
        }
        for l in graph_leads
    ]

    payload: Dict[str, Any] = {
        "query": query,
        "domain": domain,
        "agent_name": agent_name,
        "cache_hit": False,
        "vector_hits": len(vector),
        "graph_hits": len(graph_leads),
        "results": results,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    payload["latency_ms"] = int((time.monotonic() - t0) * 1000)

    if use_cache:
        cache_set(key, payload)

    try:
        record_query(
            agent_name, domain, key, payload["latency_ms"], False,
            len(vector), len(graph_leads),
        )
    except Exception:  # noqa: BLE001
        pass

    return payload
