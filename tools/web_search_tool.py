"""Web search via DuckDuckGo-backed clients.

Prefer `ddgs` (successor to deprecated `duckduckgo_search`). Falls back to
`duckduckgo_search` if `ddgs` is not installed.

Tries multiple ddgs engine backends and ranks hits so dictionary/wiki spam
does not win over regional business listings.

See: https://pypi.org/project/ddgs/
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Filled on failure for operators (pytest -s / real_verification prints it).
_LAST_WEB_SEARCH_DIAG: str = ""

# Engines that historically return usable local-business hits for this project.
_DDGS_ENGINE_ORDER = ("yahoo", "brave", "bing", "auto")

_JUNK_HOST_NEEDLES = (
    "wikipedia.org",
    "wiktionary.org",
    "merriam-webster.com",
    "cambridge.org",
    "britannica.com",
    "dictionary.com",
    "drive.google.com",
    "accounts.google.com",
    "docs.google.com",
    "support.microsoft.com",
    "login.microsoftonline.com",
    "outlook.live.com",
    "softonic.com",
    "microsoft.com",
    "bing.com",  # ad redirect digests
)


def get_last_web_search_diag() -> str:
    return _LAST_WEB_SEARCH_DIAG


def _discover_ddgs_classes() -> List[Tuple[str, Callable[[], Any]]]:
    """Return [(label, factory), ...] where factory returns a context manager with .text()."""
    out: List[Tuple[str, Callable[[], Any]]] = []

    try:
        from ddgs import DDGS as DDGSNew  # type: ignore

        out.append(("ddgs", DDGSNew))
    except ImportError:
        pass

    try:
        from duckduckgo_search import DDGS as DDGSOld  # type: ignore

        out.append(("duckduckgo_search", DDGSOld))
    except ImportError:
        pass

    return out


def _normalize_item(item: Dict[str, Any]) -> Dict[str, str]:
    return {
        "title": str(item.get("title", "") or ""),
        "url": str(item.get("href", "") or item.get("url", "") or ""),
        "snippet": str(item.get("body", "") or item.get("snippet", "") or ""),
    }


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _is_junk(hit: Dict[str, str]) -> bool:
    url = (hit.get("url") or "").lower()
    host = _host(url)
    if not host:
        return True
    if any(n in host or n in url for n in _JUNK_HOST_NEEDLES):
        return True
    # Advertisement click wrappers without a real destination in href
    if "bing.com/aclick" in url:
        return True
    return False


def _relevance_score(hit: Dict[str, str], query: str) -> int:
    """Higher is better — prefer hits that mention query tokens / TLD business signals."""
    if _is_junk(hit):
        return -100
    blob = f"{hit.get('title', '')} {hit.get('snippet', '')} {hit.get('url', '')}".lower()
    score = 0
    tokens = [t for t in re.split(r"\W+", query.lower()) if len(t) > 2]
    for t in tokens:
        if t in blob:
            score += 2
    host = _host(hit.get("url") or "")
    if host.endswith(".tn"):
        score += 8
    if any(k in blob for k in ("agency", "agence", "marketing", "digital", "software", "web")):
        score += 3
    if any(k in blob for k in ("definition", "meaning", "dictionary", "encyclopedia", "wikipedia")):
        score -= 20
    return score


def _dedupe_by_url(hits: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = set()
    out: List[Dict[str, str]] = []
    for h in hits:
        url = (h.get("url") or "").rstrip("/")
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(h)
    return out


def web_search_tool(query: str, max_results: int = 10) -> List[Dict[str, str]]:
    """Search and return list of {title, url, snippet}. Empty list if all attempts fail."""
    global _LAST_WEB_SEARCH_DIAG
    _LAST_WEB_SEARCH_DIAG = ""

    backends = _discover_ddgs_classes()
    if not backends:
        _LAST_WEB_SEARCH_DIAG = "No search backend installed. Run: pip install ddgs"
        logger.error(_LAST_WEB_SEARCH_DIAG)
        return []

    last_exc: Optional[BaseException] = None
    collected: List[Dict[str, str]] = []
    tried: List[str] = []

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
