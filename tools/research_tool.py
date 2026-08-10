"""research — CRM-driven lead investigation tool (replaces hunter).

Detects empty columns on a lead, runs field-targeted web searches (self-hosted
SearXNG with DDGS fallback), and fills remaining gaps by extracting the lead's
own site with Crawl4AI + an LLM. Returns a knowledge summary + evidence sources.
Never raises; reports status instead. The enrich workflow persists the result.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import sqlalchemy as sa

from db.models import Lead

MAX_QUERIES = 8

HUNT_DENYLIST = {
    "id", "created_at", "updated_at", "status", "status_notes",
    "source", "url", "google_maps_url", "research",
}

# field -> query template. "{name}" = lead name; "{domain}" = lead domain.
_FIELD_QUERY_TEMPLATES = {
    "email": "{name} email OR contact",
    "phone": "{name} phone OR telephone OR tel",
    "facebook": "{name} facebook",
    "instagram": "{name} instagram",
    "linkedin": "{name} linkedin",
    "twitter": "{name} twitter OR x.com",
    "address": "{name} address OR adresse",
    "industry": "{name} services OR \"what they do\"",
    "business_type": "{name} services OR \"what they do\"",
    "hours": "{name} hours OR horaires OR opening",
    "description": "{name} about OR \"qui sommes-nous\"",
    "price_level": "{name} reviews OR category",
    "tags": "{name} reviews OR category",
    "country": "{name} city OR country",
    "rating": "{name} reviews",
    "review_count": "{name} reviews",
    "seo_score": "site:{domain}",
}


def _huntable_columns() -> List[str]:
    """All leads-table columns minus the denylist (schema-driven, future-proof)."""
    return [c.name for c in Lead.__table__.columns if c.name not in HUNT_DENYLIST]


def _column_human(field: str) -> str:
    return field.replace("_", " ")


def _domain(url: str) -> str:
    try:
        host = (urlparse(url or "").hostname or "").lower()
    except Exception:  # noqa: BLE001
        return ""
    return host[4:] if host.startswith("www.") else host


def _query_for_field(field: str, name: str, domain: str = "") -> str:
    tpl = _FIELD_QUERY_TEMPLATES.get(field)
    if not tpl:
        return f"{name} {_column_human(field)}"
    if "{domain}" in tpl:
        return tpl.format(domain=domain) if domain else f"{name} {_column_human(field)}"
    return tpl.format(name=name)


def _build_queries(
    name: str,
    url: str = "",
    industry: str = "",
    country: str = "",
    gaps: Optional[List[str]] = None,
) -> List[str]:
    name = (name or "").strip()
    if not name:
        return []
    domain = _domain(url)
    queries: List[str] = []
    queries.append(f"{name} {country}".strip() if country else name)
    if domain:
        queries.append(f"site:{domain}")
    for field in gaps or []:
        q = _query_for_field(field, name, domain)
        if q not in queries:
            queries.append(q)
    return queries[:MAX_QUERIES]


_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")


def _hit_blob(hits):
    return " ".join(
        f"{h.get('title', '')} {h.get('snippet', '')} {h.get('url', '')}"
        for h in hits
    )


def _mine_field(field: str, hits: List[Dict[str, Any]]) -> Any:
    """Deterministic extraction for fields that don't need an LLM."""
    if field == "email":
        m = _EMAIL_RE.search(_hit_blob(hits))
        return m.group(0) if m else None
    if field == "phone":
        for h in hits:
            blob = f"{h.get('title', '')} {h.get('snippet', '')}"
            for cand in re.findall(r"\+?[\d\s\-().]{7,15}", blob):
                from tools.scrape_tool import _clean_phone

                cleaned = _clean_phone(cand)
                if cleaned:
                    return cleaned
        return None
    if field in ("facebook", "instagram", "linkedin", "twitter"):
        from tools.scrape_tool import _extract_socials

        return _extract_socials(_hit_blob(hits)).get(field)
    if field == "description":
        return (hits[0].get("snippet") or "")[:500] if hits else None
    if field in ("industry", "business_type"):
        for h in hits[:3]:
            snip = (h.get("snippet") or "").strip()
            if snip:
                return snip[:128]
        return None
    return None


def _coerce_for_column(field: str, value: Any) -> Any:
    """Fit a mined value to the lead column's type: truncate strings to the
    column length, coerce numerics, drop values that can't fit. Returns None
    when the value can't be stored."""
    col = Lead.__table__.columns.get(field)
    if col is None:
        return value
    t = col.type
    if isinstance(t, sa.String):
        if isinstance(value, str):
            return value[:t.length] if t.length else value
        return value
    if isinstance(t, sa.Integer):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    if isinstance(t, sa.Float):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    if getattr(t, "python_type", None) is dict:
        return value if isinstance(value, (dict, list)) else None
    return value


