# google_maps_tool — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a free, Playwright-based `google_maps_search` tool function that the Discovery Agent can call to scrape Google Maps place results. The function mirrors `meta_ads_tool` / `web_search_tool` — same signature shape, same `{title, url, snippet, ...}` return contract, same junk filtering. This is a backend-only tool module; no UI, no extra CLI scripts, no wrapper scripts.

**Architecture:** A new `tools/google_maps_tool.py` mirrors `meta_ads_tool.py` and `web_search_tool.py` — same function shape, same return contract, same filtering. One new entry is added to `TOOL_CATALOG` in `tools/registry.py`, and `DiscoveryAgent.run()` calls it between Meta Ads and DuckDuckGo. Leads flow into the CRM via the unchanged `recorder.create_lead_from_hit()`. No UI changes, no CLI wrapper scripts — pure backend tool + registry registration + agent integration.

**Tech Stack:** Python 3.11, Playwright (sync API, same as `scrape_tool.py`), regex extraction, no external API keys.

## Global Constraints

- No paid APIs (PRD §1.5: "No paid APIs"). Uses Playwright headless Chromium — free, same as `scrape_tool.py`.
- PRD §2.3: Max 50 leads per scan. `max_results` defaults to 10, capped at 50.
- PRD §1.5: Rate limit 1 req/sec per domain — `time.sleep(1.0)` between page load and parse.
- PRD: Tunisia-first, MENA region preference.
- `.cursor/rules/real-data-only.mdc`: No mock/fake CRM writes. Unit tests mock Playwright only — no CRM interaction. Live tests gated behind `@pytest.mark.live` + `RUN_LIVE_TESTS=1`.
- Follow existing tool naming: `google_maps_tool.google_maps_search`.
- `TOOLS/` directory already has: `__init__.py`, `registry.py`, `web_search_tool.py`, `meta_ads_tool.py`, `scrape_tool.py`, `seo_audit_tool.py`, `crm_tool.py`.
- `requirements.txt` already includes `playwright>=1.40.0` — no dependency changes.
- No new `.env` variables, no UI endpoints, no CLI scripts.

---

### Task 1: Write unit tests for `google_maps_tool` (TDD — tests first, no CRM)

**Files:**
- Create: `tests/test_google_maps_tool.py`

**Interfaces:**
- Consumes: `sync_playwright` (will be patched), `filter_prospect_hits` (from `tools.web_search_tool`)
- Produces: nothing yet — tests assert behavior on the not-yet-existing `google_maps_search`

Test file mocks `playwright.sync_api.sync_playwright` via `unittest.mock.patch`. Inline HTML fixture strings simulate Google Maps result cards.

