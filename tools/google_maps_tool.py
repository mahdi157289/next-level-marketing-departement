"""Google Maps place-search scraper via Playwright (free, no API key).

Delegates to the superleadfinder/scraper.js Node.js scraper, which uses
the exact same scraping techniques, bot-detection evasion, and lead fields.
This module provides a Python interface that calls the Node.js scraper as a
subprocess and returns results in the standard {title, url, snippet, ...} format.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
from typing import Any, Dict, List, Optional, Callable

logger = logging.getLogger(__name__)

_LAST_GOOGLE_MAPS_DIAG: str = ""

# Path to the bundled Node.js scraper (superleadfinder/scraper.js)
# Located at tools/google_maps_scraper/ for self-contained deployment
_SUPERLEADFINDER_PATH = os.environ.get(
    "SUPERLEADFINDER_PATH",
    os.path.join(os.path.dirname(__file__), "google_maps_scraper"),
)

_NODE_BIN = os.environ.get("NODE_BIN", "node")


def get_last_google_maps_diag() -> str:
    return _LAST_GOOGLE_MAPS_DIAG


def google_maps_search(
    query: str,
    region: str = "Tunisia",
    max_results: int = 10,
    headless: bool = True,
    onLog: Callable[[str], None] = None,
    onProgress: Callable[[int], None] = None,
    onLeadScaped: Callable[[Dict[str, Any]], None] = None,
) -> List[Dict[str, Any]]:
    """Scrape Google Maps place search results via the Node.js superleadfinder scraper.

    This delegates to superleadfinder/scraper.js which uses Playwright with
    bot-detection evasion, infinite scroll, and full field extraction.

    Args:
        query: Keywords / Business Type (e.g. "plumber", "pizza restaurant").
        region: Where — City / Region (e.g. "Tunis, Tunisia").
        max_results: Max number of business hits (capped at 100).
        headless: Run browser in headless mode.
        onLog: Optional callback for log messages from the scraper.
        onProgress: Optional callback for count updates.
        onLeadScaped: Optional callback for each lead scraped.

    Returns:
        List of dicts: {title, url, snippet, address, phone, rating, ...}
    """
    global _LAST_GOOGLE_MAPS_DIAG
    _LAST_GOOGLE_MAPS_DIAG = ""

    _log = onLog or (lambda msg: logger.info(msg))
    _prog = onProgress or (lambda n: None)
    _lead = onLeadScaped or (lambda l: None)

    if not query.strip():
        _LAST_GOOGLE_MAPS_DIAG = "empty query"
        _log("google_maps_search: empty query")
        return []

    max_results = max(1, min(max_results, 100))

    wrapper_script = os.path.join(_SUPERLEADFINDER_PATH, "run-scrape.js")
    _LAST_GOOGLE_MAPS_DIAG = f"Calling Node.js scraper: {wrapper_script}"
    _log(f"Calling Node.js scraper for query='{query}' region='{region}' max={max_results}")

    if not os.path.exists(wrapper_script):
        _LAST_GOOGLE_MAPS_DIAG = f"ERROR: scraper wrapper not found at {wrapper_script}"
        _log(_LAST_GOOGLE_MAPS_DIAG)
        return []

    results: List[Dict[str, Any]] = []

    try:
        proc = subprocess.Popen(
            [_NODE_BIN, wrapper_script, query, region, str(max_results), str(headless).lower()],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=_SUPERLEADFINDER_PATH,
        )

        # Read stdout line by line for both progress updates and final result
        while True:
            line = proc.stdout.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            if data.get("type") == "lead":
                # A lead was scraped (streaming)
                lead = data.get("data", {})
                # Normalize to our return format
                normalized = _normalize_lead(lead)
                _lead(normalized)
                results.append(normalized)
                _prog(len(results))
                _log(f"Scraped lead: {normalized.get('title', 'Unknown')}")
            elif data.get("type") == "complete":
                # Final summary
                final_leads = data.get("leads", [])
                if not results:
                    # Process any leads that came in final summary but weren't streamed
                    for lead in final_leads:
                        normalized = _normalize_lead(lead)
                        _lead(normalized)
                        results.append(normalized)
                        _prog(len(results))
                total = data.get("count", len(results))
                _log(f"Scraping complete: {total} leads")
            elif data.get("type") == "error":
                _LAST_GOOGLE_MAPS_DIAG += f" | ERROR: {data.get('message', 'unknown')}"
                _log(f"Scraper error: {data.get('message')}")

        # Read any stderr for diagnostic info
        stderr_output = proc.stderr.read()
        if stderr_output:
            _LAST_GOOGLE_MAPS_DIAG += f" | stderr: {stderr_output[:200]}"

        proc.wait()

        if proc.returncode != 0:
            _LAST_GOOGLE_MAPS_DIAG += f" | exit code: {proc.returncode}"

    except FileNotFoundError:
        _LAST_GOOGLE_MAPS_DIAG = "ERROR: Node.js not found. Install Node.js to use the scraper."
        _log(_LAST_GOOGLE_MAPS_DIAG)
        return []
    except Exception as e:
        _LAST_GOOGLE_MAPS_DIAG = f"ERROR: {type(e).__name__}: {e}"
        _log(f"google_maps_search failed: {_LAST_GOOGLE_MAPS_DIAG}")
        return results

    if results:
        _LAST_GOOGLE_MAPS_DIAG += f" | OK found={len(results)}"
    else:
        _LAST_GOOGLE_MAPS_DIAG += " | empty (no leads scraped)"

    _log(f"google_maps_search done: {_LAST_GOOGLE_MAPS_DIAG}")
    return results[:max_results]


def _normalize_lead(lead: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a lead from the Node.js scraper to our standard return format."""
    raw_phone = lead.get("phone", "") or ""
    phone = raw_phone if raw_phone and raw_phone != "Not available" else ""

    raw_website = lead.get("website", "") or ""
    maps_url = lead.get("url", "") or lead.get("google_maps_url", "") or ""
    url = raw_website if raw_website and raw_website != "Not available" else ""

    # Filter junk URLs
    if url and _is_junk_url(url):
        url = ""

    # Fall back to Google Maps URL so the lead still passes filter_prospect_hits
    # Don't use _is_junk_url here because google.com/maps URLs pass filter_prospect_hits
    if not url and maps_url:
        url = maps_url

    # Normalize phone
    if phone:
        phone_digits = re.sub(r"\D", "", phone)
        if len(phone_digits) < 7:
            phone = ""

    rating = lead.get("rating", "") or ""
    review_count = lead.get("reviewsCount", "") or lead.get("review_count", "") or ""
    address = _clean_field(lead.get("address", "") or "")
    category = _clean_field(lead.get("category", "") or "")
    hours = _clean_field(lead.get("hours", "") or "")
    description = _clean_field(lead.get("description", "") or "")

    # Build snippet from cleaned fields (not the raw lead)
    snippet_parts = []
    if rating:
        snippet_parts.append(f"\u2b50 {rating}")
    if review_count:
        snippet_parts.append(f"({review_count} reviews)")
    if category:
        snippet_parts.append(category)
    if address:
        snippet_parts.append(address)
    if phone:
        snippet_parts.append(phone)
    snippet = " \u00b7 ".join(snippet_parts)

    result = {
        "title": (lead.get("name", "") or "")[:256].strip(),
        "url": url[:512] if url else "",
        "snippet": snippet[:500],
        "address": address,
        "phone": phone,
        "rating": rating,
        "review_count": review_count,
        "category": category,
        "hours": hours,
        "description": description,
        "google_maps_url": maps_url,
        "facebook": (lead.get("facebook") or lead.get("socials", {}).get("facebook", "")) if lead.get("socials") else "",
        "instagram": (lead.get("instagram") or lead.get("socials", {}).get("instagram", "")) if lead.get("socials") else "",
        "linkedin": (lead.get("linkedin") or lead.get("socials", {}).get("linkedin", "")) if lead.get("socials") else "",
        "twitter": (lead.get("twitter") or lead.get("socials", {}).get("twitter", "")) if lead.get("socials") else "",
        "price_level": lead.get("price_level", ""),
        "tags": lead.get("tags", []),
    }

    return result


def _clean_field(value: str) -> str:
    """Strip 'Not available' / empty placeholders and whitespace from a field."""
    if not value:
        return ""
    value = value.strip()
    if value.lower() in ("not available", "n/a", "none", "null"):
        return ""
    return value


# Reuse junk-filter needles from web_search_tool
from tools.web_search_tool import _JUNK_HOST_NEEDLES  # noqa: E402

# Additional Google-internal URL patterns to filter
_GOOGLE_HOST_NEEDLES = (
    "google.com/maps",
    "maps.google.com",
    "google.com",
)


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