def _synthesize_summary(name: str, industry: str, country: str, hits: List[Dict[str, Any]]) -> str:
    from agents.lm_client import chat_completion
    from config.settings import get_settings

    snippets = "\n".join(
        f"- {h.get('title', '')}: {h.get('snippet', '')}" for h in hits[:12]
    )
    prompt = (
        "Write a short markdown intelligence profile of a company from web search results.\n"
        "Sections: ## Overview, ## Services, ## Online presence, ## What we found.\n"
        f"Company: {name}\nIndustry: {industry or 'unknown'}\nCountry: {country or 'unknown'}\n"
        f"Search results:\n{snippets}\nProfile:"
    )
    try:
        text = chat_completion(
            get_settings().agent_model_discovery,
            [{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=512,
        )
        text = (text or "").strip()
        if text:
            return text
    except BaseException:  # noqa: BLE001
        pass
    # Deterministic fallback.
    lines = [f"## Overview\n{name} ({country or 'unknown'})."]
    top = (hits[0].get("snippet") or "").strip() if hits else ""
    if top:
        lines.append(f"**Key finding:** {top[:400]}")
    lines.append(f"## Sources\n" + "\n".join(f"- {h.get('title', '')}: {h.get('url', '')}" for h in hits[:5]))
    return "\n".join(lines)


def _run_searches(queries: List[str], max_per_query: int = 5) -> List[Dict[str, Any]]:
    from tools.registry import resolve_callable
    from tools.web_search_tool import _relevance_score, web_search_tool

    fn = resolve_callable("web_search") or web_search_tool
    seen: set = set()
    collected: List[Dict[str, Any]] = []
    for q in queries:
        try:
            for h in fn(q, max_results=max_per_query) or []:
                url = (h.get("url") or "").rstrip("/")
                if url and url not in seen:
                    seen.add(url)
                    collected.append(h)
        except BaseException:  # noqa: BLE001
            continue
    return sorted(collected, key=lambda h: _relevance_score(h, queries[0] if queries else ""), reverse=True)[:15]


def research(
    name: str = "",
    url: str = "",
    industry: str = "",
    country: str = "",
    gaps: Optional[List[str]] = None,
    **fields: Any,
) -> Dict[str, Any]:
    """Investigate a lead: detect empty columns, web-search them, mine values,
    extract the site for anything still missing, and summarize."""
    pseudo = {"name": name, "url": url, "industry": industry, "country": country, **fields}
    if gaps is None:
        gaps = [c for c in _huntable_columns() if _is_empty(pseudo.get(c))]
    queries = _build_queries(name, url=url, industry=industry, country=country, gaps=gaps)
    if not queries:
        return {"summary": "", "fields_found": {}, "sources": [], "queries": [],
                "status": "no_results", "investigated_at": _now()}
    hits = _run_searches(queries)

    fields_found: Dict[str, Any] = {}
    for field in gaps:
        try:
            val = _mine_field(field, hits)
        except BaseException:  # noqa: BLE001
            val = None
        if val not in (None, "", [], {}):
            fields_found[field] = _coerce_for_column(field, val)

    site_data = _extract_site_gaps(url, gaps, fields_found)
    for field, val in site_data.items():
        fields_found[field] = _coerce_for_column(field, val)

    if not hits and not fields_found:
        summary = ""
        status = "no_results"
    else:
        summary = _synthesize_summary(name, industry, country, hits)
        status = "llm_fallback" if not summary or summary.startswith("## Overview\n" + name) else "ok"
        if not summary:
            summary = f"## Overview\n{name}"
            status = "llm_fallback"
    sources = [
        {"title": h.get("title", ""), "url": h.get("url", ""),
         "snippet": (h.get("snippet") or "")[:300], "query": queries[0]}
        for h in hits[:10]
    ]
    if url and site_data:
        sources.append({"title": name, "url": url, "snippet": "extracted from site", "query": queries[0]})
    return {
        "summary": summary,
        "fields_found": fields_found,
        "sources": sources,
        "queries": queries,
        "status": status,
        "investigated_at": _now(),
    }


def _extract_site_gaps(url: str, gaps: List[str], already: Dict[str, Any]) -> Dict[str, Any]:
    """Use site_extract to fill gap fields not yet found. Never raises."""
    if not url:
        return {}
    missing = [f for f in gaps if f not in already]
    if not missing:
        return {}
    from tools.site_extract_tool import site_extract

    try:
        out = site_extract(url, fields=missing)
    except BaseException:  # noqa: BLE001
        return {}
    if out.get("status") != "ok":
        return {}
    return {
        k: v for k, v in (out.get("fields") or {}).items()
        if k in missing and v not in (None, "", [], {})
    }


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (list, dict)) and not value:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if value == 0:
        return True
    return False


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