```python
import os
from unittest.mock import patch, MagicMock
from tools.google_maps_tool import google_maps_search

# Inline HTML fixture: one business card
_MOCK_MAPS_HTML = """
<div role="article" aria-label="Pizza Palace">
  <a href="/maps/place/Pizza+Palace/data=!3m1!4b1!4m5!3m1!1s0x123:0xabc!8m2!3d36.8!4d10!1m1!1s0x123:0xabc"
     aria-label="Pizza Palace - Website">
    <h3>Pizza Palace</h3>
    <button data-id="website">https://pizzapalace.tn</button>
  </a>
  <span>⭐ 4.2 (120 reviews)</span>
  <span>123 Main St, Tunis, Tunisia</span>
  <span>+216 71 000 000</span>
</div>
"""

class _FakeLocator:
    def __init__(self, html):
        self._html = html

    @property
    def count(self):
        return MagicMock(return_value=1)

class _FakePage:
    def __init__(self, html):
        self._html = html

    def goto(self, url, timeout=None, wait_until=None):
        return None

    def wait_for_selector(self, selector, timeout=None):
        if "article" in selector or "Nv2Tne" in selector:
            return
        raise TimeoutError(f"selector not found: {selector}")

    def content(self):
        return self._html

class _FakeBrowser:
    def new_page(self, **kwargs):
        return _FakePage(_MOCK_MAPS_HTML)

    def close(self):
        pass

class _FakeChromium:
    def launch(self, **kwargs):
        return _FakeBrowser()

class _FakePlaywright:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    @property
    def chromium(self):
        return _FakeChromium()


def test_extract_normal_business():
    with patch("tools.google_maps_tool.sync_playwright", return_value=_FakePlaywright()):
        results = google_maps_search("pizza", region="Tunis", max_results=3)
    assert len(results) == 1
    hit = results[0]
    assert hit["title"] == "Pizza Palace"
    assert hit["url"] == "https://pizzapalace.tn"
    assert "Pizza Palace" in hit["snippet"]
    assert "4.2" in hit["snippet"]
    assert "Tunis" in hit["snippet"]


def test_junk_url_filtered():
    html = _MOCK_MAPS_HTML.replace(
        "https://pizzapalace.tn",
        "https://en.wikipedia.org/wiki/Pizza"
    )
    class _FakePageWiki:
        def goto(self, url, **kw): ...
        def wait_for_selector(self, selector, timeout=None):
            if "article" in selector or "Nv2Tne" in selector:
                return
            raise TimeoutError()
        def content(self):
            return html
    class _FakeBrowserWiki:
        def new_page(self, **kw): return _FakePageWiki()
        def close(self): ...
    class _FakeChromiumWiki:
        def launch(self, **kw): return _FakeBrowserWiki()
    class _FakePW:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        @property
        def chromium(self): return _FakeChromiumWiki()

    with patch("tools.google_maps_tool.sync_playwright", return_value=_FakePW()):
        results = google_maps_search("pizza", region="Tunis", max_results=3)
    assert results == []


def test_returns_empty_on_no_cards():
    class _FakePageEmpty:
        def goto(self, url, **kw): ...
        def wait_for_selector(self, selector, timeout=None):
            raise TimeoutError("no elements")
        def content(self):
            return "<div>no results</div>"
    class _FakeBrowserEmpty:
        def new_page(self, **kw): return _FakePageEmpty()
        def close(self): ...
    class _FakeChromiumEmpty:
        def launch(self, **kw): return _FakeBrowserEmpty()
    class _FakePWEmpty:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        @property
        def chromium(self): return _FakeChromiumEmpty()

    with patch("tools.google_maps_tool.sync_playwright", return_value=_FakePWEmpty()):
        results = google_maps_search("zzznomatch", region="Tunisia", max_results=3)
    assert results == []


def test_max_results_respected():
    # Build a fixture with 5 identical cards
    card = '<div role="article" aria-label="Biz%d"><a href="/maps/place?p=Biz%d"><h3>Biz%d</h3></a></div>'
    html = "".join(card % (i, i, i) for i in range(5))
    class _FakePageN:
        def goto(self, url, **kw): ...
        def wait_for_selector(self, selector, timeout=None): ...
        def content(self):
            return html
    class _FakeBrowserN:
        def new_page(self, **kw): return _FakePageN()
        def close(self): ...
    class _FakeChromiumN:
        def launch(self, **kw): return _FakeBrowserN()
    class _FakePWN:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        @property
        def chromium(self): return _FakeChromiumN()

    with patch("tools.google_maps_tool.sync_playwright", return_value=_FakePWN()):
        results = google_maps_search("business", region="Tunisia", max_results=2)
    assert len(results) == 2


def test_region_passed_to_url():
    captured_url = []
    class _FakePageURL:
        def goto(self, url, **kw):
            captured_url.append(url)
        def wait_for_selector(self, selector, timeout=None): ...
        def content(self):
            return "<div>no cards</div>"
    class _FakeBrowserURL:
        def new_page(self, **kw): return _FakePageURL()
        def close(self): ...
    class _FakeChromiumURL:
        def launch(self, **kw): return _FakeBrowserURL()
    class _FakePWURL:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        @property
        def chromium(self): return _FakeChromiumURL()

    with patch("tools.google_maps_tool.sync_playwright", return_value=_FakePWURL()):
        google_maps_search("restaurant", region="Sousse, Tunisia", max_results=5)
    assert "Sousse" in captured_url[0]
```

- [ ] **Step 1: Write the failing test file**
- [ ] **Step 2: Run tests to verify they fail**
  Run: `python -m pytest tests/test_google_maps_tool.py -v`
  Expected: FAIL with `ModuleNotFoundError: No module named 'tools.google_maps_tool'`
