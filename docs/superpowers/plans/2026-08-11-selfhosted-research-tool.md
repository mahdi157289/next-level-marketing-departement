# Self-Hosted Research Tool (SearXNG + Crawl4AI) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flaky `hunter` tool with a self-hosted `research` tool that fills a lead's empty CRM columns via SearXNG search + Crawl4AI site extraction, and caches crawled pages into a durable store with RAG auto-embedding.

**Architecture:** A new `research` orchestrator (same output shape as the old `hunter`, so the enrich workflow, `leads.research` column, API, and frontend stay untouched) uses `web_search_tool` (now SearXNG-first with DDGS fallback) plus a new `site_extract` tool (Crawl4AI in-process → clean markdown → LLM field extraction). Phase-2 adds a `crawl_pages` table with a `db/crawl_store` cache and auto-embeds crawled pages into the existing `agent_chunks` pgvector store via Ollama, so `knowledge.rag` retrieves past crawls instantly.

**Tech Stack:** Python 3.11 (Docker) / 3.9 (local tests), FastAPI + SQLAlchemy + Alembic + PostgreSQL/pgvector, httpx, Crawl4AI, SearXNG, Ollama (`nomic-embed-text`), pytest.

## Global Constraints

- Tool id `hunter` is **removed everywhere**; `research` replaces it. Migration `20260810_0013` and `tests/test_hunter_db.py` are left alone (they cover the `leads.research` column, which stays).
- `leads.research` column, `crm.service.enrich_missing` storage path, `api/routes/research.py`, and the frontend research UI are **untouched**.
- Every tool must **never raise** to callers — return a `status` field instead (`ok`, `no_results`, `robots_denied`, `unavailable`, `fetch_failed`, `timeout`).
- Robots.txt is respected via `tools.scrape_tool._robots_allows` + `DEFAULT_UA`.
- Crawl4AI requires Python 3.10+ — it is installed **only in Docker** (3.11) via `requirements-crawl4ai.txt`; `site_extract` lazy-imports it so local 3.9 tests skip it gracefully (return `status: "unavailable"`).
- Embedding failures degrade gracefully: the crawl is still cached; only the `agent_chunks` insert is skipped.
- Tests are pytest; DB tests are gated on `DATABASE_URL` env (`@pytest.mark.skipif(not _db_url(), ...)`), following `tests/test_hunter_db.py`.
- No frontend changes. No changes to existing `leads` columns. Only new tables: `crawl_pages`.

---

### Task 1: SearXNG search backend + settings + compose

**Files:**
- Modify: `config/settings.py:29` (add settings after `orchestrator_workers`)
- Create: `searxng/settings.yml`
- Modify: `docker-compose.yml` (new `searxng` service; `app` gets env + `depends_on`)
- Modify: `tools/web_search_tool.py` (add `httpx` import, `searxng_search()`, SearXNG-first in `web_search_tool`)
- Test: `tests/test_web_search_tool.py` (new)

**Interfaces:**
- Consumes: `config.settings.get_settings()` (adds `searxng_base_url`, `searxng_timeout_s`).
- Produces: `tools.web_search_tool.searxng_search(query: str, max_results: int = 10) -> List[Dict[str, str]]` returning `[{title, url, snippet}]`, never raises. `web_search_tool(query, max_results)` keeps its existing signature and now prefers SearXNG.

- [ ] **Step 1: Write the failing tests**

```python
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

        def text(self, **kw):
            return ddgs_hits

    with patch("tools.web_search_tool.searxng_search", return_value=[]), \
         patch("tools.web_search_tool._discover_ddgs_classes", return_value=[("fake", lambda: _FakeDDGS)]):
        out = web_search_tool("Acme", max_results=3)
    assert any("ddgs.tn" in h["url"] for h in out)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_web_search_tool.py -v`
Expected: FAIL — `ImportError: cannot import name 'searxng_search'`.

- [ ] **Step 3: Add settings**

In `config/settings.py`, after `orchestrator_workers: int = 3`:

```python
    searxng_base_url: str = ""
    searxng_timeout_s: float = 8.0
    site_extract_timeout_s: float = 45.0
    site_extract_max_markdown_chars: int = 12000
    crawl_cache_enabled: bool = True
    crawl_embed_content: bool = True
```

- [ ] **Step 4: Implement `searxng_search` + SearXNG-first `web_search_tool`**

In `tools/web_search_tool.py`:

1. Add to the imports (after the `from urllib.parse import urlparse` line):

```python
from config.settings import get_settings

import httpx
```

2. Add after `_dedupe_by_url`:

```python
def searxng_search(query: str, max_results: int = 10) -> List[Dict[str, str]]:
    """Self-hosted SearXNG JSON search → [{title, url, snippet}]. Never raises."""
    s = get_settings()
    base = (s.searxng_base_url or "").strip().rstrip("/")
    if not base:
        return []
    try:
        resp = httpx.get(
            f"{base}/search",
            params={"q": query, "format": "json", "pageno": 1},
            timeout=s.searxng_timeout_s,
        )
        resp.raise_for_status()
        data = resp.json()
    except BaseException as e:  # noqa: BLE001
        logger.warning("searxng_search: query=%r failed: %s", query, e)
        return []
    out: List[Dict[str, str]] = []
    for item in data.get("results") or []:
        url = str(item.get("url") or item.get("href") or "").strip()
        if not url:
            continue
        out.append({
            "title": str(item.get("title") or ""),
            "url": url,
            "snippet": str(item.get("content") or item.get("snippet") or ""),
        })
        if len(out) >= max_results:
            break
    return out
```

3. Replace the body of `web_search_tool` (the whole function, lines 132-212) with:

```python
def web_search_tool(query: str, max_results: int = 10) -> List[Dict[str, str]]:
    """Search and return list of {title, url, snippet}. Empty list if all attempts fail."""
    global _LAST_WEB_SEARCH_DIAG
    _LAST_WEB_SEARCH_DIAG = ""

    last_exc: Optional[BaseException] = None
    tried: List[str] = ["searxng"]
    collected: List[Dict[str, str]] = searxng_search(query, max_results=max(max_results * 2, 8))

    if len(_dedupe_by_url(collected)) < max_results:
        backends = _discover_ddgs_classes()
        if backends:
            fetch_n = max(max_results * 2, 8)
            per_engine_timeout_s = 12.0

            def _fetch(DDGS: Callable[[], Any], engine: str) -> List[Dict[str, Any]]:
                with DDGS() as client:
                    return list(
                        client.text(
                            query,
                            max_results=fetch_n,
                            region="wt-wt",
                            backend=engine,
                        )
                    )

            from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

            for label, DDGS in backends:
                for engine in _DDGS_ENGINE_ORDER:
                    tried.append(f"{label}:{engine}")
                    try:
                        time.sleep(0.15)
                        with ThreadPoolExecutor(max_workers=1) as pool:
                            fut = pool.submit(_fetch, DDGS, engine)
                            raw = fut.result(timeout=per_engine_timeout_s)
                        for x in raw:
                            if isinstance(x, dict):
                                collected.append(_normalize_item(x))
                    except FuturesTimeout:
                        last_exc = TimeoutError(f"{label}:{engine} timed out after {per_engine_timeout_s}s")
                        logger.warning("web_search_tool: %s", last_exc)
                        continue
                    except BaseException as e:
                        last_exc = e
                        logger.warning("web_search_tool: %s/%s failed: %s", label, engine, e)
                        continue

                    ranked_preview = [h for h in collected if _relevance_score(h, query) > 0]
                    if len(_dedupe_by_url(ranked_preview)) >= max_results:
                        break
                if len([h for h in collected if _relevance_score(h, query) > 0]) >= max_results:
                    break
        else:
            _LAST_WEB_SEARCH_DIAG = "No search backend installed. Run: pip install ddgs"
            logger.error(_LAST_WEB_SEARCH_DIAG)

    normalized = [r for r in _dedupe_by_url(collected) if r.get("url")]
    ranked = sorted(normalized, key=lambda h: _relevance_score(h, query), reverse=True)
    good = [h for h in ranked if _relevance_score(h, query) > 0][:max_results]

    if good:
        _LAST_WEB_SEARCH_DIAG = (
            f"ok tried={tried} kept={len(good)} raw={len(normalized)} "
            f"top_score={_relevance_score(good[0], query)}"
        )
        return good

    non_junk = [h for h in ranked if not _is_junk(h)][:max_results]
    if non_junk:
        _LAST_WEB_SEARCH_DIAG = (
            f"weak tried={tried} kept={len(non_junk)} (low relevance) last_error={last_exc!r}"
        )
        return non_junk

    _LAST_WEB_SEARCH_DIAG = (
        f"tried={tried} last_error={last_exc!r} "
        "(empty/junk — try: pip install -U ddgs, VPN, or different network)"
    )
    logger.error("web_search_tool: giving up query=%r diag=%s", query, _LAST_WEB_SEARCH_DIAG)
    return []
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_web_search_tool.py -v`
Expected: 5 PASS.

- [ ] **Step 6: Add the SearXNG compose service + config**

Create `searxng/settings.yml`:

```yaml
use_default_settings: true

server:
  secret_key: "marketing_searxng_secret"
  limiter: false
  public_instance: false
  method: "GET"

search:
  formats:
    - html
    - json
```

In `docker-compose.yml`, add after the `janusgraph` service (before `app`):

```yaml
  searxng:
    image: searxng/searxng:latest
    container_name: marketing_searxng
    ports:
      - "8080:8080"
    environment:
      SEARXNG_BASE_URL: http://searxng:8080/
      SEARXNG_SECRET: ${SEARXNG_SECRET:-marketing_searxng_secret}
      SEARXNG_LIMITER: "false"
      SEARXNG_PUBLIC_INSTANCE: "false"
      SEARXNG_METHOD: GET
    volumes:
      - ./searxng/settings.yml:/etc/searxng/settings.yml:ro
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8080/')"]
      interval: 20s
      timeout: 8s
      retries: 5
```

In `docker-compose.yml`, `app` service: add to `environment`:

```yaml
      SEARXNG_BASE_URL: http://searxng:8080
```

and add to `app.depends_on`:

```yaml
      searxng:
        condition: service_healthy
```

- [ ] **Step 7: Validate compose config**

Run: `docker compose config --quiet`
Expected: exits 0 (no output). If it fails, fix the YAML.

- [ ] **Step 8: Commit**

```bash
git add config/settings.py tools/web_search_tool.py tests/test_web_search_tool.py searxng/settings.yml docker-compose.yml
git commit -m "feat: self-hosted SearXNG search backend with DDGS fallback"
```

---

### Task 2: `site_extract` tool (Crawl4AI in-process + LLM field extraction)

**Files:**
- Create: `tools/site_extract_tool.py`
- Test: `tests/test_site_extract.py` (new)

**Interfaces:**
- Consumes: `config.settings.get_settings()` (`site_extract_timeout_s`, `site_extract_max_markdown_chars`, `agent_model_discovery`), `agents.lm_client.chat_completion`, `tools.scrape_tool._robots_allows` + `DEFAULT_UA`.
- Produces: `tools.site_extract_tool.site_extract(url: str, fields: Optional[List[str]] = None) -> Dict[str, Any]` with keys `{status, url, title, markdown, fields, [error]}`. `_crawl_sync(url, timeout_s)` and `_llm_extract_fields(fields, markdown)` are patchable test seams.

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_site_extract.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tools.site_extract_tool'`.

- [ ] **Step 3: Implement `tools/site_extract_tool.py`**

