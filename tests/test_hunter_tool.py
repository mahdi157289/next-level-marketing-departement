from unittest.mock import patch

from crm.agents_registry import AGENT_ROSTER
from tools.hunter_tool import _build_queries, _domain, _huntable_columns, _mine_field, hunter
from tools.registry import TOOL_CATALOG, resolve_callable, validate_tool_ids

HITS = [
    {"title": "Acme - Contact", "url": "https://acme.tn/contact",
     "snippet": "Email hello@acme.tn or call +216 71 123 456. Facebook: facebook.com/acme.tn Instagram: instagram.com/acme"},
    {"title": "Acme", "url": "https://acme.tn", "snippet": "Acme is a web agency in Tunis"},
]


def test_mine_email_and_phone():
    assert _mine_field("email", HITS) == "hello@acme.tn"
    assert "+216" in _mine_field("phone", HITS)


def test_mine_socials_from_snippets():
    socials = _mine_field("facebook", HITS)
    assert socials == "https://facebook.com/acme.tn"


def test_mine_unknown_field_uses_best_snippet():
    val = _mine_field("vat_number", HITS)
    assert isinstance(val, str) and len(val) > 0


def test_mined_values_respect_column_lengths():
    LONG = "X" * 500
    H = [{"title": "Acme", "url": "https://acme.tn", "snippet": LONG}]
    with patch("tools.hunter_tool._run_searches", return_value=H), \
         patch("tools.hunter_tool._synthesize_summary", return_value="Acme overview."):
        out = hunter(name="Acme", country="Tunisia",
                     gaps=["price_level", "business_type"])
    found = out["fields_found"]
    if "price_level" in found:
        assert len(found["price_level"]) <= 16
    if "business_type" in found:
        assert len(found["business_type"]) <= 64


def test_numeric_columns_never_receive_strings():
    H = [{"title": "Acme", "url": "https://acme.tn", "snippet": "Acme rating 4.5 120 reviews"}]
    with patch("tools.hunter_tool._run_searches", return_value=H), \
         patch("tools.hunter_tool._synthesize_summary", return_value="s"):
        out = hunter(name="Acme", gaps=["rating", "review_count", "seo_score"])
    for num in ("rating", "review_count", "seo_score"):
        if num in out["fields_found"]:
            assert isinstance(out["fields_found"][num], (int, float))


def test_hunter_returns_full_payload_and_fills_gaps():
    with patch("tools.hunter_tool._run_searches", return_value=HITS), \
         patch("tools.hunter_tool._synthesize_summary", return_value="Acme is an agency."):
        out = hunter(name="Acme", url="https://acme.tn", country="Tunisia", gaps=["email", "phone"])
    assert out["status"] == "ok"
    assert out["summary"] == "Acme is an agency."
    assert out["fields_found"]["email"] == "hello@acme.tn"
    assert out["queries"]
    assert out["sources"]


def test_hunter_default_gaps_are_empty_columns():
    with patch("tools.hunter_tool._run_searches", return_value=[]):
        out = hunter(name="Acme", country="Tunisia")
    assert out["status"] == "no_results"
    joined = " ".join(out["queries"])
    assert "email OR contact" in joined        # empty column is hunted
    assert "phone OR telephone" in joined      # empty column is hunted
    assert "Acme name" not in joined           # populated column is NOT hunted
    assert "Acme country" not in joined        # populated column is NOT hunted


def test_hunter_never_raises_on_search_failure():
    with patch("tools.hunter_tool._run_searches", return_value=[]), \
         patch("tools.hunter_tool._synthesize_summary", return_value=""):
        out = hunter(name="Acme")
    assert out["status"] == "no_results"


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


def test_hunter_in_catalog_for_all_agents():
    entry = next(t for t in TOOL_CATALOG if t["id"] == "hunter")
    assert set(entry["agents"]) == {a["name"] for a in AGENT_ROSTER}


def test_hunter_resolves():
    assert callable(resolve_callable("hunter"))


def test_hunter_valid_for_every_agent():
    from tools.registry import DISCOVERY_REQUIRED_TOOLS

    for a in AGENT_ROSTER:
        tools = (
            sorted(DISCOVERY_REQUIRED_TOOLS) + ["hunter"]
            if a["name"] == "discovery"
            else ["hunter"]
        )
        validate_tool_ids(tools, agent_name=a["name"])


def test_hunter_in_all_roster_default_tools():
    for a in AGENT_ROSTER:
        assert "hunter" in a["default_tools"]