- [ ] **Step 3: Commit test file**
  ```bash
  git add tests/test_google_maps_tool.py
  git commit -m "test: add unit tests for google_maps_tool (mocked Playwright)"
  ```

### Task 2: Implement `google_maps_tool.py`

**Files:**
- Create: `tools/google_maps_tool.py`

**Interfaces:**
- Consumes: `filter_prospect_hits` (from `tools.web_search_tool`), `sync_playwright` from `playwright.sync_api`
- Produces: `google_maps_search(query: str, region: str = "Tunisia", max_results: int = 10) -> List[Dict[str, Any]]`, `get_last_google_maps_diag() -> str`

Follows `scrape_tool.py` patterns for user-agent, and `web_search_tool.py` patterns for junk filtering and diagnostics.

```python
"""Google Maps place-search scraper via Playwright (free, no API key).

Mirrors the output contract of web_search_tool / meta_ads_tool:
returns List[Dict] with title, url, snippet (+ optional extra fields).
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict, List

from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

_LAST_GOOGLE_MAPS_DIAG: str = ""

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Reuse junk-filter needles from web_search_tool
from tools.web_search_tool import _JUNK_HOST_NEEDLES

# Google-internal domains we don't want as lead URLs
_GOOGLE_HOST_NEEDLES = (
    "google.com/maps",
    "maps.google.com",
    "google.com",
)


def get_last_google_maps_diag() -> str:
    return _LAST_GOOGLE_MAPS_DIAG


def _is_junk_url(url: str) -> bool:
    """Return True if URL is a Google Maps internal link or junk domain."""
    lower = url.lower()
    if not url or not lower.startswith("http"):
        return True
    for needle in _JUNK_HOST_NEEDLES:
        if needle in lower:
            return True
    for needle in _GOOGLE_HOST_NEEDLES:
        if needle in lower:
            return True
    return False


def _extract_phone(text: str) -> str:
    match = re.search(r"\+?\d[\d\s\-().]{7,15}", text)
    return match.group(0).strip() if match else ""


def _build_snippet(rating: str, review_count: str,
                   address: str, phone: str) -> str:
    parts = []
    if rating:
        parts.append(f"⭐ {rating}")
    if review_count:
        parts.append(f"({review_count} reviews)")
    if address:
        parts.append(address)
    if phone:
        parts.append(phone)
    return " · ".join(p for p in parts if p)


def _parse_google_maps_html(html: str, max_results: int) -> List[Dict[str, Any]]:
    """Extract business cards from Google Maps search HTML.

    Uses regex on raw HTML to avoid dependency on specific DOM structure.
    Falls back gracefully when fields are missing.
    """
    results: List[Dict[str, Any]] = []

    # Match each business card — anchored on role="article" or known card divs
    card_pattern = re.compile(
        r'<div[^>]*role=["\']article["\'][^>]*>(.*?)</div>',
        re.DOTALL | re.IGNORECASE,
    )
    cards = card_pattern.findall(html)

    # Fallback: also try .Nv2Tne class cards
    if not cards:
        nv_pattern = re.compile(
            r'<div[^>]*class=["\'][^"\']*Nv2Tne[^"\']*["\'][^>]*>(.*?)</div>',
            re.DOTALL | re.IGNORECASE,
        )
        cards = nv_pattern.findall(html)

    seen_urls: set = set()
    for card_html in cards[:max_results * 2]:
        if len(results) >= max_results:
            break

        # Name
        name_match = re.search(r'<h3[^>]*>(.*?)</h3>', card_html, re.DOTALL | re.IGNORECASE)
        if not name_match:
            name_match = re.search(r'aria-label=["\']([^"\']+)["\']', card_html)
        name = re.sub(r'<[^>]+>', '', name_match.group(1)).strip() if name_match else ""

        # Website URL — look for href that resolves to a real business site
        url = ""
        for href_match in re.finditer(r'href=["\'](/maps/place/.*?)["\']', card_html):
            href = href_match.group(1)
            sub = card_html[href_match.start():href_match.end() + 200]
            site_match = re.search(r'https?://[^\s"\'<>]+', sub)
            if site_match:
                url = site_match.group(0)
                break
        if not url:
            for href_match in re.finditer(r'href=["\'](https?://[^"\']+)["\']', card_html):
                candidate = href_match.group(1)
                if not _is_junk_url(candidate) and candidate not in seen_urls:
                    url = candidate
                    break

        if not url or _is_junk_url(url) or url in seen_urls:
            continue
        seen_urls.add(url)

        # Phone
        phone = _extract_phone(card_html)

        # Rating
        rating_match = re.search(r'⭐\s*([\d.]+)', card_html)
        if not rating_match:
            rating_match = re.search(r'aria-label=["\']([\d.]+)\s*stars?', card_html)
        rating = rating_match.group(1) if rating_match else ""

        # Review count
        review_match = re.search(r'([\d,]+)\s*reviews?', card_html, re.IGNORECASE)
        review_count = review_match.group(1).replace(",", "") if review_match else ""

        # Address
        address = ""
        addr_match = re.search(r'([\d\s]+[A-Za-z]+\s.+?,\s*.+?,\s*\w+(?:\s*\w+)*)', card_html)
        if addr_match:
            address = addr_match.group(1).strip()[:200]

        snippet = _build_snippet(rating, review_count, address, phone)

        results.append({
            "title": name[:256],
            "url": url[:512],
            "snippet": snippet[:500],
            "address": address,
            "phone": phone,
            "rating": float(rating) if rating and rating.replace(".", "").isdigit() else None,
            "review_count": int(review_count) if review_count.isdigit() else None,
            "category": name.split(" - ")[-1] if " - " in name else None,
            "google_maps_url": "",
        })

    return results


def google_maps_search(
    query: str,
    region: str = "Tunisia",
    max_results: int = 10,
) -> List[Dict[str, Any]]:
    """Scrape Google Maps place search results via Playwright (no API key).

    Args:
        query: Keywords / Business Type (e.g. "plumber", "pizza restaurant").
        region: Where — City / Region (e.g. "Tunis, Tunisia").
        max_results: Max number of business hits (capped at 50).

    Returns:
        List of dicts: {title, url, snippet, address, phone, rating, review_count, ...}
    """
    global _LAST_GOOGLE_MAPS_DIAG
    _LAST_GOOGLE_MAPS_DIAG = ""

    if not query.strip():
        _LAST_GOOGLE_MAPS_DIAG = "empty query"
        logger.warning("google_maps_search: empty query")
        return []

    max_results = max(1, min(max_results, 50))
    search_term = f"{query.strip()} {region.strip()}".replace(" ", "+")
    target_url = f"https://www.google.com/maps/search/{search_term}"

    _LAST_GOOGLE_MAPS_DIAG = f"GET {target_url}"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page(user_agent=DEFAULT_UA)
                page.goto(target_url, timeout=12000, wait_until="domcontentloaded")
                try:
                    page.wait_for_selector('div[role="article"]', timeout=5000)
                except Exception:
                    pass
                time.sleep(1.0)
                html = page.content()
            finally:
                browser.close()
    except Exception as e:
        _LAST_GOOGLE_MAPS_DIAG = f"ERROR: {type(e).__name__}: {e}"
        logger.warning("google_maps_search failed: %s", _LAST_GOOGLE_MAPS_DIAG)
        return []

    try:
        hits = _parse_google_maps_html(html, max_results)
    except Exception as e:
        _LAST_GOOGLE_MAPS_DIAG += f" | parse error: {e}"
        logger.warning("google_maps_search parse error: %s", e)
        hits = []

    if hits:
        _LAST_GOOGLE_MAPS_DIAG += f" | OK found={len(hits)}"
    else:
        _LAST_GOOGLE_MAPS_DIAG += " | empty (no cards parsed)"
    logger.info("google_maps_search: %s", _LAST_GOOGLE_MAPS_DIAG)
    return hits
```

