"""Fetch page content with Playwright; respect robots.txt via urllib.robotparser."""

from __future__ import annotations

import re
import urllib.robotparser
from typing import Any, Dict, List
from urllib.parse import urljoin, urlparse

from playwright.sync_api import sync_playwright

DEFAULT_UA = (
    "Mozilla/5.0 (compatible; NextLevelMarketingDept/1.0; +https://the-next-level-tech-company-1.onrender.com)"
)


def _robots_allows(url: str, user_agent: str = "*") -> bool:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return False
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(robots_url)
    try:
        rp.read()
    except Exception:
        # No robots or unreadable — allow (per common crawler practice)
        return True
    try:
        return rp.can_fetch(user_agent, url)
    except Exception:
        return True


def scrape_tool(url: str, timeout_ms: int = 15_000) -> Dict[str, Any]:
    """
    Load URL in headless Chromium; return title, url, sample emails/phones from HTML.
    If robots.txt disallows the URL for *, returns error dict.
    """
    if not _robots_allows(url, DEFAULT_UA):
        return {"error": "robots_disallowed", "url": url}

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page(user_agent=DEFAULT_UA)
                page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
                html = page.content()
                title = page.title()
            finally:
                browser.close()
    except Exception as e:
        return {"error": "timeout" if "Timeout" in type(e).__name__ else "fetch_failed", "detail": str(e), "url": url}

    emails = list(
        set(
            re.findall(
                r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
                html,
            )
        )
    )
    phones = list(set(re.findall(r"\+?[\d\s\-().]{7,15}", html)))

    return {
        "title": title,
        "url": url,
        "emails": emails[:5],
        "phones": phones[:3],
    }
