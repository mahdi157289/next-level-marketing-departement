# tests/test_web_search_tool.py
from unittest.mock import MagicMock, patch

from tools.web_search_tool import searxng_search, web_search_tool


def _settings(searxng_url: str):
    s = MagicMock()
    s.searxng_base_url = searxng_url
    s.searxng_timeout_s = 8.0
    return s


def test_searxng_search_parses_results():
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {
        "results": [
            {"title": "Acme", "url": "https://acme.tn", "content": "Acme agency"},
            {"title": "No url", "content": "skip me"},
        ]
    }
    with patch("tools.web_search_tool.httpx.get", return_value=resp), \
         patch("tools.web_search_tool.get_settings", return_value=_settings("http://searxng:8080")):
        out = searxng_search("Acme", max_results=5)
    assert out[0] == {"title": "Acme", "url": "https://acme.tn", "snippet": "Acme agency"}
    assert len(out) == 1  # result without url dropped


def test_searxng_search_disabled_when_no_base_url():
    with patch("tools.web_search_tool.get_settings", return_value=_settings("")):
        assert searxng_search("Acme") == []


def test_searxng_search_never_raises():
    with patch("tools.web_search_tool.httpx.get", side_effect=RuntimeError("boom")), \
         patch("tools.web_search_tool.get_settings", return_value=_settings("http://searxng:8080")):
        assert searxng_search("Acme") == []


def test_web_search_prefers_searxng_when_configured():
    hits = [{"title": "Acme", "url": "https://acme.tn", "snippet": "Acme agency"}]
    with patch("tools.web_search_tool.searxng_search", return_value=hits), \
         patch("tools.web_search_tool._discover_ddgs_classes", return_value=[]):
        out = web_search_tool("Acme", max_results=3)
    assert out and out[0]["url"] == "https://acme.tn"


def test_web_search_falls_back_to_ddgs_when_searxng_empty():
    ddgs_hits = [{"title": "Acme ddgs", "url": "https://ddgs.tn", "snippet": "found via ddgs"}]

    class _FakeDDGS:
        def __init__(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def text(self, query, **kw):
            return ddgs_hits

    with patch("tools.web_search_tool.searxng_search", return_value=[]), \
         patch("tools.web_search_tool._discover_ddgs_classes", return_value=[("fake", lambda: _FakeDDGS())]):
        out = web_search_tool("Acme", max_results=3)
    assert any("ddgs.tn" in h["url"] for h in out)