- [ ] **Step 1: Create `tools/google_maps_tool.py`** with the full implementation above
- [ ] **Step 2: Run unit tests**
  Run: `python -m pytest tests/test_google_maps_tool.py -v`
  Expected: All tests pass
- [ ] **Step 3: Commit**
  ```bash
  git add tools/google_maps_tool.py
  git commit -m "feat: add google_maps_tool (Playwright-based, no API key)"
  ```

### Task 3: Register `google_maps_search` in the tool registry

**Files:**
- Modify: `tools/registry.py`

**Interfaces:**
- Consumes: `google_maps_search` (from `tools.google_maps_tool`)
- Produces: `TOOL_CATALOG` includes new entry; `resolve_callable("google_maps_search")` returns the function

Add to `TOOL_CATALOG` list (after `meta_ads_search` entry):
```python
{
    "id": "google_maps_search",
    "label": "Google Maps Place Search (Playwright)",
    "agents": ["discovery"],
},
```

Update `resolve_callable` to handle the new tool_id:
```python
if tool_id == "google_maps_search":
    from tools.google_maps_tool import google_maps_search
    return google_maps_search
```

- [ ] **Step 1: Edit `tools/registry.py`** — add catalog entry + resolve_callable branch
- [ ] **Step 2: Verify import works**
  Run: `python -c "from tools.google_maps_tool import google_maps_search; print('OK')"`
  Run: `python -c "from tools.registry import resolve_callable, catalog_for_agent; assert resolve_callable('google_maps_search') is not None; assert any(t['id']=='google_maps_search' for t in catalog_for_agent('discovery'))"`
