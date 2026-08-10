from unittest.mock import patch

from tools.hunter_tool import _build_queries, _domain, _huntable_columns, _mine_field, hunter

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


def test_hunter_returns_full_payload_and_fills_gaps():
    with patch("tools.hunter_tool._run_searches", return_value=HITS), \
         patch("tools.hunter_tool._synthesize_summary", return_value="Acme is an agency."):
        out = hunter(name="Acme", url="https://acme.tn", country="Tunisia", gaps=["email", "phone"])
    assert out["status"] == "ok"
    assert out["summary"] == "Acme is an agency."
    assert out["fields_found"]["email"] == "hello@acme.tn"
    assert out["queries"]
    assert out["sources"]


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
