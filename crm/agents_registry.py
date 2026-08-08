"""Static roster of every agent in the department.

The roster is the source of truth for which agent names exist. A name here maps
to an ``agent_profiles`` row when one exists; otherwise the roster entry's
defaults are used as a profile-shaped fallback (see ``crm.service``).
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set

AGENT_ROSTER: List[Dict[str, object]] = [
    {
        "name": "discovery", "display_name": "Discovery (Scout)",
        "description": "Searches the web/maps/ad library and writes leads.",
        "default_tools": [
            "web_search", "google_maps_search", "meta_ads_search",
            "crm_write_leads", "llm_chat", "scrape",
        ],
        "providers": ["openai", "serpapi", "google_maps", "meta_ads"],
    },
    {
        "name": "head", "display_name": "Head (Supervisor)",
        "description": "Plans missions and dispatches subordinate agents.",
        "default_tools": ["llm_chat"], "providers": ["openai"],
    },
    {
        "name": "qualifier", "display_name": "Qualifier",
        "description": "Scores and qualifies leads against the service catalog.",
        "default_tools": ["llm_chat"], "providers": ["openai"],
    },
    {
        "name": "categorization", "display_name": "Categorization",
        "description": "Tags leads with country, industry, business type.",
        "default_tools": ["llm_chat"], "providers": ["openai"],
    },
    {
        "name": "analysis", "display_name": "Analysis",
        "description": "Enriches leads with SEO score, email, phone, lead score.",
        "default_tools": ["llm_chat"], "providers": ["openai"],
    },
    {
        "name": "outreach", "display_name": "Outreach",
        "description": "Contacts leads (planned: SMTP/WhatsApp).",
        "default_tools": ["llm_chat"], "providers": ["openai", "smtp", "whatsapp"],
    },
    {
        "name": "content", "display_name": "Content",
        "description": "Produces marketing content (planned: WordPress/social).",
        "default_tools": ["llm_chat"], "providers": ["openai", "wordpress"],
    },
]


def roster_names() -> Set[str]:
    """All roster agent names — the single source of truth for allowlists."""
    return {entry["name"] for entry in AGENT_ROSTER}


def roster_entry(name: str) -> Optional[Dict[str, object]]:
    """Return the roster entry for ``name`` or ``None`` if not on the roster."""
    for entry in AGENT_ROSTER:
        if entry["name"] == name:
            return entry
    return None