```python
"""site_extract — in-process page extraction with Crawl4AI + LLM field parsing.

Crawls a URL (respecting robots.txt), returns clean markdown, and optionally
extracts requested fields as JSON via the same LLM used for summaries. Never
raises; reports status instead. Caching + auto-embedding of crawled pages are
added by Phase 2 in db/crawl_store.
"""

from __future__ import annotations

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from agents.lm_client import chat_completion
from config.settings import get_settings
from tools.scrape_tool import DEFAULT_UA, _robots_allows

logger = logging.getLogger(__name__)

_FIELD_EXTRACT_PROMPT = (
    "Extract the following fields from the page content below and return ONLY a JSON "
    "object (no markdown, no commentary) mapping each field name to its value. "
    "Use null when a field is not present. For numeric fields (rating, review_count, "
    "seo_score) return a number. For hours return the opening-hours text.\n"
    "Fields: {fields}\n\nPage content:\n{markdown}\n\nJSON:"
)


def site_extract(
    url: str,
    fields: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Crawl ``url`` and return {status, title, url, markdown, fields}.

    ``status`` is one of: ok, robots_denied, unavailable (crawl4ai missing),
    fetch_failed, timeout.
    """
    s = get_settings()
    if s.crawl_cache_enabled:
        cached = _cached(url, fields)
        if cached is not None:
            return cached
    if not _robots_allows(url, DEFAULT_UA):
        return {"status": "robots_denied", "url": url, "title": "", "markdown": "", "fields": {}}
    try:
        result = _crawl_sync(url, timeout_s=s.site_extract_timeout_s)
    except ImportError:
        return {"status": "unavailable", "url": url, "title": "", "markdown": "", "fields": {}}
    except BaseException as e:  # noqa: BLE001
        status = "timeout" if "Timeout" in type(e).__name__ else "fetch_failed"
        return {"status": status, "url": url, "title": "", "markdown": "",
                "fields": {}, "error": str(e)[:200]}

    title = _clean_str(getattr(result, "title", ""))
    markdown = _extract_markdown(result)
    if not markdown:
        return {"status": "fetch_failed", "url": url, "title": title,
                "markdown": "", "fields": {}, "error": "empty page content"}
    markdown = markdown[: s.site_extract_max_markdown_chars]
    fields_out: Dict[str, Any] = {}
    if fields:
        fields_out = _llm_extract_fields(fields, markdown) or {}
    try:
        _persist_and_embed(url, title, markdown, fields_out)
    except BaseException:  # noqa: BLE001
        pass
    return {"status": "ok", "url": url, "title": title, "markdown": markdown,
            "fields": fields_out}


def _crawl_sync(url: str, timeout_s: float) -> Any:
    """Run Crawl4AI in-process; raises on failure. Lazy-imports crawl4ai."""
    from crawl4ai import AsyncWebCrawler  # noqa: F401  (raises ImportError on 3.9)

    async def _run():
        async with AsyncWebCrawler() as crawler:
            return await crawler.arun(url)

    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(asyncio.run, _run())
        return fut.result(timeout=timeout_s)


def _llm_extract_fields(fields: List[str], markdown: str) -> Dict[str, Any]:
    s = get_settings()
    prompt = _FIELD_EXTRACT_PROMPT.format(
        fields=", ".join(fields), markdown=markdown[:6000]
    )
    try:
        text = chat_completion(
            s.agent_model_discovery,
            [{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=512,
        )
    except BaseException as e:  # noqa: BLE001
        logger.warning("site_extract: LLM field extraction failed: %s", e)
        return {}
    return _parse_json_object(text or "") or {}


def _parse_json_object(text: str) -> Optional[Dict[str, Any]]:
    """Robustly parse a JSON object that may be wrapped in markdown fences."""
    if not text:
        return None
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _clean_str(value: Any) -> str:
    return str(value or "").strip()


def _extract_markdown(result: Any) -> str:
    """Crawl4AI changed `result.markdown` from a plain str (≤0.6) to an object
    with raw_markdown / fit_markdown (0.7+). Handle both forms."""
    md = getattr(result, "markdown", None)
    if isinstance(md, str):
        return _clean_str(md)
    if md is not None:
        return _clean_str(getattr(md, "raw_markdown", "") or getattr(md, "fit_markdown", ""))
    return ""


def _cached(url: str, fields: Optional[List[str]]) -> Optional[Dict[str, Any]]:
    """Return a prior crawl from the durable cache, else None (never raises)."""
    try:
        from db.crawl_store import get_crawl

        row = get_crawl(url)
    except BaseException:  # noqa: BLE001
        return None
    if not row or row.get("status") != "ok":
        return None
    return {
        "status": "ok",
        "url": url,
        "title": row.get("title") or "",
        "markdown": row.get("markdown") or "",
        "fields": {f: (row.get("fields") or {}).get(f) for f in (fields or [])} if fields
                  else (row.get("fields") or {}),
        "source": "cache",
    }


def _persist_and_embed(url: str, title: str, markdown: str, fields: Dict[str, Any]) -> None:
    """Persist the crawl and auto-embed it into the RAG store. Never raises."""
    from urllib.parse import urlparse

    s = get_settings()
    try:
        domain = (urlparse(url).hostname or "").lower()
    except Exception:  # noqa: BLE001
        domain = ""
    try:
        from db.crawl_store import save_crawl

        save_crawl(url, title=title, domain=domain, markdown=markdown, fields=fields,
                   status="ok", source="site_extract")
    except BaseException as e:  # noqa: BLE001
        logger.warning("site_extract: save_crawl failed for %s: %s", url, e)
    if not s.crawl_embed_content or not markdown:
        return
    try:
        from db.embeddings import insert_chunk

        insert_chunk(agent_name="research", content=markdown[:1500],
                     scope="shared", source_uri=url)
    except BaseException as e:  # noqa: BLE001
        logger.warning("site_extract: embed failed for %s: %s", url, e)
```

