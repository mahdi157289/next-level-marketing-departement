"""Unit tests for google_maps_tool — mocks subprocess, no CRM writes.

Tests verify that google_maps_tool correctly calls the Node.js scraper
via subprocess and parses JSON output into the expected {title, url, snippet, ...} format.
"""

import json
import os
import subprocess
from unittest.mock import patch, MagicMock

from tools.google_maps_tool import google_maps_search, get_last_google_maps_diag


class _MockCompletedProcess:
    """Mimics subprocess.Popen for testing."""

    def __init__(self, stdout_lines, stderr="", returncode=0):
        self._stdout_lines = stdout_lines
        self._stderr = stderr
        self._returncode = returncode
        self.stdout = MagicMock()
        self.stderr = MagicMock()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _MockPopen:
    """Mock subprocess.Popen that yields JSON lines from stdout."""

    def __init__(self, stdout_lines=None, stderr="", returncode=0):
        self._stdout_lines = stdout_lines or []
        self._stderr = stderr
        self._returncode = returncode
        self.stdout = self
        self.stderr = self
        self._read_index = 0
        self.wait_called = False
        # Store all stdout lines joined
        self._all_stdout = "\n".join(self._stdout_lines)
        self._all_stderr = stderr

    def readline(self):
        if self._read_index < len(self._stdout_lines):
            line = self._stdout_lines[self._read_index]
            self._read_index += 1
            return line + "\n"
        return ""

    def read(self):
        if self is self.stderr:
            return self._all_stderr
        return ""

    def wait(self):
        self.wait_called = True
        return self._returncode

    @property
    def returncode(self):
        return self._returncode


def _make_lead_json(lead):
    """Create a streaming JSON line for a lead."""
    return json.dumps({"type": "lead", "data": lead})


def _make_complete_json(leads):
    """Create a final summary JSON line."""
    return json.dumps({"type": "complete", "count": len(leads), "leads": leads})


_PIZZA_LEAD = {
    "id": "lead_1",
    "name": "Pizza Palace",
    "address": "123 Main St, Tunis, Tunisia",
    "phone": "+21671000000",
    "website": "https://pizzapalace.tn",
    "category": "Italian Restaurant",
    "rating": "4.2",
    "reviewsCount": "120",
    "hours": "Mon-Fri: 9:00 AM - 10:00 PM",
    "description": "Best pizza in town since 1990",
    "url": "https://www.google.com/maps/place/Pizza+Palace/@36.8,10.0",
    "email": "info@pizzapalace.tn",
    "socials": {
        "facebook": "https://facebook.com/pizzapalace",
        "instagram": "https://instagram.com/pizzapalace",
        "linkedin": "",
        "twitter": "",
    },
}

_BURGER_LEAD = {
    "id": "lead_2",
    "name": "Burger King",
    "address": "456 Oak Ave, Tunis, Tunisia",
    "phone": "+216790000000",
    "website": "https://burgerking.tn",
    "category": "Fast Food Restaurant",
    "rating": "3.8",
    "reviewsCount": "45",
    "hours": "Open 24 hours",
    "description": "Flame-grilled burgers",
    "url": "https://www.google.com/maps/place/Burger+King/@36.8,10.0",
    "email": "",
    "socials": {
        "facebook": "",
        "instagram": "https://instagram.com/burgerking",
        "linkedin": "",
        "twitter": "",
    },
}


def test_extract_normal_business():
    """Test extracting a normal business from scraper output."""
    stdout_lines = [
        _make_lead_json(_PIZZA_LEAD),
        _make_complete_json([_PIZZA_LEAD]),
    ]
    mock_popen = _MockPopen(stdout_lines=stdout_lines, stderr="[LOG] Scraping done\n")

    with patch("tools.google_maps_tool.subprocess.Popen", return_value=mock_popen):
        results = google_maps_search("pizza", region="Tunis", max_results=3)

    assert len(results) == 1
    hit = results[0]
    assert hit["title"] == "Pizza Palace"
    assert hit["url"] == "https://pizzapalace.tn"
    assert "4.2" in hit["snippet"]
    assert "Tunis" in hit["snippet"]
    assert "+216" in hit["phone"] or "71000000" in hit["phone"]
    assert hit["category"] == "Italian Restaurant"
    assert hit["review_count"] == "120"
    assert "123 Main St" in hit["address"]
    assert "Mon-Fri: 9:00 AM" in hit["hours"]
    assert "Best pizza" in hit["description"]
    assert hit["facebook"] == "https://facebook.com/pizzapalace"
    assert hit["instagram"] == "https://instagram.com/pizzapalace"


def test_junk_url_filtered():
    """Test that Wikipedia/junk URLs are filtered out."""
    junk_lead = dict(_PIZZA_LEAD)
    junk_lead["website"] = "https://en.wikipedia.org/wiki/Pizza"

    stdout_lines = [
        _make_lead_json(junk_lead),
        _make_complete_json([junk_lead]),
    ]
    mock_popen = _MockPopen(stdout_lines=stdout_lines)

    with patch("tools.google_maps_tool.subprocess.Popen", return_value=mock_popen):
        results = google_maps_search("pizza", region="Tunisia", max_results=3)

    assert len(results) == 1
    # URL should be empty or the Google Maps URL, not Wikipedia
    assert "wikipedia" not in results[0]["url"]


