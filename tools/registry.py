"""Stable tool ids for agent profiles (whitelist).

Only ids listed in an agent_profiles.enabled_tools may run at Start time.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

TOOL_CATALOG: List[Dict[str, Any]] = [
    {
        "id": "web_search",
        "label": "DuckDuckGo / DDGS web search",
        "agents": ["discovery"],
    },
    {
        "id": "meta_ads_search",
        "label": "Meta Ad Library — find businesses running ads",
        "agents": ["discovery"],
    },
    {
        "id": "google_maps_search",
        "label": "Google Maps Place Search (Playwright)",
        "agents": ["discovery"],
    },
    {
        "id": "crm_write_leads",
        "label": "Write leads to CRM",
        "agents": ["discovery"],
    },
    {
        "id": "llm_chat",
        "label": "LiteLLM / LM Studio chat",
        "agents": ["discovery", "head"],
    },
    {
        "id": "seo_audit",
        "label": "SEO audit tool",
        "agents": ["discovery"],
    },
    {
        "id": "scrape",
        "label": "Playwright scrape",
        "agents": ["discovery"],
    },
]

_KNOWN_IDS = {t["id"] for t in TOOL_CATALOG}

DISCOVERY_REQUIRED_TOOLS = frozenset({"web_search", "llm_chat"})
# Always keep lead writes when the operator enabled them (Head often omits this).
DISCOVERY_FORCE_IF_ALLOWED = frozenset({"crm_write_leads"})


def catalog_for_agent(agent_name: str) -> List[Dict[str, Any]]:
    return [t for t in TOOL_CATALOG if agent_name in t["agents"]]


def validate_tool_ids(tool_ids: List[str], *, agent_name: Optional[str] = None) -> List[str]:
    """Return cleaned unique tool ids; raise ValueError if unknown or missing required."""
    cleaned: List[str] = []
    seen = set()
    for tid in tool_ids or []:
        tid = str(tid).strip()
        if not tid or tid in seen:
            continue
        if tid not in _KNOWN_IDS:
            raise ValueError(f"Unknown tool id: {tid}")
        if agent_name:
            allowed = {t["id"] for t in catalog_for_agent(agent_name)}
            if tid not in allowed:
                raise ValueError(f"Tool {tid} is not available for agent {agent_name}")
        seen.add(tid)
        cleaned.append(tid)
    if agent_name == "discovery":
        missing = DISCOVERY_REQUIRED_TOOLS - set(cleaned)
        if missing:
            raise ValueError(
                f"Discovery requires tools: {sorted(DISCOVERY_REQUIRED_TOOLS)} "
                f"(missing: {sorted(missing)})"
            )
    return cleaned


def tool_enabled(enabled_tools: Optional[List[str]], tool_id: str) -> bool:
    return tool_id in (enabled_tools or [])


def clamp_discovery_tools(
    requested: List[str],
    *,
    allowed: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Intersect Head's request with operator-allowed Discovery tools; always keep required.

    Returns {tools, skill_gaps} where skill_gaps are requested or required tools
    that were not in the allowed set (except required are force-added if allowed).
    """
    allowed_set = set(allowed or [t["id"] for t in catalog_for_agent("discovery")])
    # Required tools must be allowed for a valid scout; if operator stripped them, error via validate later.
    requested_clean = []
    seen = set()
    for tid in requested or []:
        tid = str(tid).strip()
        if not tid or tid in seen:
            continue
        if tid not in _KNOWN_IDS:
            continue
        seen.add(tid)
        requested_clean.append(tid)

    skill_gaps = [t for t in requested_clean if t not in allowed_set]
    selected = [t for t in requested_clean if t in allowed_set]
    for req in DISCOVERY_REQUIRED_TOOLS | DISCOVERY_FORCE_IF_ALLOWED:
        if req not in selected and req in allowed_set:
            selected.append(req)
        elif req in DISCOVERY_REQUIRED_TOOLS and req not in allowed_set and req not in skill_gaps:
            skill_gaps.append(req)

    # Prefer stable order from catalog
    order = [t["id"] for t in catalog_for_agent("discovery")]
    selected_sorted = [t for t in order if t in selected]
    for t in selected:
        if t not in selected_sorted:
            selected_sorted.append(t)

    validated = validate_tool_ids(selected_sorted, agent_name="discovery")
    return {"tools": validated, "skill_gaps": skill_gaps, "requested": requested_clean}


def resolve_callable(tool_id: str) -> Optional[Callable[..., Any]]:
    """Lazy import to avoid heavy deps at import time."""
    if tool_id == "web_search":
        from tools.web_search_tool import web_search_tool

        return web_search_tool
    if tool_id == "meta_ads_search":
        from tools.meta_ads_tool import meta_ads_search

        return meta_ads_search
    if tool_id == "google_maps_search":
        from tools.google_maps_tool import google_maps_search

        return google_maps_search
    if tool_id == "seo_audit":
        from tools.seo_audit_tool import seo_audit_tool

        return seo_audit_tool
    if tool_id == "scrape":
        from tools.scrape_tool import scrape_tool

        return scrape_tool
    if tool_id in ("crm_write_leads", "llm_chat"):
        return None  # handled inline by agents
    return None
