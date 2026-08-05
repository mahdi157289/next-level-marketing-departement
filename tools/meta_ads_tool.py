"""Meta Ad Library API — find businesses running ads (active spenders = hot leads)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

API_BASE = "https://graph.facebook.com/v21.0/ads_archive"

_ad_search_diag: List[str] = []


def _get_token() -> str:
    from config.settings import get_settings
    token = get_settings().meta_ads_access_token
    if token:
        return token.strip()
    return (os.getenv("META_ADS_ACCESS_TOKEN") or "").strip()


def _log(msg: str) -> None:
    _ad_search_diag.append(msg)


def get_last_meta_ad_diag() -> List[str]:
    return list(_ad_search_diag)


def meta_ads_search(
    search_terms: str = "",
    country: str = "TN",
    limit: int = 10,
    ad_active_status: str = "ACTIVE",
) -> List[Dict[str, Any]]:
    """Search Meta Ad Library for running ads in a country.

    Returns list of dicts with keys: title, url, snippet (matching web_search format).
    Each result is a Facebook Page running ads — their landing page is the lead URL.
    """
    token = _get_token()
    if not token:
        _log("META_ADS_ACCESS_TOKEN not set — skipping Meta Ad Library search")
        return []

    params: Dict[str, Any] = {
        "access_token": token,
        "ad_active_status": ad_active_status,
        "ad_reached_countries": [country],
        "limit": min(limit, 50),
        "fields": "page_name,ad_creation_time,ad_delivery_start_time,ad_creative_bodies,snapshot_url,landing_page_urls",
    }
    if search_terms.strip():
        params["search_terms"] = search_terms.strip()

    query = urllib.parse.urlencode(params, doseq=True)
    url = f"{API_BASE}?{query}"

    _log(f"GET {API_BASE} country={country} terms={search_terms!r} limit={limit}")
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:300]
        _log(f"HTTP {e.code}: {detail}")
        return []
    except Exception as e:
        _log(f"Error: {e}")
        return []

    data = body.get("data") or []
    _log(f"Found {len(data)} ads")

    results = []
    seen_pages: set = set()
    for ad in data:
        page_name = ad.get("page_name", "")
        page_id = ad.get("page_id", "")
        if not page_name or page_id in seen_pages:
            continue
        seen_pages.add(page_id)

        landing_urls = ad.get("landing_page_urls") or []
        url = landing_urls[0] if landing_urls else f"https://facebook.com/{page_id}"

        bodies = ad.get("ad_creative_bodies") or []
        snippet = (bodies[0] if bodies else "Running Facebook ads")[:500]

        results.append({
            "title": page_name,
            "url": url,
            "snippet": snippet,
            "source": "meta_ads",
            "page_id": page_id,
        })
        if len(results) >= limit:
            break

    _log(f"{len(results)} unique pages extracted")
    return results
