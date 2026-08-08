"""Agent-side brain retrieval (P6) — scoped RAG context for prompt injection."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def default_domain(agent_name: str) -> str:
    """AgentProfile.default_domain, else 'global'. Never raises."""
    try:
        from crm import service as crm_service

        profile = crm_service.get_agent_profile(agent_name) or {}
        return (profile.get("default_domain") or "").strip() or "global"
    except Exception:  # noqa: BLE001
        return "global"


def build_brain_context(agent_name: str, query: str, limit: int = 5) -> str:
    """Scoped brain results formatted for prompt injection; '' when no results.

    Reuses scoped_query (cache -> pgvector -> graph -> metrics), so agent
    retrieval automatically hits the Redis cache and records telemetry.
    Never raises: any failure here returns ''.
    """
    from knowledge.rag import scoped_query

    try:
        payload = scoped_query(agent_name, default_domain(agent_name), query, limit=limit)
    except Exception:  # noqa: BLE001
        return ""
    rows = payload.get("results") or []
    if not rows:
        return ""
    lines = ["## Brain context"]
    for r in rows[:limit]:
        kind = r.get("type", "chunk")
        content = (r.get("content") or "").strip()
        source = (r.get("source") or r.get("url") or "").strip()
        if not content:
            continue
        lines.append(f"- [{kind}] {content} ({source or 'unknown'})")
    return "\n".join(lines) if len(lines) > 1 else ""
