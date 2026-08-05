# Spec: `google_maps_tool` for Discovery Agent

## 1. Overview

**Goal:** Add a Google Maps place-search lead source to the Discovery Agent so it can find real local businesses (e.g. restaurants, plumbers, clinics) the same way it already uses DuckDuckGo and Meta Ad Library.

**Constraints honored:**
- No paid APIs (PRD §1.5, §1.6). Uses Playwright headless Chromium — same free stack as `scrape_tool`, `seo_audit_tool`.
- No API key required.
- Tunisia-first, region-overrideable.
- Hits the CRM via the same `create_lead_from_search_hit` path as existing tools.

## 2. Architecture & Placement

```
google_maps_tool.py (NEW)  →  returns List[Dict{title,url,snippet,...}]
      ↓
DiscoveryAgent.run()       →  filters via filter_prospect_hits(), writes leads via recorder
      ↓
CRM service (crm/service.py) → leads table (status="raw", source="google_maps")
```

This mirrors the exact flow of `meta_ads_tool` → `DiscoveryAgent.run()` → `Recorder.create_lead_from_hit()`.

### 2.1 Tool Registry Entry (`tools/registry.py`)

Add to `TOOL_CATALOG`:
```python
{
    "id": "google_maps_search",
    "label": "Google Maps Place Search (Playwright)",
    "agents": ["discovery"],
},
```
- **Not** added to `DISCOVERY_REQUIRED_TOOLS` (only `web_search` + `llm_chat` are required).
- `DISCOVERY_FORCE_IF_ALLOWED` unchanged.
- `resolve_callable("google_maps_search")` returns `google_maps_search` function.

### 2.2 DiscoveryAgent Integration (`agents/discovery_agent.py`)

**Default `enabled_tools`**: add `"google_maps_search"` to the defaults list:
```python
self.enabled_tools = list(enabled_tools or ... or [
    "meta_ads_search", "google_maps_search", "web_search",
    "crm_write_leads", "llm_chat"
])
```

**Search flow in `run()`**: insert after Meta Ads, before DuckDuckGo fallback:
```python
# 3) Google Maps — local businesses with real addresses/phones
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

**No changes** to LLM report generation, lead insertion, or enrichment logic — those already iterate over `raw`.

### 2.3 HeadAgent Awareness (`agents/head_agent.py`)

`plan_discovery` already calls `_load_discovery_allowed()` which reads the discovery profile's `enabled_tools` and falls back to `catalog_for_agent("discovery")`. Once `google_maps_search` is registered, HeadAgent will see it as an option in its tool catalog. No code change needed.

## 3. `google_maps_tool` API

### 3.1 Signature
```python
def google_maps_search(
    query: str,
    region: str = "Tunisia",
    max_results: int = 10,
) -> List[Dict[str, Any]]:
```

### 3.2 Parameters
| Param | Source (from UI/API) | Purpose |
|---|---|---|
| `query` | Keywords / Business Type | e.g. "plumber", "pizza restaurant" |
| `region` | Where — City / Region | e.g. "Tunis, Tunisia" (default) |
| `max_results` | Max results limit | Capped at 50 per PRD §2.3 limitation |

### 3.3 Return Shape
Each hit must be compatible with `filter_prospect_hits()` and `create_lead_from_search_hit()`:
```python
{
    "title": "Pizza Palace",                    # business name
    "url": "https://pizzapalace.tn",            # website URL (fallback to maps URL)
    "snippet": "⭐ 4.2 (120 reviews) · 123 Main St, Tunis · +216 71 000 000",  # for CRM status_notes
    # extra metadata (stored alongside, not in core snippet):
    "address": "123 Main St, Tunis, Tunisia",
    "phone": "+216 71 000 000",
    "rating": 4.2,
    "review_count": 120,
    "category": "Restaurant",
    "google_maps_url": "https://www.google.com/maps/place/Pizza+Palace...",
}
```

### 3.4 Extraction Logic (Playwright)
1. Launch headless Chromium via `sync_playwright()` (same pattern as `scrape_tool.py`).
2. Navigate to `https://www.google.com/maps/search/{query}+{region}` with realistic `User-Agent`.
3. Wait for `div[role="article"]` or `.Nv2Tne` elements (business result cards).
4. For each card (up to `max_results`):
   - **Name**: `h3` text or `aria-label` of the card link.
   - **URL**: Resolve redirect link → extract actual business website (if present in card), else Google Maps URL.
   - **Address/Phone**: Regex on card inner text (e.g. `/\+\d{8,15}/` for phone, `/\d+\s.*St/,.*Tunisia/` for address).
   - **Rating**: `⭐` character or `font-vcard` class, `aria-label` containing "stars".
   - **Review count**: Extract number from "120 reviews" pattern.
5. Rate-limit: `time.sleep(1.1)` between card inspections (1 req/sec policy, robots.txt-aware).
6. Filter junk hosts (reuse `_JUNK_HOST_NEEDLES` from `tools/web_search_tool.py` plus Google domains).

