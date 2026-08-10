# tests/test_site_extract.py
from unittest.mock import patch

from tools.site_extract_tool import _llm_extract_fields, _parse_json_object, site_extract


def _page(**kw):
    class _R:
        pass

    r = _R()
    r.title = kw.get("title", "Acme")
    r.markdown = kw.get("markdown", "Acme is a web agency. Contact hello@acme.tn")
    return r


def test_site_extract_returns_markdown_and_fields():
    with patch("tools.site_extract_tool._cached", return_value=None), \
         patch("tools.site_extract_tool._robots_allows", return_value=True), \
         patch("tools.site_extract_tool._crawl_sync", return_value=_page()), \
         patch("tools.site_extract_tool.chat_completion", return_value='{"email": "hello@acme.tn"}'):
        out = site_extract("https://acme.tn", fields=["email"])
    assert out["status"] == "ok"
    assert out["markdown"]
    assert out["fields"]["email"] == "hello@acme.tn"


def test_site_extract_respects_robots():
    with patch("tools.site_extract_tool._robots_allows", return_value=False):
        out = site_extract("https://acme.tn")
    assert out["status"] == "robots_denied"


def test_site_extract_never_raises_on_crawl_failure():
    with patch("tools.site_extract_tool._cached", return_value=None), \
         patch("tools.site_extract_tool._robots_allows", return_value=True), \
         patch("tools.site_extract_tool._crawl_sync", side_effect=RuntimeError("boom")):
        out = site_extract("https://acme.tn")
    assert out["status"] == "fetch_failed"


def test_site_extract_unavailable_without_crawl4ai():
    with patch("tools.site_extract_tool._cached", return_value=None), \
         patch("tools.site_extract_tool._robots_allows", return_value=True), \
         patch("tools.site_extract_tool._crawl_sync", side_effect=ImportError("crawl4ai")):
        out = site_extract("https://acme.tn")
    assert out["status"] == "unavailable"


def test_parse_json_object_handles_fences_and_garbage():
    assert _parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert _parse_json_object("garbage") is None


def test_llm_extract_fields_returns_empty_on_bad_output():
    with patch("tools.site_extract_tool.chat_completion", return_value="not json at all"):
        assert _llm_extract_fields(["email"], "content") == {}