- [ ] **Step 3: Run existing registry tests**
  Run: `python -m pytest tests/test_agent_control.py::test_validate_tool_ids_discovery_required tests/test_agent_control.py::test_clamp_discovery_tools_intersects_allowed -v`
  Expected: PASS (existing tests should be unaffected since new tool is optional)
- [ ] **Step 4: Commit**
  ```bash
  git add tools/registry.py
  git commit -m "feat: register google_maps_search in tool registry"
  ```

### Task 4: Integrate into `DiscoveryAgent.run()`

**Files:**
- Modify: `agents/discovery_agent.py`

**Interfaces:**
- Consumes: `google_maps_search` (via `resolve_callable`), `filter_prospect_hits` (already imported), `tool_enabled` (already imported), `Recorder.agent_run` (already used)
- Produces: `raw` hits from Google Maps appended to search pipeline

**Change 1** — Add to `enabled_tools` default (line ~120):
```python
self.enabled_tools = list(
    enabled_tools
    if enabled_tools is not None
    else (profile.get("enabled_tools") if profile else None)
    or ["meta_ads_search", "google_maps_search", "web_search",
        "crm_write_leads", "llm_chat"]
)
```

**Change 2** — Insert Google Maps search block after Meta Ads (after the Meta Ads `if` block around line 170, before the DuckDuckGo block at line 172):
```python
# 3) Google Maps — local businesses with addresses/phones/ratings
if len(raw) < max_results and tool_enabled(self.enabled_tools, "google_maps_search"):
    run.record_api("playwright", "google_maps")
    gm_fn = resolve_callable("google_maps_search")
    if gm_fn:
        gm_hits = filter_prospect_hits(
            gm_fn(seed_query, region="Tunisia", max_results=max(max_results, 10))
        )
        existing_urls = {r.get("url") for r in raw}
        for hit in gm_hits:
            if hit.get("url") not in existing_urls:
                raw.append(hit)
        raw = raw[:max_results]
```

Insert **before** the existing DuckDuckGo block (line 172), so the order becomes: Meta Ads → Google Maps → DuckDuckGo.

- [ ] **Step 1: Edit `agents/discovery_agent.py`** — add to defaults + insert search block
- [ ] **Step 2: Run existing agent tests**
  Run: `python -m pytest tests/test_agent_control.py -v`
  Expected: All pass (no regressions in profile/required-tool logic)
- [ ] **Step 3: Run full test suite (unit, no live)**
  Run: `python -m pytest tests/ -v -k "not live"`
  Expected: All pass
- [ ] **Step 4: Commit**
  ```bash
  git add agents/discovery_agent.py
  git commit -m "feat: integrate google_maps_search into DiscoveryAgent tool chain"
  ```

### Task 5: Final verification

- [ ] **Step 1: Run full test suite**
  Run: `python -m pytest tests/ -v -k "not live"`
  Expected: All pass including new `test_google_maps_tool.py`
- [ ] **Step 2: Run existing test suites unchanged**
  Run: `python -m pytest tests/test_agent_control.py tests/test_crm_api.py tests/test_tools.py -v`
  Expected: All pass