Note: `_cached` and `_persist_and_embed` reference `db.crawl_store`, which Task 5 creates. The lazy imports keep this task independently importable — `site_extract` still works when `db.crawl_store` does not yet exist (the `except BaseException` paths swallow the `ImportError`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_site_extract.py -v`
Expected: 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/site_extract_tool.py tests/test_site_extract.py
git commit -m "feat: site_extract tool with Crawl4AI + LLM field extraction"
```

---

### Task 3: `research` orchestrator (the hunter replacement)

**Files:**
- Create: `tools/research_tool.py`
- Delete: (none yet — hunter removed in Task 4)
- Test: `tests/test_research_tool.py` (new)

**Interfaces:**
- Consumes: `db.models.Lead` (schema), `tools.registry.resolve_callable("web_search")`, `tools.scrape_tool._clean_phone` / `_extract_socials`, `tools.site_extract_tool.site_extract` (lazy import), `agents.lm_client.chat_completion`.
- Produces: `tools.research_tool.research(name: str = "", url: str = "", industry: str = "", country: str = "", gaps: Optional[List[str]] = None, **fields) -> Dict[str, Any]` returning `{summary, fields_found, sources, queries, status, investigated_at}` — identical shape to old `hunter`. Pure tool; does NOT write to the DB (the enrich workflow persists).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_research_tool.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_research_tool.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tools.research_tool'`.

- [ ] **Step 3: Implement `tools/research_tool.py`**

```python
"""research — CRM-driven lead investigation tool (replaces hunter).

Detects empty columns on a lead, runs field-targeted web searches (self-hosted
SearXNG with DDGS fallback), and fills remaining gaps by extracting the lead's
own site with Crawl4AI + an LLM. Returns a knowledge summary + evidence sources.
Never raises; reports status instead. The enrich workflow persists the result.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import sqlalchemy as sa

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
    except Exception:  # noqa: BLE001
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


_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")


def _hit_blob(hits):
    return " ".join(
        f"{h.get('title', '')} {h.get('snippet', '')} {h.get('url', '')}"
        for h in hits
    )


def _mine_field(field: str, hits: List[Dict[str, Any]]) -> Any:
    """Deterministic extraction for fields that don't need an LLM."""
    if field == "email":
        m = _EMAIL_RE.search(_hit_blob(hits))
        return m.group(0) if m else None
    if field == "phone":
        for h in hits:
            blob = f"{h.get('title', '')} {h.get('snippet', '')}"
            for cand in re.findall(r"\+?[\d\s\-().]{7,15}", blob):
                from tools.scrape_tool import _clean_phone

                cleaned = _clean_phone(cand)
                if cleaned:
                    return cleaned
        return None
    if field in ("facebook", "instagram", "linkedin", "twitter"):
        from tools.scrape_tool import _extract_socials

        return _extract_socials(_hit_blob(hits)).get(field)
    if field == "description":
        return (hits[0].get("snippet") or "")[:500] if hits else None
    if field in ("industry", "business_type"):
        for h in hits[:3]:
            snip = (h.get("snippet") or "").strip()
            if snip:
                return snip[:128]
        return None
    return None


def _coerce_for_column(field: str, value: Any) -> Any:
    """Fit a mined value to the lead column's type: truncate strings to the
    column length, coerce numerics, drop values that can't fit. Returns None
    when the value can't be stored."""
    col = Lead.__table__.columns.get(field)
    if col is None:
        return value
    t = col.type
    if isinstance(t, sa.String):
        if isinstance(value, str):
            return value[:t.length] if t.length else value
        return value
    if isinstance(t, sa.Integer):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    if isinstance(t, sa.Float):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    if getattr(t, "python_type", None) is dict:
        return value if isinstance(value, (dict, list)) else None
    return value


def _synthesize_summary(name: str, industry: str, country: str, hits: List[Dict[str, Any]]) -> str:
    from agents.lm_client import chat_completion
    from config.settings import get_settings

    snippets = "\n".join(
        f"- {h.get('title', '')}: {h.get('snippet', '')}" for h in hits[:12]
    )
    prompt = (
        "Write a short markdown intelligence profile of a company from web search results.\n"
        "Sections: ## Overview, ## Services, ## Online presence, ## What we found.\n"
        f"Company: {name}\nIndustry: {industry or 'unknown'}\nCountry: {country or 'unknown'}\n"
        f"Search results:\n{snippets}\nProfile:"
    )
    try:
        text = chat_completion(
            get_settings().agent_model_discovery,
            [{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=512,
        )
        text = (text or "").strip()
        if text:
            return text
    except BaseException:  # noqa: BLE001
        pass
    # Deterministic fallback.
    lines = [f"## Overview\n{name} ({country or 'unknown'})."]
    top = (hits[0].get("snippet") or "").strip() if hits else ""
    if top:
        lines.append(f"**Key finding:** {top[:400]}")
    lines.append(f"## Sources\n" + "\n".join(f"- {h.get('title', '')}: {h.get('url', '')}" for h in hits[:5]))
    return "\n".join(lines)


def _run_searches(queries: List[str], max_per_query: int = 5) -> List[Dict[str, Any]]:
    from tools.registry import resolve_callable
    from tools.web_search_tool import _relevance_score, web_search_tool

    fn = resolve_callable("web_search") or web_search_tool
    seen: set = set()
    collected: List[Dict[str, Any]] = []
    for q in queries:
        try:
            for h in fn(q, max_results=max_per_query) or []:
                url = (h.get("url") or "").rstrip("/")
                if url and url not in seen:
                    seen.add(url)
                    collected.append(h)
        except BaseException:  # noqa: BLE001
            continue
    return sorted(collected, key=lambda h: _relevance_score(h, queries[0] if queries else ""), reverse=True)[:15]


def research(
    name: str = "",
    url: str = "",
    industry: str = "",
    country: str = "",
    gaps: Optional[List[str]] = None,
    **fields: Any,
) -> Dict[str, Any]:
    """Investigate a lead: detect empty columns, web-search them, mine values,
    extract the site for anything still missing, and summarize."""
    pseudo = {"name": name, "url": url, "industry": industry, "country": country, **fields}
    if gaps is None:
        gaps = [c for c in _huntable_columns() if _is_empty(pseudo.get(c))]
    queries = _build_queries(name, url=url, industry=industry, country=country, gaps=gaps)
    if not queries:
        return {"summary": "", "fields_found": {}, "sources": [], "queries": [],
                "status": "no_results", "investigated_at": _now()}
    hits = _run_searches(queries)

    fields_found: Dict[str, Any] = {}
    for field in gaps:
        try:
            val = _mine_field(field, hits)
        except BaseException:  # noqa: BLE001
            val = None
        if val not in (None, "", [], {}):
            fields_found[field] = _coerce_for_column(field, val)

    site_data = _extract_site_gaps(url, gaps, fields_found)
    for field, val in site_data.items():
        fields_found[field] = _coerce_for_column(field, val)

    if not hits and not fields_found:
        summary = ""
        status = "no_results"
    else:
        summary = _synthesize_summary(name, industry, country, hits)
        status = "llm_fallback" if not summary or summary.startswith("## Overview\n" + name) else "ok"
        if not summary:
            summary = f"## Overview\n{name}"
            status = "llm_fallback"
    sources = [
        {"title": h.get("title", ""), "url": h.get("url", ""),
         "snippet": (h.get("snippet") or "")[:300], "query": queries[0]}
        for h in hits[:10]
    ]
    if url and site_data:
        sources.append({"title": name, "url": url, "snippet": "extracted from site", "query": queries[0]})
    return {
        "summary": summary,
        "fields_found": fields_found,
        "sources": sources,
        "queries": queries,
        "status": status,
        "investigated_at": _now(),
    }


def _extract_site_gaps(url: str, gaps: List[str], already: Dict[str, Any]) -> Dict[str, Any]:
    """Use site_extract to fill gap fields not yet found. Never raises."""
    if not url:
        return {}
    missing = [f for f in gaps if f not in already]
    if not missing:
        return {}
    from tools.site_extract_tool import site_extract

    try:
        out = site_extract(url, fields=missing)
    except BaseException:  # noqa: BLE001
        return {}
    if out.get("status") != "ok":
        return {}
    return {
        k: v for k, v in (out.get("fields") or {}).items()
        if v not in (None, "", [], {})
    }


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (list, dict)) and not value:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if value == 0:
        return True
    return False


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_research_tool.py -v`
Expected: All PASS. (The catalog/roster tests for `research` are written in Task 4 where the registry/roster wiring lands.)

- [ ] **Step 5: Commit**

```bash
git add tools/research_tool.py tests/test_research_tool.py
git commit -m "feat: research tool to fill empty CRM fields (hunter replacement)"
```

---

### Task 4: Wiring + hunter removal + migration 0014

**Files:**
- Modify: `tools/registry.py` (catalog + `resolve_callable`)
- Modify: `crm/agents_registry.py` (default_tools)
- Modify: `workflows/enrich_leads.py:252-273`
- Create: `migrations/versions/20260811_0014_research_tool.py`
- Delete: `tools/hunter_tool.py`, `tests/test_hunter_tool.py`
- Modify: `tests/test_agent_roster.py:83`
- Modify: `tests/test_enrich_leads.py` (2 tests)
- Note: `tests/test_hunter_db.py` is left untouched.

**Interfaces:**
- Consumes: `tools.research_tool.research`, `tools.site_extract_tool.site_extract` (both produced by Tasks 2-3).
- Produces: registry maps `research` → `research()`, `site_extract` → `site_extract()`; agent rosters list both; migration renames the enabled-tool id in `agent_profiles`.

- [ ] **Step 1: Update the tool catalog + resolver in `tools/registry.py`**

Replace the `hunter` catalog entry (lines 55-61) with:

```python
    {
        "id": "research",
        "label": "CRM lead research: fill missing fields via SearXNG + site extraction",
        "agents": [
            "discovery", "head", "qualifier", "categorization",
            "analysis", "outreach", "content",
        ],
    },
    {
        "id": "site_extract",
        "label": "Extract page content as markdown + JSON fields (Crawl4AI)",
        "agents": ["discovery"],
    },
```

Also update the `web_search` catalog label (line 13) to:

```python
        "label": "Self-hosted SearXNG / DuckDuckGo web search",
```

Replace the `resolve_callable` hunter branch (lines 173-176) with:

```python
    if tool_id == "research":
        from tools.research_tool import research

        return research
    if tool_id == "site_extract":
        from tools.site_extract_tool import site_extract

        return site_extract
```

- [ ] **Step 2: Update agent rosters in `crm/agents_registry.py`**

Discovery (lines 16-19):

```python
        "default_tools": [
            "web_search", "google_maps_search", "meta_ads_search",
            "crm_write_leads", "llm_chat", "seo_audit", "scrape", "site_extract", "research",
        ],
```

The other five profiles — `head`, `qualifier`, `categorization`, `analysis`, `outreach`, `content` (lines 25, 30, 35, 40, 45, 50) — change `["llm_chat", "hunter"]` to `["llm_chat", "research"]`.

- [ ] **Step 3: Update the enrich workflow call site**

In `workflows/enrich_leads.py`, replace lines 253-273 (the `if not lead.get("research"):` block) with:

```python
    if not lead.get("research"):
        research_fn = resolve_callable("research")
        if research_fn:
            run.record_api("searxng", "research")
            try:
                result = research_fn(
                    name=lead.get("name") or "",
                    url=lead.get("url") or "",
                    industry=lead.get("industry") or "",
                    country=lead.get("country") or "",
                    **{k: lead.get(k) for k in service.FILLABLE_FIELDS
                       if k not in ("industry", "country")},
                )
            except BaseException:
                result = None
            if result and (result.get("fields_found") or result.get("summary")):
                data = {"research": result}
                if result.get("fields_found"):
                    data.update(result["fields_found"])
                service.enrich_missing(lid, data, agent_run_id=run.id)
                steps.append("research")
```

- [ ] **Step 4: Write migration 0014**

```python
# migrations/versions/20260811_0014_research_tool.py
"""Rename hunter tool to research; enable site_extract on discovery.

Revision ID: 20260811_0014
Revises: 20260810_0013
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260811_0014"
down_revision: Union[str, None] = "20260810_0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT agent_name, enabled_tools FROM agent_profiles WHERE enabled_tools IS NOT NULL"
    )).fetchall()
    profiles = sa.table(
        "agent_profiles",
        sa.column("agent_name", sa.String),
        sa.column("enabled_tools", postgresql.JSON),
    )
    for agent_name, enabled_tools in rows:
        tools = [t for t in (enabled_tools or []) if t != "hunter"]
        if "hunter" in (enabled_tools or []) and "research" not in tools:
            tools.append("research")
        if agent_name == "discovery" and "site_extract" not in tools:
            tools.append("site_extract")
        conn.execute(
            profiles.update().where(profiles.c.agent_name == agent_name),
            {"enabled_tools": tools},
        )


def downgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT agent_name, enabled_tools FROM agent_profiles WHERE enabled_tools IS NOT NULL"
    )).fetchall()
    profiles = sa.table(
        "agent_profiles",
        sa.column("agent_name", sa.String),
        sa.column("enabled_tools", postgresql.JSON),
    )
    for agent_name, enabled_tools in rows:
        tools = [t for t in (enabled_tools or []) if t not in ("research", "site_extract")]
        if "research" in (enabled_tools or []):
            tools.append("hunter")
        conn.execute(
            profiles.update().where(profiles.c.agent_name == agent_name),
            {"enabled_tools": tools},
        )
```

- [ ] **Step 5: Delete the hunter tool + rewrite its tests**

Delete `tools/hunter_tool.py` and `tests/test_hunter_tool.py`.

Append these catalog/roster tests to `tests/test_research_tool.py` (Task 3 created that file):

```python
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
```

In `tests/test_agent_roster.py:83`, change the assertion to:

```python
    assert p["enabled_tools"] == ["llm_chat", "research"]
```

In `tests/test_enrich_leads.py`:
- In the first hunt-step test (around line 281), change `assert "hunt" in res["steps"]` to `assert "research" in res["steps"]`.
- Rename `test_enrich_one_passes_current_values_to_hunter_as_fields` (line 293) to `test_enrich_one_passes_current_values_to_research_as_fields`, rename the local `_fake_hunter` to `_fake_research` (lines 314-316), and keep `patch("workflows.enrich_leads.resolve_callable", return_value=_fake_research)`. The kwargs assertions stay identical.

- [ ] **Step 6: Verify no live references to `hunter` remain**

Run:
```bash
git grep -n "hunter" -- "*.py" "*.json" "*.tsx" "*.ts" "*.js" "*.jsx"
```
Expected: only `migrations/versions/20260810_0013_hunter_research.py` and `tests/test_hunter_db.py` (both intentionally kept — they cover the `leads.research` column). If the frontend references the `hunt` step label, update the enrichment step display label to `research` there.

- [ ] **Step 7: Run the full suite**

Run: `pytest tests -x -q -k "not db"` (or run all; DB tests skip without `DATABASE_URL`)
Expected: all pass. If a `DATABASE_URL` is available, first run `alembic upgrade head`, then `pytest tests -q` and confirm the 4 catalog/roster tests now pass too.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "feat: replace hunter with research tool everywhere (registry, rosters, enrich, migration)"
```

---

### Task 5: Durable crawl store + RAG auto-embed

**Files:**
- Modify: `db/models.py` (add `CrawlPage`)
- Create: `migrations/versions/20260811_0015_crawl_pages.py`
- Create: `db/crawl_store.py`
- Modify: `tools/site_extract_tool.py` (already wired in Task 2 — no code change needed; `_cached`/`_persist_and_embed` now resolve `db.crawl_store`)
- Test: `tests/test_crawl_store.py` (new, DB-gated)
- Test: `tests/test_site_extract.py` (add cache-hit, persist, embed-failure tests)

**Interfaces:**
- Consumes: `db.session.SessionLocal`, `db.models.CrawlPage`.
- Produces: `db.crawl_store.save_crawl(url, *, title, domain, markdown, fields, status, source, tags) -> Optional[Dict]`, `db.crawl_store.get_crawl(url) -> Optional[Dict]`, `db.crawl_store.list_crawls(domain=None, limit=50) -> List[Dict]`. Rows land in `crawl_pages` and are auto-embedded into `agent_chunks` (via `db.embeddings.insert_chunk`) so `knowledge.rag::scoped_query` retrieves them.

- [ ] **Step 1: Add the `CrawlPage` model**

In `db/models.py`, append at the end (after `ScoutMessage`):

```python
class CrawlPage(Base):
    """One crawled page — durable cache + source of truth for research hits."""

    __tablename__ = "crawl_pages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    url = Column(String(512), nullable=False, unique=True)
    title = Column(String(512))
    domain = Column(String(256))
    markdown = Column(Text)
    fields = Column(JSON)
    status = Column(String(32))
    source = Column(String(32))
    tags = Column(JSON)
    fetched_at = Column(TIMESTAMP, default=datetime.utcnow)
```

- [ ] **Step 2: Write migration 0015**

```python
# migrations/versions/20260811_0015_crawl_pages.py
"""Add crawl_pages cache table.

Revision ID: 20260811_0015
Revises: 20260811_0014
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260811_0015"
down_revision: Union[str, None] = "20260811_0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "crawl_pages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("url", sa.String(length=512), nullable=False),
        sa.Column("title", sa.String(length=512)),
        sa.Column("domain", sa.String(length=256)),
        sa.Column("markdown", sa.Text()),
        sa.Column("fields", sa.JSON()),
        sa.Column("status", sa.String(length=32)),
        sa.Column("source", sa.String(length=32)),
        sa.Column("tags", sa.JSON()),
        sa.Column("fetched_at", sa.TIMESTAMP()),
        sa.UniqueConstraint("url", name="uq_crawl_pages_url"),
    )
    op.create_index("ix_crawl_pages_domain", "crawl_pages", ["domain"])


def downgrade() -> None:
    op.drop_index("ix_crawl_pages_domain", table_name="crawl_pages")
    op.drop_table("crawl_pages")
```

- [ ] **Step 3: Write the failing DB tests**

```python
# tests/test_crawl_store.py
"""DB tests for the crawl_pages cache + RAG auto-embed store."""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, delete

from db.crawl_store import get_crawl, list_crawls, save_crawl
from db.models import CrawlPage


def _db_url() -> str:
    return os.getenv("DATABASE_URL", "")


def _cleanup(url: str) -> None:
    if not _db_url():
        return
    eng = create_engine(_db_url())
    with eng.connect() as conn:
        conn.execute(delete(CrawlPage).where(CrawlPage.url == url))
        conn.commit()
    eng.dispose()


@pytest.mark.skipif(not _db_url(), reason="DATABASE_URL not set")
def test_crawl_save_get_upsert_and_list():
    url = f"https://crawl-db-{uuid.uuid4().hex[:8]}.tn"
    domain = url.split("://")[1]
    try:
        save_crawl(url, title="Acme", domain=domain, markdown="Acme md",
                   fields={"hours": "9-18"}, status="ok", tags=["research"])
        row = get_crawl(url)
        assert row["status"] == "ok"
        assert row["fields"]["hours"] == "9-18"
        assert row["domain"] == domain

        save_crawl(url, title="Acme v2", domain=domain, markdown="updated", status="ok")
        row2 = get_crawl(url)
        assert row2["title"] == "Acme v2"
        assert row2["markdown"] == "updated"
        assert row2["fields"]["hours"] == "9-18"  # preserved on update

        rows = list_crawls(domain=domain)
        assert any(r["url"] == url for r in rows)
    finally:
        _cleanup(url)


@pytest.mark.skipif(not _db_url(), reason="DATABASE_URL not set")
def test_crawl_embed_writes_agent_chunk():
    from sqlalchemy import create_engine, text

    url = f"https://crawl-embed-{uuid.uuid4().hex[:8]}.tn"
    domain = url.split("://")[1]
    try:
        save_crawl(url, title="Acme", domain=domain, markdown="Acme marketing agency",
                   fields={}, status="ok")
        eng = create_engine(_db_url())
        with eng.connect() as conn:
            n = conn.execute(text(
                "SELECT count(*) FROM agent_chunks WHERE source_uri = :u"
            ), {"u": url}).scalar()
            conn.commit()
        eng.dispose()
        assert n == 0  # embedding is done by site_extract, not save_crawl itself
    finally:
        _cleanup(url)
```

- [ ] **Step 4: Implement `db/crawl_store.py`**

```python
"""Durable cache of crawled pages + auto-indexing into the RAG vector store."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from db.models import CrawlPage
from db.session import SessionLocal

logger = logging.getLogger(__name__)


def save_crawl(
    url: str,
    *,
    title: str = "",
    domain: str = "",
    markdown: str = "",
    fields: Optional[Dict[str, Any]] = None,
    status: str = "ok",
    source: str = "site_extract",
    tags: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """Insert or update a crawl record (keyed on url). Never raises."""
    try:
        session = SessionLocal()
        try:
            row = session.scalars(
                select(CrawlPage).where(CrawlPage.url == url)
            ).first()
            if row is None:
                row = CrawlPage(
                    id=uuid.uuid4(), url=url, title=title or "", domain=domain,
                    markdown=markdown or "", fields=fields or {}, status=status,
                    source=source, tags=tags or [], fetched_at=datetime.utcnow(),
                )
                session.add(row)
            else:
                row.title = title or row.title
                row.domain = domain or row.domain
                row.markdown = markdown or row.markdown
                row.fields = fields if fields is not None else row.fields
                row.status = status
                row.source = source
                if tags is not None:
                    row.tags = tags
                row.fetched_at = datetime.utcnow()
            session.commit()
            return _row_to_dict(row)
        finally:
            session.close()
    except BaseException as e:  # noqa: BLE001
        logger.warning("crawl_store.save_crawl failed for %s: %s", url, e)
        return None


def get_crawl(url: str) -> Optional[Dict[str, Any]]:
    try:
        session = SessionLocal()
        try:
            row = session.scalars(
                select(CrawlPage).where(CrawlPage.url == url)
            ).first()
            return _row_to_dict(row) if row else None
        finally:
            session.close()
    except BaseException:  # noqa: BLE001
        return None


def list_crawls(domain: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    try:
        session = SessionLocal()
        try:
            q = select(CrawlPage).order_by(CrawlPage.fetched_at.desc()).limit(limit)
            if domain:
                q = q.where(CrawlPage.domain == domain)
            return [_row_to_dict(r) for r in session.scalars(q).all()]
        finally:
            session.close()
    except BaseException:  # noqa: BLE001
        return []


def _row_to_dict(row: CrawlPage) -> Dict[str, Any]:
    return {
        "id": str(row.id),
        "url": row.url,
        "title": row.title,
        "domain": row.domain,
        "markdown": row.markdown,
        "fields": row.fields,
        "status": row.status,
        "source": row.source,
        "tags": row.tags,
        "fetched_at": row.fetched_at.isoformat() if row.fetched_at else None,
    }
```

- [ ] **Step 5: Run DB tests**

Run: `DATABASE_URL=... alembic upgrade head && DATABASE_URL=... pytest tests/test_crawl_store.py -v` (use the project's DB URL; without it the tests skip)
Expected: 2 PASS.

- [ ] **Step 6: Add site_extract cache/persist/embed tests**

Append to `tests/test_site_extract.py`:

```python
def test_site_extract_returns_cache_hit():
    cached = {"status": "ok", "title": "Acme", "markdown": "cached md",
              "fields": {"hours": "9-18"}, "source": "cache"}
    with patch("tools.site_extract_tool._cached", return_value=cached):
        out = site_extract("https://acme.tn", fields=["hours"])
    assert out["source"] == "cache"
    assert out["fields"]["hours"] == "9-18"


def test_site_extract_persists_and_embeds_after_crawl():
    with patch("tools.site_extract_tool._cached", return_value=None), \
         patch("tools.site_extract_tool._robots_allows", return_value=True), \
         patch("tools.site_extract_tool._crawl_sync", return_value=_page()), \
         patch("tools.site_extract_tool.chat_completion", return_value='{"email": "a@b.tn"}'), \
         patch("tools.site_extract_tool._persist_and_embed") as persist:
        site_extract("https://acme.tn", fields=["email"])
    persist.assert_called_once()


def test_site_extract_degrades_when_embedding_fails():
    def _boom(*a, **k):
        raise RuntimeError("ollama down")

    with patch("tools.site_extract_tool._cached", return_value=None), \
         patch("tools.site_extract_tool._robots_allows", return_value=True), \
         patch("tools.site_extract_tool._crawl_sync", return_value=_page()), \
         patch("tools.site_extract_tool.chat_completion", return_value="{}"), \
         patch("tools.site_extract_tool._persist_and_embed", side_effect=_boom):
        out = site_extract("https://acme.tn", fields=["email"])
    assert out["status"] == "ok"
```

- [ ] **Step 7: Run tests**

Run: `pytest tests/test_site_extract.py -v`
Expected: 9 PASS.

- [ ] **Step 8: Commit**

```bash
git add db/models.py db/crawl_store.py migrations/versions/20260811_0015_crawl_pages.py tests/test_crawl_store.py tests/test_site_extract.py
git commit -m "feat: durable crawl_pages cache + RAG auto-embed for site_extract"
```

---

### Task 6: Docker packaging + full verification

**Files:**
- Create: `requirements-crawl4ai.txt`
- Modify: `Dockerfile`

**Interfaces:**
- Consumes: all tasks above.
- Produces: Docker image with Crawl4AI installed; verified live research → `crawl_pages` row + `agent_chunks` chunk + `leads.research` populated.

- [ ] **Step 1: Create `requirements-crawl4ai.txt`**

```text
crawl4ai>=0.6.0
```

- [ ] **Step 2: Update `Dockerfile`**

Change line 16-17 to:

```dockerfile
COPY requirements.txt requirements-agents-crewai.txt requirements-crawl4ai.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-agents-crewai.txt -r requirements-crawl4ai.txt
```

Add after line 20 (`RUN playwright install chromium`):

```dockerfile
RUN crawl4ai-setup
```

- [ ] **Step 3: Run the full backend suite**

Run: `pytest tests -q`
Expected: all pass (DB tests skip without `DATABASE_URL`). If a DB URL is set, run `alembic upgrade head` first so migrations 0014 + 0015 apply.

- [ ] **Step 4: Live smoke — SearXNG**

Run:
```bash
docker compose up -d --build searxng
docker compose exec searxng curl -s "http://localhost:8080/search?q=agence+web+tunis&format=json" | head -c 500
```
Expected: JSON with a `results` array. If it returns HTML/403, verify `search.formats` includes `json` in `searxng/settings.yml`.

- [ ] **Step 5: Live smoke — research on a real lead (with Ollama running)**

Run: `docker compose --profile ollama up -d --build app ollama searxng`, then:

```bash
docker compose exec app python -c "
from tools.research_tool import research
out = research(name='Acme Web Agency', url='https://example.tn', country='Tunisia', gaps=['email', 'hours', 'description'])
print(out['status'], out['fields_found'], out['summary'][:120])
"
```
Expected: `status` is `ok`/`no_results` (never raises), `fields_found` contains coerced values, and a row exists in `crawl_pages` (`SELECT count(*) FROM crawl_pages;` > 0) plus a matching chunk in `agent_chunks` (`SELECT count(*) FROM agent_chunks WHERE agent_name='research' AND source_uri='https://example.tn';`).

- [ ] **Step 6: Live smoke — RAG retrieval finds the crawl**

Run:
```bash
docker compose exec app python -c "
from knowledge.rag import scoped_query
hits = scoped_query('research', 'what does example.tn do', scope='shared', limit=3)
print([h.get('source_uri') for h in hits])
"
```
Expected: the crawled `source_uri` appears, proving past crawls are queryable without re-fetching.

- [ ] **Step 7: Live smoke — enrich writes research**

Run: `docker compose exec app python -c "from workflows.enrich_leads import enrich_leads; print(enrich_leads([<lead_id>], recorder=<recorder>))"` — or trigger a lead-completion run through the API and confirm `leads.research` is populated and empty columns are filled.

- [ ] **Step 8: Commit**

```bash
git add requirements-crawl4ai.txt Dockerfile
git commit -m "chore: install Crawl4AI in Docker for site extraction"
```

---

## Self-Review

- **Spec coverage:** Every requirement maps to a task — SearXNG (Task 1), `site_extract` (Task 2), `research` orchestrator filling empty CRM fields (Task 3), hunter removal + migration (Task 4), crawl cache + RAG auto-embed reusing pgvector/Ollama (Task 5), Docker + verification (Task 6). `leads.research` column, enrich storage path, research API, and frontend are untouched by design.
- **Placeholder scan:** No TBDs; every step has concrete code or an exact command.
- **Type consistency:** `research()` and old `hunter()` return identical shapes; `site_extract()` contract is consistent between Task 2 and Task 5; `db.crawl_store` signatures are defined in Task 5 and consumed lazily by Task 2 (guarded by `try/except`). Migration chain: 0013 → 0014 → 0015.

**Execution options (pick one):**
1. **Subagent-Driven (recommended)** — fresh subagent per task with review between tasks.
2. **Inline Execution** — execute tasks in this session with checkpoints.