def test_returns_empty_on_scraper_error():
    """Test that an error from the scraper returns empty list."""
    stdout_lines = [json.dumps({"type": "error", "message": "Scraper failed"})]
    mock_popen = _MockPopen(stdout_lines=stdout_lines, returncode=1)

    with patch("tools.google_maps_tool.subprocess.Popen", return_value=mock_popen):
        results = google_maps_search("zzznomatch", region="Tunisia", max_results=3)
    assert results == []


def test_max_results_respected():
    """Test that max_results cap is respected."""
    leads = []
    for i in range(10):
        lead = {
            "name": f"Biz{i}",
            "address": f"Address {i}",
            "phone": f"+2167900000{i}",
            "website": f"https://biz{i}.tn",
            "category": f"Category {i}",
            "rating": "4.0",
            "reviewsCount": "10",
            "url": f"https://maps.google.com/place/Biz{i}",
            "socials": {},
        }
        leads.append(lead)

    stdout_lines = [_make_lead_json(l) for l in leads[:5]] + [_make_complete_json(leads[:5])]
    mock_popen = _MockPopen(stdout_lines=stdout_lines)

    with patch("tools.google_maps_tool.subprocess.Popen", return_value=mock_popen):
        results = google_maps_search("business", region="Tunisia", max_results=3)

    assert len(results) == 3


def test_region_passed_to_subprocess():
    """Test that region is passed to the Node.js subprocess."""
    mock_popen = _MockPopen(stdout_lines=[_make_complete_json([])])

    with patch("tools.google_maps_tool.subprocess.Popen", return_value=mock_popen) as mock_popen_cls:
        google_maps_search("restaurant", region="Sousse, Tunisia", max_results=5)

        # Check the command passed to Popen
        call_args = mock_popen_cls.call_args
        cmd = call_args[0][0]
        assert "Sousse, Tunisia" in cmd
        assert "restaurant" in cmd


def test_empty_query_returns_empty():
    """Test that empty query returns empty list without calling subprocess."""
    with patch("tools.google_maps_tool.subprocess.Popen") as mock_popen:
        results = google_maps_search("", region="Tunisia", max_results=3)
    assert results == []
    assert "empty" in get_last_google_maps_diag().lower()
    mock_popen.assert_not_called()


def test_max_results_capped_at_100():
    """Test that max_results is capped at 100."""
    # Create 200 leads
    leads = []
    for i in range(200):
        leads.append({
            "name": f"Biz{i}",
            "address": f"Addr {i}",
            "phone": "+21679000000",
            "website": f"https://biz{i}.com",
            "category": "Test",
            "rating": "4.0",
            "reviewsCount": "10",
        })

    stdout_lines = [_make_lead_json(l) for l in leads] + [_make_complete_json(leads)]
    mock_popen = _MockPopen(stdout_lines=stdout_lines)

    with patch("tools.google_maps_tool.subprocess.Popen", return_value=mock_popen):
        results = google_maps_search("pizza", region="Tunisia", max_results=200)

    assert len(results) <= 100


def test_business_fields_extracted():
    """Test that all business fields are correctly extracted from scraper output."""
    stdout_lines = [
        _make_lead_json(_PIZZA_LEAD),
        _make_lead_json(_BURGER_LEAD),
        _make_complete_json([_PIZZA_LEAD, _BURGER_LEAD]),
    ]
    mock_popen = _MockPopen(stdout_lines=stdout_lines)

    with patch("tools.google_maps_tool.subprocess.Popen", return_value=mock_popen):
        results = google_maps_search("pizza", region="Tunisia", max_results=5)

    pizza = next((r for r in results if r["title"] == "Pizza Palace"), None)
    assert pizza is not None
    assert pizza["address"] == "123 Main St, Tunis, Tunisia"
    assert pizza["phone"] == "+21671000000"
    assert pizza["url"] == "https://pizzapalace.tn"
    assert pizza["category"] == "Italian Restaurant"
    assert pizza["rating"] == "4.2"
    assert pizza["review_count"] == "120"
    assert "9:00 AM" in pizza["hours"]
    assert "Best pizza" in pizza["description"]
    assert pizza["facebook"] == "https://facebook.com/pizzapalace"
    assert pizza["instagram"] == "https://instagram.com/pizzapalace"
    assert pizza["google_maps_url"] == "https://www.google.com/maps/place/Pizza+Palace/@36.8,10.0"


def test_callback_invoked_for_each_lead():
    """Test that onLeadScaped callback is called for each lead."""
    stdout_lines = [
        _make_lead_json(_PIZZA_LEAD),
        _make_lead_json(_BURGER_LEAD),
        _make_complete_json([_PIZZA_LEAD, _BURGER_LEAD]),
    ]
    mock_popen = _MockPopen(stdout_lines=stdout_lines)

    captured_leads = []

    def on_lead(lead):
        captured_leads.append(lead)

    with patch("tools.google_maps_tool.subprocess.Popen", return_value=mock_popen):
        google_maps_search("pizza", region="Tunisia", max_results=5, onLeadScaped=on_lead)

    assert len(captured_leads) == 2
    assert captured_leads[0]["title"] == "Pizza Palace"
    assert captured_leads[1]["title"] == "Burger King"


def test_node_not_found_returns_empty():
    """Test that missing Node.js returns empty list with diagnostic."""
    import builtins

    def mock_popen(*args, **kwargs):
        raise FileNotFoundError(2, "No such file or directory: 'node'")

    with patch("tools.google_maps_tool.subprocess.Popen", side_effect=mock_popen):
        results = google_maps_search("pizza", region="Tunisia", max_results=3)

    assert results == []
    diag = get_last_google_maps_diag()
    assert "Node.js not found" in diag or "not found" in diag.lower()
