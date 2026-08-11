from unittest.mock import patch

from tools.research_tool import _build_queries, _coerce_for_column, _domain, _extract_site_gaps, _huntable_columns, _mine_field, research

HITS = [
    {"title": "Acme - Contact", "url": "https://acme.tn/contact",
     "snippet": "Email hello@acme.tn or call +216 71 123 456. Facebook: facebook.com/acme.tn Instagram: instagram.com/acme"},
    {"title": "Acme", "url": "https://acme.tn", "snippet": "Acme is a web agency in Tunis"},
]


def test_mine_email_and_phone():
    assert _mine_field("email", HITS) == "hello@acme.tn"
    assert "+216" in _mine_field("phone", HITS)


def test_mine_socials_from_snippets():
    assert _mine_field("facebook", HITS) == "https://facebook.com/acme.tn"


def test_coerced_values_respect_column_lengths():
    assert len(_coerce_for_column("price_level", "X" * 500)) <= 16
    assert len(_coerce_for_column("business_type", "X" * 500)) <= 64


def test_numeric_columns_never_receive_strings():
    assert _coerce_for_column("rating", "abc") is None
    assert _coerce_for_column("review_count", "120") == 120


def test_research_returns_full_payload_and_fills_gaps():
    with patch("tools.research_tool._run_searches", return_value=HITS), \
         patch("tools.research_tool._synthesize_summary", return_value="Acme is an agency."):
        out = research(name="Acme", url="https://acme.tn", country="Tunisia", gaps=["email", "phone"])
    assert out["status"] == "ok"
    assert out["summary"] == "Acme is an agency."
    assert out["fields_found"]["email"] == "hello@acme.tn"
    assert out["queries"]
    assert out["sources"]


def test_research_default_gaps_are_empty_columns():
    with patch("tools.research_tool._run_searches", return_value=[]):
        out = research(name="Acme", country="Tunisia")
    assert out["status"] == "no_results"
    joined = " ".join(out["queries"])
    assert "email OR contact" in joined        # empty column is hunted
    assert "phone OR telephone" in joined      # empty column is hunted
    assert "Acme name" not in joined           # populated column is NOT hunted
    assert "Acme country" not in joined        # populated column is NOT hunted


def test_research_never_raises_on_search_failure():
    with patch("tools.research_tool._run_searches", return_value=[]), \
         patch("tools.research_tool._synthesize_summary", return_value=""):
        out = research(name="Acme")
    assert out["status"] == "no_results"


def test_research_uses_site_extract_for_gaps():
    with patch("tools.research_tool._run_searches", return_value=[]), \
         patch("tools.research_tool._synthesize_summary", return_value="Acme overview."), \
         patch("tools.research_tool._extract_site_gaps", return_value={"hours": "Mon-Fri 9:00-18:00"}):
        out = research(name="Acme", url="https://acme.tn", country="Tunisia", gaps=["hours"])
    assert out["fields_found"]["hours"] == "Mon-Fri 9:00-18:00"


def test_extract_site_gaps_uses_site_extract_and_skips_found():
    with patch("tools.site_extract_tool.site_extract") as se:
        se.return_value = {"status": "ok", "fields": {"hours": "9-18", "email": "a@b.tn"}}
        out = _extract_site_gaps("https://acme.tn", gaps=["hours", "email"], already={"email": "a@b.tn"})
    assert out == {"hours": "9-18"}


def test_huntable_columns_exclude_denylist():
    cols = _huntable_columns()
    assert "email" in cols
    assert "research" not in cols
    assert "id" not in cols
    assert "status" not in cols
    assert "url" not in cols


def test_build_queries_has_context_and_per_gap():
    qs = _build_queries("Acme", url="https://www.acme.tn", industry="agency", country="Tunisia", gaps=["email", "phone"])
    assert qs[0] == "Acme Tunisia"
    assert "site:acme.tn" in qs
    assert any("email" in q for q in qs)
    assert any("phone" in q or "telephone" in q or "tel" in q for q in qs)
    assert len(qs) <= 8


def test_build_queries_generic_fallback_for_unknown_column():
    qs = _build_queries("Acme", country="Tunisia", gaps=["vat_number"])
    assert any("vat number" in q for q in qs)


def test_domain_strips_www_and_scheme():
    assert _domain("https://www.acme.tn/") == "acme.tn"
    assert _domain("http://acme.com") == "acme.com"
    assert _domain("") == ""


from crm.agents_registry import AGENT_ROSTER
from tools.registry import DISCOVERY_REQUIRED_TOOLS, TOOL_CATALOG, resolve_callable, validate_tool_ids


def test_research_in_catalog_for_all_agents():
    entry = next(t for t in TOOL_CATALOG if t["id"] == "research")
    assert set(entry["agents"]) == {a["name"] for a in AGENT_ROSTER}


def test_research_resolves():
    assert callable(resolve_callable("research"))


def test_research_valid_for_every_agent():
    for a in AGENT_ROSTER:
        tools = (
            sorted(DISCOVERY_REQUIRED_TOOLS) + ["research", "site_extract"]
            if a["name"] == "discovery"
            else ["research"]
        )
        validate_tool_ids(tools, agent_name=a["name"])


def test_research_in_all_roster_default_tools():
    for a in AGENT_ROSTER:
        assert "research" in a["default_tools"]
