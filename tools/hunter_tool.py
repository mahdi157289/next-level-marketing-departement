"""hunter — CRM-driven lead investigation tool.

Detects empty columns on a lead from the live `leads` schema, runs
field-targeted web searches to hunt for the missing values, mines them with
the same validators as the scrape tool, and returns a knowledge summary +
evidence sources. Never raises; reports status instead.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

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
    except Exception:
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
