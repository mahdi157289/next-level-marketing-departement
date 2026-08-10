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