## 4. Error Handling

- **No leads found** → return `[]` (matches `web_search_tool` / `meta_ads_tool` convention).
- **Playwright timeout/error** → log via `logging.getLogger(__name__)`, return `[]` or partial results.
- **Robots.txt disallowed**: Google Maps has no restrictive robots for search results, but we check to follow PRD policy (same as `scrape_tool._robots_allows`).
- **Diagnostic**: expose `get_last_google_maps_diag()` like `web_search_tool.get_last_web_search_diag()` for debugging / ops prints.

## 5. Configuration (No new env vars required)

- No `GOOGLE_API_KEY` needed (free scraping approach).
- Uses existing `Playwright` install from `requirements.txt`.
- Region defaults to `"Tunisia"` (can be overridden at runtime).
- No new `.env` variables needed.

### Region Parameter Flow
| Layer | Key | Default |
|---|---|---|
| `DiscoveryAgent.run()` | hardcoded `region="Tunisia"` | Matches PRD Tunisia-first constraint |
| `crm/router.py` `DiscoveryStartRequest` | (future) — accepts optional `region` | Could pass through if UI adds it |
| CLI `scripts/real_verification.py --google-maps` | CLI arg | For live testing without CRM

## 6. Testing (`tests/test_google_maps_tool.py`)

### 6.1 Unit Tests (mocked Playwright — no CRM writes)
These tests mock `sync_playwright()` to verify extraction logic without any network or real CRM interaction. **No real leads are inserted** (per `.cursor/rules/real-data-only.mdc`).

| Test | Description |
|---|---|
| `test_extract_fields_from_html` | Mock Playwright HTML fixture with 3 business cards → assert title, url, address, rating, phone extracted correctly |
| `test_junk_filtering` | Inject a wikipedia.org result in mock HTML → assert filtered by `filter_prospect_hits` |
| `test_max_results_respected` | `max_results=3` → returns at most 3 hits |
| `test_region_in_url` | Assert `region="Sousse"` passed through to Google Maps search URL |
| `test_returns_empty_on_timeout` | Mock `page.goto` raise TimeoutError → returns `[]` + logs diagnostic |
| `test_extracts_website_url` | Mock card with website link → URL points to business's real site (not maps.google.com) |

**Mocking strategy**: Patch `playwright.sync_api.sync_playwright` to yield a fake `Page` with controlled `.content()` returning HTML fixture strings. Mock HTML fixtures stored as inline strings in tests (no `.html` fixture files needed — avoids file management overhead).

### 6.2 Live Test (real scraping — gated behind `@pytest.mark.live`)
Following the existing `tests/test_live.py` pattern:
```python
@pytest.mark.live
def test_google_maps_search_live():
    if os.getenv("RUN_LIVE_TESTS") != "1":
        pytest.skip("Set RUN_LIVE_TESTS=1 for live Google Maps scraping")
    results = google_maps_search("plumber", region="Tunis, Tunisia", max_results=3)
    assert len(results) >= 1
    assert results[0]["url"].startswith("http")
    assert results[0]["title"]
```
This is **opt-in only** and produces **real leads** via the DiscoveryAgent pipeline (inspected via `/crm/ui/leads`).

### 6.3 Real-Data-Only Compliance
Per `.cursor/rules/real-data-only.mdc`:
- ❌ No `example.com` URLs, no "Test" names, no `source=pytest`
- ✅ Live scraping test produces real leads with `source=google_maps` via the real pipeline
- ✅ Unit tests use **only** mocked data — no CRM writes at all

## 7. Integration Points — Summary

| File | Change |
|---|---|
| `tools/google_maps_tool.py` | **NEW** — main implementation |
| `tools/registry.py` | Add `google_maps_search` to `TOOL_CATALOG`, update `resolve_callable` |
| `agents/discovery_agent.py` | Add to defaults, insert into search flow |
| `tests/test_google_maps_tool.py` | **NEW** — unit tests with mocked Playwright (inline HTML fixtures) |
| `scripts/real_verification.py` | Optional: add `--google-maps` flag for live testing |
| `doc5_tool_api_specs.md` | Update tool spec table |
| `ARCHITECTURE.md` | Mark `google_maps_tool` as ✅ Implemented |
| `doc7_environment_config.md` | No new env vars needed (confirmed — free scraping) |
| `docs/crm/AGENT_INTEGRATION.md` | Update available_tools list for discovery |
| `.cursor/rules/real-data-only.mdc` | Followed: no mock CRM writes, live tests gated behind `@pytest.mark.live` |

## 8. Out of Scope
- Google Places API (paid) integration.
- Google Maps reverse geocoding.
- Storing extra fields (phone, rating) in dedicated CRM columns — stored in `status_notes` / `snippet` for now (same as existing lead flow).
- Social / reviews extraction from individual business pages (left to `AnalysisAgent` + `scrape_tool` later).
